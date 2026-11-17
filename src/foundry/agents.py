#!/usr/bin/env python3
"""Foundry step F3 - creates (a new version of) every agent whose MCP servers and Foundry connections already exist,
all on the pinned model deployment (settings.foundry). Each MCP tool is bound to its custom-OAuth project connection (OAuth
identity passthrough: every tool call runs as the person chatting, so Snowflake row access and Databricks row
filters apply per person). Agents that aren't ready yet are skipped with the reason.

  contoso-orchestrator-a   Part A / S5, design A: semantic view + read-only SQL     } ready at the Snowflake
  contoso-orchestrator-b   Part A / S5, design B: the Commercial Analyst agent      } checkpoint (README phase 5)
  contoso-orchestrator     Part B: commercial + loyalty (Snowflake), demand forecast + supply chain (Databricks)
                           - ready after Databricks (README phase 7)

  python foundry/agents.py                              # everything that is ready
  python foundry/agents.py --only contoso-orchestrator-b
"""
import argparse
import sys

import fdy
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (AgentEndpointConfig, FixedRatioVersionSelectionRule, PromptAgentDefinition,
                                      ProtocolConfiguration, Reasoning, ResponsesProtocolConfiguration,
                                      VersionSelector)
from azure.identity import AzureCliCredential

pc = fdy.pc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help="agent names to (re)create")
    args = ap.parse_args()
    v = pc.demo_values()
    deployment = pc.state().get("foundryDeployment") or pc.settings()["foundry"]["deploymentName"]
    created, skipped = [], []

    with AzureCliCredential() as cred, AIProjectClient(endpoint=fdy.endpoint(), credential=cred) as project:
        for name, spec in fdy.agent_definitions(v).items():
            if args.only and name not in args.only:
                continue
            try:
                tools = [fdy.mcp_tool(project, key) for key in spec["tools"]]
            except fdy.NotReady as e:
                skipped.append(name)
                print(f"    {name}: skipped - {e}")
                continue
            reasoning = {"reasoning": Reasoning(effort=spec["reasoning"])} if spec.get("reasoning") else {}
            version = project.agents.create_version(
                agent_name=name, description=spec["description"],
                definition=PromptAgentDefinition(model=deployment, instructions=spec["instructions"], tools=tools,
                                                 **reasoning))
            # Point the agent's endpoint at the new version (same pattern as the SDK samples).
            project.agents.update_details(agent_name=name, agent_endpoint=AgentEndpointConfig(
                version_selector=VersionSelector(version_selection_rules=[
                    FixedRatioVersionSelectionRule(agent_version=version.version, traffic_percentage=100)]),
                protocol_configuration=ProtocolConfiguration(responses=ResponsesProtocolConfiguration())))
            created.append(name)
            print(f"    {name}: version {version.version} live - tools {', '.join(t.server_label for t in tools)}")

    if not created or (args.only and skipped):
        sys.exit(f"\nNot created: {', '.join(skipped) or 'nothing matched --only'}")
    genie_ready = bool(pc.state().get("databricksGenie"))
    if fdy.ORCHESTRATOR in created:
        print("\nNext: python foundry/chat.py --as ava   (Demo 2 Part B; then --as ben and --as cara)")
    elif fdy.ORCHESTRATOR in skipped and genie_ready:
        print("\nNext: create the two Genie OAuth connections (README phase 7, step F2), then run this again.")
    elif not genie_ready:
        print("\nNext (Snowflake checkpoint): python foundry/chat.py --as ava, then --as ben   (spike S2, design B)")
    print("The first run per person and connection prints an OAuth consent link.")


if __name__ == "__main__":
    main()
