#!/usr/bin/env python3
"""Ask an agent a question as a demo person - the same path as the Foundry playground: the agent calls the MCP
servers with OAuth identity passthrough, so each person gets only their data. Also the demo's command-line backup.

  python foundry/chat.py --as ava                       # the Demo 2 question to the default agent (below)
  python foundry/chat.py --as ben "How did Holiday Kickoff do last week in my region, and why?"
  python foundry/chat.py --as cara --agent contoso-orchestrator-a "Holiday Kickoff units and net sales by region"
  python foundry/chat.py --as ben --check               # pre-flight: every MCP server lists tools for Ben (cheap)

Default agent: design B (contoso-orchestrator-b, Snowflake only) at the Snowflake checkpoint; contoso-orchestrator
once Databricks is built. The first run per person and MCP connection prints a consent link: open it in a private
window signed in as that person, accept, then press Enter here (one link at a time - a person new to the
orchestrator gets up to four in a row). The first run per person also opens a browser sign-in; it is cached
afterwards (state/auth/<person>.json - delete it to sign in again).
"""
import argparse
import json

import fdy
import openai
from azure.ai.projects import AIProjectClient

pc = fdy.pc
DEMO_QUESTION = "How did Holiday Kickoff do last week in my region, and why?"
CHECK_PROMPT = "Reply with the single word OK. Don't call any tool."


def consent(links: list[str]) -> None:
    print("\nOAuth consent needed (once per person and MCP connection):")
    for link in links:
        print(f"  {link}")
    try:
        input("Open each link signed in as this person, accept, then press Enter... ")
    except EOFError:  # not run from a terminal
        raise SystemExit("Open the link above signed in as this person, accept, then run this again.") from None


def genie_status(output: str) -> str:
    """Genie MCP results are JSON with a status (ASKING_AI, EXECUTING_QUERY, COMPLETED, ...); other tools return ''."""
    try:
        status = json.loads(output).get("status")
    except (ValueError, AttributeError):
        return ""
    return f", {status}" if isinstance(status, str) else ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--as", dest="persona", default="ava", choices=["ava", "ben", "cara", "me"])
    ap.add_argument("--agent", choices=[fdy.ORCHESTRATOR, fdy.DESIGN_A, fdy.DESIGN_B],
                    help="default: contoso-orchestrator once Databricks is built, otherwise design B")
    ap.add_argument("--show-payloads", action="store_true", help="print each MCP call's full output")
    ap.add_argument("--check", action="store_true",
                    help="only check that every MCP server lists its tools for this person (walks through any missing "
                         "consents; no data questions are asked) - run it for each person before a demo")
    ap.add_argument("question", nargs="?", default=DEMO_QUESTION)
    args = ap.parse_args()
    args.agent = args.agent or fdy.default_agent()

    cred = fdy.persona_credential(args.persona)
    try:
        with AIProjectClient(endpoint=fdy.endpoint(), credential=cred) as project, \
                project.get_openai_client(agent_name=args.agent) as client:
            r = fdy.ask(client, CHECK_PROMPT if args.check else args.question, on_consent=consent)
    except openai.APIStatusError as e:  # for example an MCP server that refuses this person, or a blocked agent
        detail = e.body.get("message") if isinstance(e.body, dict) else str(e)
        pc.banner(f"{args.agent} as {args.persona}: Foundry stopped the run (HTTP {e.status_code})")
        print(detail)
        raise SystemExit(1) from None

    if args.check:
        pc.banner(f"{args.agent} as {args.persona}: MCP servers and their tools")
        for i in r["raw"].output:
            if getattr(i, "type", "") == "mcp_list_tools":
                print(f"  {i.server_label:<26} {len(i.tools or [])} tools" + (f"  ERROR {i.error}" if i.error else ""))
        print("\n  " + ("READY - every server lists its tools." if not r["list_errors"] else
                        "NOT READY - " + "; ".join(r["list_errors"])))
        return

    pc.banner(f"{args.agent} as {args.persona}: {args.question}")
    print(r["answer"])
    pc.banner("Trace")
    for e in r["list_errors"]:
        print(f"  ! {e}")
    for c in r["calls"]:
        status = f"ERROR {c['error']}" if c["error"] else f"{len(c['output']):,} chars back{genie_status(c['output'])}"
        print(f"  {c['server']}/{c['tool']}  args {len(c['arguments']):,} chars  ->  {status}")
        if args.show_payloads:
            print("    " + json.dumps(c["output"])[:4000])
    saved = pc.ROOT / "state" / "chat" / f"{r['response_id']}.json"
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_text(r["raw"].model_dump_json(indent=2), encoding="utf-8")
    print(f"\n  {r['latency_s']:.1f} s · Foundry tokens in/out/total: {r['input_tokens']}/{r['output_tokens']}/"
          f"{r['total_tokens']} · {len(r['calls'])} MCP calls · response {r['response_id']}")
    print(f"  full response: {saved.relative_to(pc.ROOT)}")


if __name__ == "__main__":
    main()
