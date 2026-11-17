#!/usr/bin/env python3
"""Reads the Azure VNet subnets Snowflake uses to reach your storage (SYSTEM$GET_SNOWFLAKE_PLATFORM_INFO) and saves
them to state/outputs.json (snowflakeSubnetIds) for scripts/90-lockdown-storage.ps1."""
import json

import sf

pc = sf.pc


def main() -> None:
    conn = sf.connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT SYSTEM$GET_SNOWFLAKE_PLATFORM_INFO()")
        info = json.loads(cur.fetchone()[0])
    finally:
        conn.close()
    subnets = sorted({s for k, v in info.items() if "subnet" in k.lower() for s in (v if isinstance(v, list) else [v])})
    if not subnets:
        raise SystemExit(f"No subnet IDs in the platform info: {json.dumps(info)[:400]}")
    pc.update_state({"snowflakeSubnetIds": subnets})
    for s in subnets:
        print(f"    {s}")
    print("Saved to state/outputs.json - next: scripts/90-lockdown-storage.ps1")


if __name__ == "__main__":
    main()
