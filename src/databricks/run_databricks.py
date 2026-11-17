#!/usr/bin/env python3
"""Runs the Databricks SQL files in order on the serverless SQL warehouse (Statement Execution API, Azure CLI auth).
Each file also opens as-is in the Databricks SQL editor once rendered.

  python databricks/run_databricks.py                  # all files
  python databricks/run_databricks.py --from 30        # 30_... onwards
  python databricks/run_databricks.py --only 40 --dry-run

{{PLACEHOLDERS}} come from config/settings.json and state/outputs.json. "-- @requires NAME" skips a file until the
value exists; "-- @may-fail" before a statement tolerates its failure. Stops at the first error.
"""
import argparse
import re
import sys
from pathlib import Path

import dbx

HERE = Path(__file__).resolve().parent
pc = dbx.pc
SHOW_ROWS = ("SHOW", "DESC", "DESCRIBE", "SELECT", "LIST", "WITH")
REQUIRES = re.compile(r"^--\s*@requires\s+(.+)$", re.M)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help="file name prefixes to run")
    ap.add_argument("--from", dest="start", help="run this file and everything after it")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    files = pc.sql_files(HERE / "sql", args.only, args.start)
    if not files:
        sys.exit("No matching SQL files.")
    variables = dbx.variables()
    rendered = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        needed = [n.strip() for m in REQUIRES.findall(text) for n in m.split(",") if n.strip()]
        missing = [n for n in needed if variables.get(n) in (None, "")]
        if missing:
            print(f"--  skipping {f.name}: needs {', '.join(missing)}")
            continue
        rendered.append((f, pc.split_sql(pc.render(text, variables))))
    if args.dry_run:
        for f, stmts in rendered:
            pc.banner(f.name)
            print(";\n\n".join(stmts) + ";")
        return

    w, wid = dbx.workspace(), dbx.warehouse_id()
    for f, stmts in rendered:
        pc.banner(f"{f.name} ({len(stmts)} statements)")
        for i, stmt in enumerate(stmts, 1):
            code = pc.strip_comments(stmt)
            head = " ".join(code.split())[:110]
            try:
                cols, data = dbx.run_sql(w, code, wid)
            except Exception as e:  # noqa: BLE001
                if "@may-fail" in stmt:
                    print(f"  [{i}] allowed to fail: {head}\n      {str(e).splitlines()[0][:200]}")
                    continue
                print(f"  [{i}] FAILED: {head}\n      {e}")
                sys.exit(f"\nFix the issue, then resume with: python databricks/run_databricks.py --from {f.name[:2]}")
            print(f"  [{i}] {head}")
            if code.upper().startswith(SHOW_ROWS) and cols:
                for row in data[:40]:
                    print("      " + " | ".join(f"{c}={v}" for c, v in zip(cols, row))[:300])
    print("\nDone.")


if __name__ == "__main__":
    main()
