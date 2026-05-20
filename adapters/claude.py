"""Claude Agent SDK adapter.

`run_task(question, dsn, model, trace_path)` runs one analytics question
end-to-end:
  - spawns `tools.server` over stdio as the MCP tool source
  - hands the SDK the system prompt from `prompts/system.md`
  - streams the agent loop, recording every model output / tool call / tool
    result to JSONL
  - returns the last assistant text (the answer) and a structured RunResult

No retries, no fallbacks.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)
from claude_agent_sdk.types import McpStdioServerConfig

from tracing.jsonl import open_trace

REPO_ROOT = Path(__file__).resolve().parent.parent
SYSTEM_PROMPT_PATH = REPO_ROOT / "prompts" / "system.md"

MCP_SERVER_NAME = "sql"
MCP_TOOLS = [
    "connect", "disconnect", "list_tables", "describe_schema",
    "sample_rows", "execute_sql", "validate_sql",
]
ALLOWED_TOOLS = [f"mcp__{MCP_SERVER_NAME}__{t}" for t in MCP_TOOLS]


@dataclass
class RunResult:
    answer: str | None             # last assistant text
    num_turns: int
    total_cost_usd: float | None
    input_tokens: int | None
    output_tokens: int | None
    stop_reason: str | None
    is_error: bool
    error: str | None
    trace_path: Path


def _build_user_prompt(question: str, dsn: str, business_context: str | None) -> str:
    parts = []
    if business_context:
        parts.append(f"Domain context:\n{business_context}\n")
    parts.extend([
        f"Database DSN: {dsn}",
        "",
        f"Question: {question}",
        "",
        "Connect to the DSN, explore the schema with the MCP tools, write the "
        "SQL that answers the question, run it, and give me the answer.",
    ])
    return "\n".join(parts)


def _mcp_config() -> McpStdioServerConfig:
    return McpStdioServerConfig(
        type="stdio",
        command=sys.executable,
        args=["-m", "tools.server"],
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )


async def run_task(
    question: str,
    dsn: str,
    model: str = "claude-sonnet-4-6",
    business_context: str | None = None,
    trace_path: Path | None = None,
    max_turns: int = 15,
) -> RunResult:
    """Run one analytics question through the Claude Agent SDK."""
    if trace_path is None:
        trace_path = REPO_ROOT / "runs" / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) / "run.jsonl"

    system_prompt = SYSTEM_PROMPT_PATH.read_text()
    user_prompt = _build_user_prompt(question, dsn, business_context)

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        mcp_servers={MCP_SERVER_NAME: _mcp_config()},
        allowed_tools=ALLOWED_TOOLS,
        model=model,
        max_turns=max_turns,
        permission_mode="bypassPermissions",
        cwd=str(REPO_ROOT),
        setting_sources=[],
    )

    last_text = ""
    final_result: ResultMessage | None = None
    num_turns = 0

    meta = {
        "task": "fde-analytics-query",
        "question": question,
        "dsn": dsn,
        "model": model,
        "adapter": "claude",
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    with open_trace(trace_path, meta=meta) as trace:
        trace.tool_call("user_question", {"question": question, "dsn": dsn})

        try:
            async for msg in query(prompt=user_prompt, options=options):
                if isinstance(msg, AssistantMessage):
                    num_turns += 1
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            trace.model_output({"text": block.text})
                            last_text = block.text  # keep only the most recent
                        elif isinstance(block, ToolUseBlock):
                            trace.tool_call(block.name, block.input)
                elif isinstance(msg, UserMessage):
                    for block in msg.content:
                        if isinstance(block, ToolResultBlock):
                            trace.tool_result(
                                block.tool_use_id,
                                {"content": block.content, "is_error": block.is_error},
                            )
                elif isinstance(msg, ResultMessage):
                    final_result = msg
        except Exception as e:
            trace.final(predicted_sql=None, success=False, error=f"sdk: {type(e).__name__}: {e}")
            return RunResult(
                answer=None, num_turns=num_turns, total_cost_usd=None,
                input_tokens=None, output_tokens=None, stop_reason=None,
                is_error=True, error=f"sdk: {type(e).__name__}: {e}",
                trace_path=trace_path,
            )

        usage = final_result.usage if final_result else None
        input_tokens = usage.get("input_tokens") if isinstance(usage, dict) else None
        output_tokens = usage.get("output_tokens") if isinstance(usage, dict) else None
        cost = final_result.total_cost_usd if final_result else None
        stop_reason = final_result.stop_reason if final_result else None
        is_error = bool(final_result and final_result.is_error)

        trace.final(
            predicted_sql=None,
            success=not is_error and bool(last_text),
            error=None if last_text else "no assistant text produced",
        )

    return RunResult(
        answer=last_text or None,
        num_turns=num_turns,
        total_cost_usd=cost,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        stop_reason=stop_reason,
        is_error=is_error,
        error=None if last_text else "no assistant text produced",
        trace_path=trace_path,
    )
