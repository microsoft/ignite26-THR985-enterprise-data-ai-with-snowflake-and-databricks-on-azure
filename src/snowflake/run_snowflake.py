#!/usr/bin/env python3
"""Runs the Snowflake SQL files in order (each file also opens as-is in a Snowsight worksheet once rendered).

  python snowflake/run_snowflake.py --only 00 10        # files whose names start with 00 and 10
  python snowflake/run_snowflake.py --from 20           # 20_... onwards
  python snowflake/run_snowflake.py --only 70 --dry-run # print the rendered SQL, run nothing

{{PLACEHOLDERS}} are filled from config/settings.json and state/outputs.json. Files with a "-- @requires NAME[, NAME]"
header are skipped (with a notice) until those values exist - for example the Snowflake OAuth fallback, which needs
the redirect URL Foundry shows. Stops at the first error and tells you how to resume.
"""
import argparse
import re
import sys
from pathlib import Path

import sf

HERE = Path(__file__).resolve().parent
pc = sf.pc
SHOW_ROWS = ("SHOW", "DESC", "DESCRIBE", "SELECT", "LIST", "CALL", "WITH")
MAX_ROWS = 60
REQUIRES = re.compile(r"^--\s*@requires\s+(.+)$", re.M)


def missing_requirements(text: str, variables: dict) -> list[str]:
    names = [n.strip() for m in REQUIRES.findall(text) for n in m.split(",") if n.strip()]
    return [n for n in names if variables.get(n) in (None, "")]


def resume_args(only: list[str] | None, files: list[Path], failed: Path) -> str:
    """Resume at the failed file without widening the selection: after --only, --from would also run every later file."""
    if only:
        return "--only " + " ".join(f.name[:2] for f in files[files.index(failed):])
    return f"--from {failed.name[:2]}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help="file name prefixes to run")
    ap.add_argument("--from", dest="start", help="run this file and everything after it")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    files = pc.sql_files(HERE / "sql", args.only, args.start)
    if not files:
        sys.exit("No matching SQL files.")
    variables = sf.variables()
    rendered = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        missing = missing_requirements(text, variables)
        if missing:
            print(f"--  skipping {f.name}: needs {', '.join(missing)}")
            continue
        rendered.append((f, pc.split_sql(pc.render(text, variables))))
    if args.dry_run:
        for f, stmts in rendered:
            pc.banner(f.name)
            print(";\n\n".join(stmts) + ";")
        return

    conn = sf.connect()
    cur = conn.cursor()
    try:
        for f, stmts in rendered:
            pc.banner(f"{f.name} ({len(stmts)} statements)")
            for i, stmt in enumerate(stmts, 1):
                code = pc.strip_comments(stmt)
                head = " ".join(code.split())[:110]
                try:
                    cur.execute(stmt)
                except Exception as e:  # noqa: BLE001
                    if "@may-fail" in stmt:
                        print(f"  [{i}] allowed to fail: {head}\n      {str(e).splitlines()[0]}")
                        continue
                    print(f"  [{i}] FAILED: {head}\n      {e}")
                    sys.exit("\nFix the issue, then resume with: python snowflake/run_snowflake.py "
                             + resume_args(args.only, files, f))
                print(f"  [{i}] {head}")
                if code.upper().startswith(SHOW_ROWS) and cur.description:
                    cols = [c[0] for c in cur.description]
                    for row in cur.fetchmany(MAX_ROWS):
                        print("      " + " | ".join(f"{c}={v}" for c, v in zip(cols, row))[:300])
    finally:
        cur.close()
        conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
