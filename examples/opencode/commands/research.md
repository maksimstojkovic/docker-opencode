---
description: Research a topic with live web grounding and inline citations.
model: openrouter/moonshotai/kimi-k2.6:online
---
Research the following topic. Use the `:online` web grounding to find current
sources rather than relying on training data.

Topic: $ARGUMENTS

Output structure:
- **TL;DR** — two sentences.
- **Key facts** — bullet list, each with an inline `[source-domain]` citation.
- **Contested or uncertain** — anything where reputable sources disagree.
- **Further reading** — three URLs that go deeper than the above.
