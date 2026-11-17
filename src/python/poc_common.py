"""Shared helpers for the contoso-poc Python runners (settings, state, SQL templating and splitting)."""
from __future__ import annotations

import functools
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "state" / "outputs.json"

# Same isolated Azure CLI profile as the PowerShell scripts (scripts/common.ps1): Azure CLI credentials used by the
# Azure and Databricks SDKs come from the PoC profile, never from your other (for example work) sign-ins.
os.environ["AZURE_CONFIG_DIR"] = str(Path.home() / ".azure-contoso-thr985")

# The questions the Part B orchestrator (foundry/fdy.py) sends to the two Genie agents. Each one has a curated example
# SQL in databricks/setup_genie.py, so Genie answers it with that SQL: fast, and the same numbers every time.
GENIE_QUESTIONS = {
    "demand_forecast": "How did {promotion} do against forecast last week in my region, and which stores missed it?",
    "supply_chain": "Which late supplier deliveries hit {promotion} products last week, and how many of my stores ran out "
                    "while they were late?",
}


def settings() -> dict:
    path = ROOT / "config" / "settings.json"
    if not path.exists():
        sys.exit("config/settings.json not found - copy config/settings.example.json and fill it in.")
    return json.loads(path.read_text(encoding="utf-8-sig"))


@functools.cache
def assert_personal_tenant() -> None:
    """Stops unless the PoC Azure CLI profile is signed in to settings.tenantId. Called before any Azure access."""
    expected = settings().get("tenantId")
    if not expected:
        sys.exit("Set tenantId in config/settings.json to your PERSONAL Entra tenant ID.")
    cmd = ["az", "account", "show", "--query", "tenantId", "-o", "tsv", "--only-show-errors"]
    out = subprocess.run((["cmd", "/c"] if os.name == "nt" else []) + cmd, capture_output=True, text=True)
    current = out.stdout.strip()
    if not current:
        sys.exit("Not signed in to the PoC Azure CLI profile - run scripts/login.ps1 first.")
    if current != expected:
        sys.exit(f"The PoC Azure CLI profile is signed in to tenant {current}, not your personal tenant {expected}. "
                 "Run scripts/login.ps1.")


def state() -> dict:
    return json.loads(STATE_PATH.read_text(encoding="utf-8-sig")) if STATE_PATH.exists() else {}


def update_state(values: dict) -> None:
    current = state()
    current.update(values)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")


def names() -> dict:
    suffix = state().get("suffix")
    if not suffix:
        sys.exit("No suffix in state/outputs.json - run scripts/00-preflight.ps1 first.")
    return {k: v.replace("{suffix}", suffix) for k, v in settings()["names"].items()}


def answer_key() -> dict:
    """Expected demo answers; scripts/30-upload-landing.ps1 copies them next to the state file."""
    path = ROOT / "state" / "answer_key.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def demo_values() -> dict:
    """Demo week and promo id, taken from the answer key of the data that was actually uploaded."""
    from datetime import date, timedelta
    key, demo = answer_key(), settings()["demo"]
    start, end = key.get("demo_week") or [demo["weekStart"], demo["weekEnd"]]
    monday = date.fromisoformat(start)
    return {
        "DEMO_WEEK_START": start,
        "DEMO_WEEK_END": end,
        "PRIOR_4WK_START": (monday - timedelta(days=28)).isoformat(),
        "PROMO_ID": key.get("promo_id") or f"PR-{monday:%y%m%d}-HK",
        "DEMO_WEEK_LABEL": f"{monday:%b} {monday.day}-{date.fromisoformat(end).day}, {monday.year}",
    }


_VAR = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def render(sql: str, variables: dict) -> str:
    """Replaces {{NAME}} placeholders; fails loudly on any missing value."""
    missing = sorted({m for m in _VAR.findall(sql) if variables.get(m) in (None, "")})
    if missing:
        sys.exit(f"Missing values for: {', '.join(missing)} (fill config/settings.json or run the earlier steps).")
    return _VAR.sub(lambda m: str(variables[m.group(1)]), sql)


def split_sql(text: str) -> list[str]:
    """Splits a SQL script on ';' outside quotes, $$ blocks and comments. Comment-only chunks are dropped."""
    out, buf, i, n = [], [], 0, len(text)
    quote = None  # "'", '"', "$$", "--", "/*"
    while i < n:
        two = text[i:i + 2]
        ch = text[i]
        if quote is None:
            if two in ("$$", "--", "/*"):
                quote = two
                buf.append(two)
                i += 2
                continue
            if ch in ("'", '"'):
                quote = ch
            elif ch == ";":
                stmt = "".join(buf).strip()
                if _has_code(stmt):
                    out.append(stmt)
                buf, i = [], i + 1
                continue
        elif quote == "--" and ch == "\n":
            quote = None
        elif quote == "/*" and two == "*/":
            quote = None
            buf.append(two)
            i += 2
            continue
        elif quote == "$$" and two == "$$":
            quote = None
            buf.append(two)
            i += 2
            continue
        elif quote in ("'", '"') and ch == quote:
            if text[i + 1:i + 2] == quote:  # escaped quote
                buf.append(ch * 2)
                i += 2
                continue
            quote = None
        buf.append(ch)
        i += 1
    stmt = "".join(buf).strip()
    if _has_code(stmt):
        out.append(stmt)
    return out


def _has_code(stmt: str) -> bool:
    return bool(strip_comments(stmt))


def strip_comments(stmt: str) -> str:
    """Removes -- and /* */ comments (quote-aware) and surrounding whitespace - for display and statement-type checks."""
    out, i, n, quote = [], 0, len(stmt), None
    while i < n:
        two, ch = stmt[i:i + 2], stmt[i]
        if quote is None:
            if two == "--":
                j = stmt.find("\n", i)
                i = n if j < 0 else j
                continue
            if two == "/*":
                j = stmt.find("*/", i + 2)
                i = n if j < 0 else j + 2
                continue
            if two == "$$":
                quote = "$$"
                out.append(two)
                i += 2
                continue
            if ch in ("'", '"'):
                quote = ch
        elif quote == "$$" and two == "$$":
            quote = None
            out.append(two)
            i += 2
            continue
        elif quote in ("'", '"') and ch == quote:
            if stmt[i + 1:i + 2] == quote:
                out.append(ch * 2)
                i += 2
                continue
            quote = None
        out.append(ch)
        i += 1
    return "".join(out).strip()


def sql_files(folder: Path, only: list[str] | None, start: str | None) -> list[Path]:
    files = sorted(folder.glob("*.sql"))
    if only:
        files = [f for f in files if any(f.name.startswith(o) for o in only)]
    if start:
        files = [f for f in files if f.name >= start]
    return files


def banner(msg: str) -> None:
    print(f"\n==> {msg}", flush=True)
