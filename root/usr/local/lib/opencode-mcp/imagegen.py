#!/usr/bin/env python3
"""OpenRouter image-generation MCP server (stdio transport, stdlib-only)."""

import base64
import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Env override > hardcoded fallback. OpenRouter has no stable -latest alias
# for image-preview models, so bump the fallback when Google ships the next one.
DEFAULT_MODEL = os.environ.get(
    "IMAGEGEN_DEFAULT_MODEL",
    "google/gemini-3.1-flash-image-preview",
)
WORKSPACE_ROOT = Path(os.environ.get("IMAGEGEN_WORKSPACE_ROOT", "/workspace")).resolve()
OUTPUT_SUBDIR = ".images"
REQUEST_TIMEOUT = 180
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


def log(msg):
    # stderr only — stdout is reserved for the JSON-RPC protocol.
    print(f"[imagegen] {msg}", file=sys.stderr, flush=True)


def send(payload):
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def send_result(req_id, result):
    send({"jsonrpc": "2.0", "id": req_id, "result": result})


def send_error(req_id, code, message):
    send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def handle_initialize(req_id, _params):
    send_result(
        req_id,
        {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        },
    )


def handle_tools_list(req_id, _params):
    send_result(
        req_id,
        {
            "tools": [
                {
                    "name": "generate_image",
                    "description": (
                        "Generate ONE image from a text prompt via OpenRouter. "
                        "Call this tool exactly once per user request — do NOT call it "
                        "multiple times to produce variations unless the user explicitly "
                        "asks for multiple images or alternative versions. "
                        f"Saves to <directory>/{OUTPUT_SUBDIR}/<YYYY-MM-DD>/ and returns "
                        "the path plus the image inline. Pass 'directory' as the absolute "
                        f"path of the active project so images land inside it; falls back to "
                        f"{WORKSPACE_ROOT}/{OUTPUT_SUBDIR} otherwise. "
                        f"Default model: {DEFAULT_MODEL}."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": "Text prompt describing the image.",
                            },
                            "model": {
                                "type": "string",
                                "description": f"OpenRouter image-output model id. Default: {DEFAULT_MODEL}.",
                                "default": DEFAULT_MODEL,
                            },
                            "directory": {
                                "type": "string",
                                "description": (
                                    "Absolute path of the active project/workspace. "
                                    f"Image is saved under <directory>/{OUTPUT_SUBDIR}/. "
                                    f"Must resolve inside {WORKSPACE_ROOT}; otherwise falls "
                                    f"back to {WORKSPACE_ROOT}/{OUTPUT_SUBDIR}."
                                ),
                            },
                        },
                        "required": ["prompt"],
                    },
                }
            ]
        },
    )


def handle_tools_call(req_id, params):
    if params.get("name") != "generate_image":
        send_error(req_id, -32602, f"unknown tool: {params.get('name')}")
        return

    args = params.get("arguments") or {}
    prompt = args.get("prompt")
    if not prompt or not isinstance(prompt, str):
        send_error(req_id, -32602, "argument 'prompt' is required and must be a string")
        return
    model = args.get("model") or DEFAULT_MODEL
    project_dir = resolve_project_dir(args.get("directory"))

    log(f"generate_image model={model} dir={project_dir} prompt={prompt[:80]!r}")
    try:
        response = call_openrouter(prompt, model)
        b64, mime = extract_image(response)
        out_path = save_image(b64, mime, project_dir)
        log(f"saved {out_path}")
        send_result(
            req_id,
            {
                "content": [
                    {"type": "text", "text": f"Image saved to {out_path}"},
                    {"type": "image", "data": b64, "mimeType": mime},
                ]
            },
        )
    except Exception as e:
        log(f"error: {e}")
        send_error(req_id, -32603, str(e))


def call_openrouter(prompt, model):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set in MCP process env")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image", "text"],
    }
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
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
    # Try the three known response shapes: Gemini-style (message.images[]),
    # OpenAI multimodal content (message.content[].image_url), Anthropic base64.
    try:
        msg = response["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(_short(f"no choices[0].message in response: {response}"))

    for img in msg.get("images") or []:
        url = (img.get("image_url") or {}).get("url") if isinstance(img, dict) else None
        if url:
            return _from_data_uri_or_url(url)

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

    raise RuntimeError(_short(f"no image data in response: {response}"))


def _from_data_uri_or_url(url):
    if url.startswith("data:"):
        try:
            header, b64 = url.split(",", 1)
        except ValueError:
            raise RuntimeError(f"malformed data URI: {url[:80]!r}")
        mime = header[5:].split(";")[0] or "image/png"
        return b64, mime
    log(f"downloading image URL: {url[:120]}")
    with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as r:
        data = r.read()
        mime = r.headers.get("Content-Type", "image/png").split(";")[0].strip()
    return base64.b64encode(data).decode("ascii"), mime


def resolve_project_dir(raw):
    # Sandbox to WORKSPACE_ROOT so a hallucinated path can't drop files in /etc.
    if raw and isinstance(raw, str):
        try:
            candidate = Path(raw).resolve()
            if candidate == WORKSPACE_ROOT or WORKSPACE_ROOT in candidate.parents:
                if candidate.is_dir():
                    return candidate
                log(f"directory {candidate} does not exist, falling back to {WORKSPACE_ROOT}")
            else:
                log(f"directory {candidate} outside {WORKSPACE_ROOT}, falling back")
        except (OSError, ValueError) as e:
            log(f"could not resolve directory {raw!r}: {e}")
    return WORKSPACE_ROOT


def save_image(b64data, mime, project_dir):
    out_dir = project_dir / OUTPUT_SUBDIR / datetime.date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%H%M%S-%f")[:-3]
    out_path = out_dir / f"{ts}.{EXT_BY_MIME.get(mime, 'bin')}"
    out_path.write_bytes(base64.b64decode(b64data))
    return out_path


def _short(s, n=600):
    s = str(s)
    return s if len(s) <= n else s[:n] + "...(truncated)"


HANDLERS = {
    "initialize": handle_initialize,
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
}


def main():
    log(f"starting (default={DEFAULT_MODEL}, workspace={WORKSPACE_ROOT}, subdir={OUTPUT_SUBDIR})")
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

        if req_id is None:
            log(f"notification: {method}")
            continue

        handler = HANDLERS.get(method)
        if not handler:
            send_error(req_id, -32601, f"method not found: {method}")
            continue

        try:
            handler(req_id, params)
        except Exception as e:
            log(f"handler exception in {method}: {e}")
            send_error(req_id, -32603, f"internal error: {e}")


if __name__ == "__main__":
    main()
