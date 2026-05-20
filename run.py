"""FDE agent starter — single-question runner.

Ask one question against one database from the command line. Writes a JSONL
trace under `runs/<timestamp>/`.

Usage:
    python run.py "Which customers had purchase events this month?" \\
        --dsn sqlite:///demo.db

    python run.py "..." --dsn sqlite:///demo.db --model claude-sonnet-4-6 \\
        --business-context business_context.md
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from adapters.claude import run_task


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("question", help="natural-language question for the agent")
    p.add_argument("--dsn", required=True,
                   help="SQLAlchemy DSN, e.g. sqlite:///demo.db")
    p.add_argument("--model", default="claude-sonnet-4-6")
    p.add_argument("--max-turns", type=int, default=15)
    p.add_argument(
        "--business-context", type=Path, default=None,
        help="path to a markdown file with customer-specific domain context "
             "(column meanings, business rules, vocabulary)",
    )
    p.add_argument(
        "--trace-path", type=Path, default=None,
        help="override JSONL trace location",
    )
    return p.parse_args()


async def main_async() -> int:
    args = parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 2

    business_context = None
    if args.business_context:
        if not args.business_context.exists():
            print(f"ERROR: --business-context file not found: {args.business_context}",
                  file=sys.stderr)
            return 2
        business_context = args.business_context.read_text()

    result = await run_task(
        question=args.question,
        dsn=args.dsn,
        model=args.model,
        business_context=business_context,
        trace_path=args.trace_path,
        max_turns=args.max_turns,
    )

    print()
    print("=" * 70)
    if result.is_error:
        print(f"ERROR: {result.error}")
        print(f"trace → {result.trace_path}")
        return 1

    print(result.answer or "(no answer produced)")
    print("=" * 70)
    print(f"turns: {result.num_turns}  "
          f"tokens: in={result.input_tokens} out={result.output_tokens}  "
          f"cost: ${result.total_cost_usd or 0:.4f}")
    print(f"trace → {result.trace_path}")
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
