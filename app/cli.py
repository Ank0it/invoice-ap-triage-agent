"""CLI entry point for invoice processing."""

import argparse
import json
import os
import sys

from app.agent.llm_client import get_llm_client
from app.agent.llm_orchestrator import LLMInvoiceAgent
from app.agent.orchestrator import InvoiceAgent
from app.models.decision import DecisionResult


def main(argv=None):
    parser = argparse.ArgumentParser(description="Invoice Intake Agent CLI")
    parser.add_argument("document", help="Path to the invoice document (PDF or image)")
    parser.add_argument("--instruction", help="Optional user instruction", default=None)
    parser.add_argument("--json", action="store_true", help="Output result as JSON")
    parser.add_argument("--mode", choices=["deterministic", "llm"], default=None,
                        help="Agent mode: deterministic (default) or llm")
    args = parser.parse_args(argv)

    agent_mode = args.mode or os.environ.get("AGENT_MODE", "deterministic")
    if agent_mode == "llm":
        llm_client = get_llm_client("llm")
        agent = LLMInvoiceAgent(llm_client=llm_client)
    else:
        agent = InvoiceAgent()

    try:
        result: DecisionResult = agent.process(args.document, args.instruction)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result.model_dump(), indent=2, default=str))
    else:
        print(f"Status: {result.status.value}")
        print(f"Message: {result.message}")
        if result.reason_codes:
            print(f"Reasons: {', '.join(c.value for c in result.reason_codes)}")
        if result.tool_trace:
            print("Tool trace:")
            for t in result.tool_trace:
                print(f"  {t.step}. {t.tool} -> success={t.success} ({t.duration_ms}ms)")


if __name__ == "__main__":
    main()
