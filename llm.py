"""
Unified LLM wrapper.

- anthropic provider → Anthropic Python SDK
- nvidia provider    → OpenAI Python SDK pointing at OpenRouter
                       (OpenRouter uses the OpenAI-compatible REST format,
                        NOT the Anthropic messages format)

Agents call llm.get_client() and llm.complete(client, prompt).
"""
from __future__ import annotations

import time

from config import LLM_PROVIDER, LLM_BASE_URL, MODEL, ANTHROPIC_API_KEY, NVIDIA_API_KEY


def get_client():
    if LLM_PROVIDER == "anthropic":
        import anthropic
        return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    elif LLM_PROVIDER == "nvidia":
        from openai import OpenAI
        return OpenAI(base_url=LLM_BASE_URL, api_key=NVIDIA_API_KEY)

    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER!r}. Use 'anthropic' or 'nvidia'.")


def complete(client, prompt: str, max_tokens: int = 3000,
             max_retries: int = 5) -> tuple[str, dict]:
    """Send a prompt and return (response_text, usage_dict).

    Automatically retries on 429 rate-limit errors (common with free tier).
    """

    if LLM_PROVIDER == "nvidia":
        from openai import RateLimitError

        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=0.1,
                )
                text = response.choices[0].message.content or ""
                usage = {
                    "input_tokens":  response.usage.prompt_tokens if response.usage else 0,
                    "output_tokens": response.usage.completion_tokens if response.usage else 0,
                    "api_calls":     1,
                }
                return text, usage

            except RateLimitError as exc:
                # Try to honour the Retry-After hint from OpenRouter
                retry_after = 30
                try:
                    meta = exc.body.get("error", {}).get("metadata", {})
                    retry_after = int(meta.get("retry_after_seconds", 30)) + 2
                except Exception:
                    pass

                if attempt < max_retries - 1:
                    print(f"  [rate limit] waiting {retry_after}s before retry "
                          f"({attempt + 1}/{max_retries - 1})…")
                    time.sleep(retry_after)
                else:
                    raise

    else:
        # Anthropic SDK format
        response = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        usage = {
            "input_tokens":  response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "api_calls":     1,
        }
        return text, usage
