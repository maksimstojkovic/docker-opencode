#!/usr/bin/env python3
"""
OpenRouter image-generation MCP server (stdio transport).

Exposes a single tool, `generate_image`, that calls OpenRouter's image-capable
chat completions endpoint and saves the result to /workspace/.opencode/generated/.

Stdlib only — no pip dependencies, runs against Alpine's python3 as-is.
Logs to stderr (stdout is reserved for the MCP JSON-RPC protocol).

Wire it into opencode.json:

    "mcp": {
      "imagegen": {
        "type": "local",
        "command": ["python3", "/usr/local/lib/opencode-mcp/imagegen.py"],
        "environment": { "OPENROUTER_API_KEY": "{env:OPENROUTER_API_KEY}" },
        "enabled": true
      }
    }
"""

import base64
import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Google's current image-gen model on OpenRouter (aka "Nano Banana 2"). Update
# this slug when Google ships the next preview; OpenRouter doesn't expose a
# stable `-latest` alias for image-preview models, so the family slug here
# tracks the current preview version. If this 404s, try the date-pinned
# variant: google/gemini-3.1-flash-image-preview-20260226
DEFAULT_MODEL = "google/gemini-3.1-flash-image-preview"
OUTPUT_ROOT = Path("/workspace/.opencode/generated")
REQUEST_TIMEOUT = 180  # seconds — image gen can be slow
PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "imagegen"
SERVER_VERSION = "0.1.0"

EXT_BY_MIME = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}


# --- stdio MCP plumbing -----------------------------------------------------

def log(msg):
    print(f"[imagegen] {msg}", file=sys.stderr, flush=True)


def send(payload):
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def send_result(req_id, result):
    send({"jsonrpc": "2.0", "id": req_id, "result": result})


def send_error(req_id, code, message):
    send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


# --- MCP method handlers ----------------------------------------------------

def handle_initialize(req_id, _params):
    send_result(req_id, {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {}},
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
    })


def handle_tools_list(req_id, _params):
    send_result(req_id, {
        "tools": [{
            "name": "generate_image",
            "description": (
                "Generate an image from a text prompt via OpenRouter. "
                "Saves the result to /workspace/.opencode/generated/<YYYY-MM-DD>/ "
                "and returns the file path plus the image inline. "
                f"Default model: {DEFAULT_MODEL} (Google Nano Banana 2). "
                "Other useful image models: openai/gpt-5.4-image-2 "
                "(GPT-driven, strong text-in-image)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Text prompt describing the image to generate.",
                    },
                    "model": {
                        "type": "string",
                        "description": (
                            "OpenRouter model id. Defaults to "
                            f"{DEFAULT_MODEL}. Must be an image-output model."
                        ),
                        "default": DEFAULT_MODEL,
                    },
                },
                "required": ["prompt"],
            },
        }]
    })


def handle_tools_call(req_id, params):
    name = params.get("name")
    if name != "generate_image":
        send_error(req_id, -32602, f"unknown tool: {name}")
        return

    args = params.get("arguments") or {}
    prompt = args.get("prompt")
    if not prompt or not isinstance(prompt, str):
        send_error(req_id, -32602, "argument 'prompt' is required and must be a string")
        return
    model = args.get("model") or DEFAULT_MODEL

    log(f"generate_image model={model} prompt={prompt[:80]!r}")
    try:
        response = call_openrouter(prompt, model)
        b64, mime = extract_image(response)
        out_path = save_image(b64, mime)
        log(f"saved {out_path} ({len(b64) * 3 // 4} bytes)")
        send_result(req_id, {
            "content": [
                {"type": "text", "text": f"Image saved to {out_path}"},
                {"type": "image", "data": b64, "mimeType": mime},
            ]
        })
    except Exception as e:  # noqa: BLE001 — propagate as MCP error
        log(f"error: {e}")
        send_error(req_id, -32603, str(e))


# --- OpenRouter call + response parsing -------------------------------------

def call_openrouter(prompt, model):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY env var is not set in the MCP process")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        # Tell OpenRouter we want both image and text back. For image-only
        # models this is harmless; for hybrid models it allows the assistant
        # to caption alongside the image.
        "modalities": ["image", "text"],
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/maksimstojkovic/docker-opencode",
            "X-Title": "docker-opencode-imagegen",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter HTTP {e.code}: {detail[:1000]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"OpenRouter request failed: {e}")


def extract_image(response):
    """
    Image-output providers differ in shape; try the patterns we know:
      1. message.images[].image_url.url   (Gemini-style via OpenRouter)
      2. message.content[].image_url.url  (OpenAI multimodal-content style)
      3. message.content[].source.data    (Anthropic-style base64)
    Returns (base64_data, mime_type).
    """
    try:
        msg = response["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(_short(f"no choices[0].message in response: {response}"))

    # Pattern 1
    for img in (msg.get("images") or []):
        url = (img.get("image_url") or {}).get("url") if isinstance(img, dict) else None
        if url:
            return _from_data_uri_or_url(url)

    # Pattern 2 & 3
    content = msg.get("content")
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") in ("image_url", "image"):
                url = (part.get("image_url") or {}).get("url")
                if url:
                    return _from_data_uri_or_url(url)
                src = part.get("source") or {}
                if src.get("type") == "base64" and src.get("data"):
                    return src["data"], src.get("media_type") or "image/png"

    raise RuntimeError(_short(
        f"no image data found in any known location. Full response: {response}"
    ))


def _from_data_uri_or_url(url):
    if url.startswith("data:"):
        try:
            header, b64 = url.split(",", 1)
        except ValueError:
            raise RuntimeError(f"malformed data URI: {url[:80]!r}")
        mime = header[5:].split(";")[0] or "image/png"
        return b64, mime
    # External URL — download and base64-encode.
    log(f"downloading image URL: {url[:120]}")
    with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as r:
        data = r.read()
        mime = r.headers.get("Content-Type", "image/png").split(";")[0].strip()
    return base64.b64encode(data).decode("ascii"), mime


def save_image(b64data, mime):
    today = datetime.date.today().isoformat()
    out_dir = OUTPUT_ROOT / today
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%H%M%S-%f")[:-3]
    ext = EXT_BY_MIME.get(mime, "bin")
    out_path = out_dir / f"{ts}.{ext}"
    out_path.write_bytes(base64.b64decode(b64data))
    return out_path


def _short(s, n=600):
    s = str(s)
    return s if len(s) <= n else s[:n] + "...(truncated)"


# --- main loop --------------------------------------------------------------

HANDLERS = {
    "initialize": handle_initialize,
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
}


def main():
    log(f"starting (default model: {DEFAULT_MODEL}, output: {OUTPUT_ROOT})")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            log(f"bad JSON from client: {e}")
            continue

        method = msg.get("method")
        req_id = msg.get("id")
        params = msg.get("params") or {}

        # Notifications (no id) — no response expected.
        if req_id is None:
            log(f"notification: {method}")
            continue

        handler = HANDLERS.get(method)
        if not handler:
            send_error(req_id, -32601, f"method not found: {method}")
            continue

        try:
            handler(req_id, params)
        except Exception as e:  # noqa: BLE001
            log(f"handler exception in {method}: {e}")
            send_error(req_id, -32603, f"internal error: {e}")


if __name__ == "__main__":
    main()
