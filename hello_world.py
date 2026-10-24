"""Hello-world LLM smoke test.

ENV=local -> Claude Agent SDK, authenticated through the local Claude Code
             login (your Claude subscription). No API key required.
otherwise -> Anthropic API, authenticated with API_KEY.
"""

import asyncio
import os

from dotenv import load_dotenv

MODEL = "claude-opus-5-5"
PROMPT = "Say hello world in one short, friendly sentence."


async def ask_local(prompt: str) -> str:
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

    # Drop any API key so the CLI falls back to the subscription login.
    os.environ.pop("ANTHROPIC_API_KEY", None)
    options = ClaudeAgentOptions(model=MODEL, max_turns=1, allowed_tools=[])
    parts: list[str] = []
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            parts.extend(b.text for b in message.content if isinstance(b, TextBlock))
    return "".join(parts)


def ask_api(prompt: str) -> str:
    from anthropic import Anthropic

    api_key = os.getenv("API_KEY")
    if not api_key:
        raise SystemExit("API_KEY is empty; set it in .env or use ENV=local")
    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in response.content if b.type == "text")


def main() -> None:
    load_dotenv()
    env = os.getenv("ENV", "local").lower()
    print(f"ENV={env}")
    answer = asyncio.run(ask_local(PROMPT)) if env == "local" else ask_api(PROMPT)
    print(answer)


if __name__ == "__main__":
    main()
