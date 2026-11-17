#!/usr/bin/env python3
"""Databricks step D2 - account level (you are the first account admin as the tenant's Global Administrator):

  * brings the Entra region groups, the HQ group, the data-admins group and Ava / Ben / Cara into the Databricks
    account with automatic identity management (resolved by Entra object ID - no SCIM app, memberships stay in Entra)
  * gives the reader groups USER access to the workspace with the consumer access entitlement (Genie and MCP only)
  * creates a notify-only budget (email at 50/80/100% - nothing is stopped)

  python databricks/setup_account.py
"""
import sys

import dbx
from databricks.sdk.errors import DatabricksError
from databricks.sdk.service import billing, iam

pc = dbx.pc
BUDGET_NAME = "contoso-thr985"


def resolve_identities(w) -> dict:
    st = pc.state()
    if not st.get("entraGroups"):
        sys.exit("Run scripts/40-entra-identity.ps1 first.")
    groups = {}
    try:
        for region, object_id in st["entraGroups"].items():
            groups[region] = w.workspace_iam_v2.resolve_group_proxy(external_id=object_id).group
            print(f"    group {groups[region].group_name} -> Databricks id {groups[region].group_id}")
        admins = w.workspace_iam_v2.resolve_group_proxy(external_id=st["entraAdminGroupId"]).group
        print(f"    group {admins.group_name} -> Databricks id {admins.group_id}")
        for alias, u in st["entraUsers"].items():
            user = w.workspace_iam_v2.resolve_user_proxy(external_id=u["objectId"]).user
            print(f"    user {user.username} -> Databricks id {user.user_id}")
    except DatabricksError as e:
        sys.exit(f"Resolving Entra identities failed: {e}\n"
                 "Automatic identity management must be on (default for accounts created after Aug 1, 2025): "
                 "account console > Settings > User provisioning > Automatic identity management. Then re-run.")
    return groups


def assign_workspace(a, groups: dict) -> None:
    ws_id = int(pc.state()["databricksWorkspaceNumericId"])
    for region, g in groups.items():
        a.workspace_assignment.update(workspace_id=ws_id, principal_id=int(g.group_id),
                                      permissions=[iam.WorkspacePermission.USER])
        print(f"    {g.group_name}: USER on workspace {ws_id}")


def grant_consumer_access(w, groups: dict) -> None:
    """Since the 2026 entitlement change (enforced Sep 14, 2026) a workspace assignment grants no entitlements and the
    'users' group has none to inherit. A user without an access entitlement gets 403 on every workspace API, the Genie
    MCP endpoints included. Consumer access is the smallest one: Genie agents and MCP tools, no notebooks or SQL editor."""
    for g in groups.values():
        have = {e.value for e in (w.groups.get(str(g.group_id)).entitlements or [])}
        if "workspace-consume" not in have:
            w.groups.patch(str(g.group_id),
                           operations=[iam.Patch(op=iam.PatchOp.ADD, path="entitlements",
                                                 value=[{"value": "workspace-consume"}])],
                           schemas=[iam.PatchSchema.URN_IETF_PARAMS_SCIM_API_MESSAGES_2_0_PATCH_OP])
        print(f"    {g.group_name}: consumer access")


def ensure_budget(a) -> None:
    s = pc.settings()
    amount = float(s["budget"]["databricksMonthlyUsd"])
    email = s["budget"]["alertEmail"] or pc.state()["userUpn"]
    if any(b.display_name == BUDGET_NAME for b in a.budgets.list()):
        print(f"    budget {BUDGET_NAME} exists")
        return
    alerts = [billing.CreateBudgetConfigurationBudgetAlertConfigurations(
        time_period=billing.AlertConfigurationTimePeriod.MONTH,
        quantity_type=billing.AlertConfigurationQuantityType.LIST_PRICE_DOLLARS_USD,
        trigger_type=billing.AlertConfigurationTriggerType.CUMULATIVE_SPENDING_EXCEEDED,
        quantity_threshold=str(round(amount * pct / 100)),
        action_configurations=[billing.CreateBudgetConfigurationBudgetActionConfigurations(
            action_type=billing.ActionConfigurationType.EMAIL_NOTIFICATION, target=email)])
        for pct in (50, 80, 100)]
    a.budgets.create(budget=billing.CreateBudgetConfigurationBudget(display_name=BUDGET_NAME,
                                                                    alert_configurations=alerts))
    print(f"    budget {BUDGET_NAME}: ${amount:.0f}/month, emails to {email} at 50/80/100% (alerts only)")


def main() -> None:
    w, a = dbx.workspace(), dbx.account()
    pc.banner("Entra identities -> Databricks (automatic identity management)")
    groups = resolve_identities(w)
    pc.banner("Workspace access for the demo groups")
    assign_workspace(a, groups)
    grant_consumer_access(w, groups)
    pc.update_state({"databricksGroups": {k: g.group_name for k, g in groups.items()}})
    pc.banner("Budget")
    ensure_budget(a)
    print("\nNext: python databricks/run_databricks.py   (catalogs, bronze/silver/gold, row filters, grants)")


if __name__ == "__main__":
    main()
