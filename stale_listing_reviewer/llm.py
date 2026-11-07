"""Optional AI summary via any OpenAI-compatible endpoint.

Works with Ollama (http://localhost:11434/v1), LM Studio, llama.cpp server,
or any OpenAI-style /chat/completions endpoint. No API key is required for
local servers; if your endpoint needs one, set it in the OPENAI_API_KEY
environment variable (never in a file).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class SummaryError(RuntimeError):
    """Raised when the summary endpoint fails or returns junk."""


def summarize(
    worksheet_text: str,
    api_base: str,
    model: str,
    timeout: float = 60.0,
) -> str:
    """Return a short plain-English summary of the worksheet.

    Calls POST {api_base}/chat/completions with an OpenAI-style payload.
    api_base should NOT include the /chat/completions path, e.g.
    "http://localhost:11434/v1" for Ollama.
    """
    if not api_base:
        raise SummaryError("api_base is empty")
    api_base = api_base.rstrip("/")
    if api_base.endswith("/chat/completions"):
        api_base = api_base[: -len("/chat/completions")]

    url = f"{api_base}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a friendly reselling assistant. Summarize the "
                    "stale-listing worksheet below in plain English. Name the "
                    "worst 2-3 listings, the overall theme (age vs low cart "
                    "rate), and one simple next action. Keep it under 150 "
                    "words. This is general guidance, not financial advice."
                ),
            },
            {"role": "user", "content": worksheet_text[:12000]},
        ],
        "temperature": 0.3,
    }

    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise SummaryError(f"endpoint returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SummaryError(
            f"could not reach {url} ({exc.reason}). Is the server running?"
        ) from exc

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SummaryError(f"unexpected response shape: {body!r}") from exc
    if not isinstance(content, str) or not content.strip():
        raise SummaryError("empty summary returned")
    return content.strip()
