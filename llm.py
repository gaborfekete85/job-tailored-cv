"""One structured-output LLM call, routed by ENV.

ENV=local -> Claude Agent SDK on the local Claude Code login (subscription).
otherwise -> Anthropic API with API_KEY.
"""

import json
import os

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

MODEL = os.getenv("MODEL", "claude-opus-5-5")


async def structured[T: BaseModel](system: str, prompt: str, schema: type[T]) -> T:
    if os.getenv("ENV", "local").lower() == "local":
        return await _local(system, prompt, schema)
    return await _api(system, prompt, schema)


async def _local[T: BaseModel](system: str, prompt: str, schema: type[T]) -> T:
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

    # Drop any API key so the CLI falls back to the subscription login.
    os.environ.pop("ANTHROPIC_API_KEY", None)
    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=system,
        allowed_tools=[],
        max_turns=4,
        output_format={"type": "json_schema", "schema": schema.model_json_schema()},
    )
    result: ResultMessage | None = None
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            result = message
    if result is None or result.is_error:
        raise RuntimeError(f"Claude Agent SDK call failed: {result and result.errors}")
    if result.structured_output is not None:
        return schema.model_validate(result.structured_output)
    return schema.model_validate(json.loads(result.result or ""))


async def _api[T: BaseModel](system: str, prompt: str, schema: type[T]) -> T:
    from anthropic import AsyncAnthropic

    api_key = os.getenv("API_KEY")
    if not api_key:
        raise SystemExit("API_KEY is empty; set it in .env or use ENV=local")
    client = AsyncAnthropic(api_key=api_key)
    response = await client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_format=schema,
    )
    return response.parsed_output
