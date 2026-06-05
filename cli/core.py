"""Core shared utilities for ds-cli.

Includes seq_code arithmetic, database operations, formatting helpers,
and shared constants.
"""

from __future__ import annotations

import os
import sys
import sqlite3
import uuid as _uuid
import datetime
import json
import re

STATE_DIR = os.path.expanduser("~/.ds-cli")
DB_DIR = os.path.join(STATE_DIR, "runs")
DB_PATH = os.path.join(DB_DIR, "dscli.db")
TASKS_DIR = os.path.join(STATE_DIR, "tasks")
CCLEAN = os.path.expanduser("~/.local/bin/cclean")
_MAX_DAILY = 1035  # ZZ is max seq_code

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


# ── seq_code helpers ──────────────────────────────────────────────────────────


def counter_to_seq_code(n: int) -> str:
    """Convert 1-based daily counter to 2-char seq_code.

    1..99  → "01".."99"
    100+   → A0, A1..A9, AA..AZ, B0..ZZ
    Raises ValueError if n exceeds ZZ (1035).
    """
    if n < 1:
        raise ValueError(f"counter must be >= 1, got {n}")
    if n <= 99:
        return f"{n:02d}"
    val = n - 100  # 0-based offset from start of letter encoding
    if val >= 26 * 36:
        raise ValueError(f"counter too large, max {_MAX_DAILY} (ZZ), got {n}")
    first = chr(ord("A") + val // 36)
    r = val % 36
    second = chr(ord("0") + r) if r < 10 else chr(ord("A") + r - 10)
    return first + second


def seq_code_to_counter(code: str) -> int:
    """Inverse of counter_to_seq_code: '01' → 1, 'A0' → 100, 'ZZ' → 1035."""
    if len(code) != 2:
        raise ValueError(f"invalid seq_code length: {code!r}")
    if code.isdigit():
        return int(code)
    first, second = code[0], code[1]
    if not ("A" <= first <= "Z"):
        raise ValueError(f"invalid seq_code: {code!r}")
    first_idx = ord(first) - ord("A")
    if "0" <= second <= "9":
        second_idx = ord(second) - ord("0")
    elif "A" <= second <= "Z":
        second_idx = ord(second) - ord("A") + 10
    else:
        raise ValueError(f"invalid seq_code char: {second!r}")
    return 100 + first_idx * 36 + second_idx


# ── database ──────────────────────────────────────────────────────────────────


def get_db():
    """Open (or create) the SQLite database, return a connection with row_factory set."""
    os.makedirs(DB_DIR, exist_ok=True)
    os.makedirs(TASKS_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            seq         INTEGER NOT NULL,
            seq_code    TEXT NOT NULL,
            run_id      TEXT NOT NULL UNIQUE,
            run_day     TEXT NOT NULL,
            uuid        TEXT NOT NULL UNIQUE,
            cwd         TEXT NOT NULL,
            prompt      TEXT NOT NULL,
            jsonl_path  TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            status      TEXT DEFAULT 'running',
            backend     TEXT DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS run_counters (
            day     TEXT PRIMARY KEY,
            last_n  INTEGER NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_run_id   ON runs(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_seq      ON runs(seq)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_created  ON runs(created_at)")

    # Recreate schema if old table is missing new columns (e.g. reset not run)
    try:
        cursor = conn.execute("PRAGMA table_info(runs)")
        cols = {row[1] for row in cursor.fetchall()}
        missing = {"run_id", "seq_code", "run_day", "backend"} - cols
        if missing:
            print(
                f"ds-cli: schema missing columns {missing}; "
                f"run 'ds-cli/reset-state.sh' to reset",
                file=sys.stderr,
            )
            sys.exit(2)
    except sqlite3.Error:
        pass

    conn.commit()
    conn.row_factory = sqlite3.Row
    return conn


def create_run(conn: sqlite3.Connection, cwd: str, prompt_text: str, backend_name: str = ""):
    """Allocate a new run inside a BEGIN IMMEDIATE transaction.

    Assigns daily counter, seq_code, run_id, uuid, jsonl_path.
    Records the backend name used.
    Returns (run_id, uuid, jsonl_path).  Caller must commit/rollback.
    """
    conn.execute("BEGIN IMMEDIATE")
    today = datetime.date.today()
    today_iso = today.isoformat()
    mmdd = today.strftime("%m%d")

    row = conn.execute(
        "SELECT last_n FROM run_counters WHERE day = ?", (today_iso,)
    ).fetchone()
    n = (row[0] + 1) if row else 1

    if n > _MAX_DAILY:
        conn.execute("ROLLBACK")
        print("ds-cli: exceeded maximum daily run count (ZZ = 1035)", file=sys.stderr)
        sys.exit(2)

    conn.execute(
        "INSERT OR REPLACE INTO run_counters (day, last_n) VALUES (?, ?)",
        (today_iso, n),
    )

    seq_code = counter_to_seq_code(n)
    run_id = f"ds-{seq_code}-{mmdd}"
    uid = str(_uuid.uuid4()).lower()
    jsonl_path = os.path.join(DB_DIR, f"{run_id}-{uid}.jsonl")

    conn.execute(
        "INSERT INTO runs (seq, seq_code, run_id, run_day, uuid, cwd, prompt, jsonl_path, backend) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (n, seq_code, run_id, today_iso, uid, cwd, prompt_text, jsonl_path, backend_name),
    )
    return run_id, uid, jsonl_path


# ── helpers ───────────────────────────────────────────────────────────────────


def short_path(p):
    """Collapse $HOME to ~/."""
    home = os.path.expanduser("~")
    if p.startswith(home + "/"):
        return "~/" + p[len(home) + 1:]
    if p == home:
        return "~"
    return p


def prompt_prefix(prompt: str | None, width: int = 30) -> str:
    lines = [l for l in (prompt or "").splitlines() if l.strip()]
    first = lines[0].strip() if lines else ""
    return first[:width]


def format_run_row(row, full_cwd: bool = False) -> dict[str, str]:
    try:
        dt = datetime.datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
        if dt.date() == datetime.date.today():
            date_str = dt.strftime("%H:%M")
        else:
            date_str = dt.strftime("%m-%d %H:%M")
    except (ValueError, TypeError):
        date_str = row["created_at"] or "?"

    cwd = row["cwd"]
    cwd_disp = short_path(cwd) if full_cwd else (os.path.basename(cwd) or cwd)
    return {
        "id": row["run_id"],
        "date": date_str,
        "prompt": prompt_prefix(row["prompt"], 40),
        "cwd": cwd_disp,
        "uuid": row["uuid"],
        "status": row["status"],
        "backend": row_value(row, "backend", "") or "",
    }


def row_value(row, key: str, default=None):
    """Read key from sqlite3.Row/dict-like row without assuming dict.get()."""
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def progress_preview(line: str) -> str:
    """One-line preview from a stream-json line for progress display."""
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return ""
    t = obj.get("type")
    try:
        if t == "assistant":
            c0 = obj["message"]["content"][0]
            text = c0.get("text") or c0.get("input") or ""
            if not isinstance(text, str):
                text = json.dumps(text)
            return text[:10].replace("\n", " ").replace("\r", " ").replace("\t", " ")
        elif t == "user":
            text = obj["message"]["content"][0].get("content", "")
            if not isinstance(text, str):
                text = json.dumps(text)
            return text[:10].replace("\n", " ").replace("\r", " ").replace("\t", " ")
        elif t == "result":
            sub = obj.get("subtype", "success")
            if sub == "success" and not obj.get("is_error", False):
                return "DONE"
            return "ERROR"
        elif t == "system":
            return obj.get("subtype", "")
        elif t == "stream_event":
            return obj.get("event", {}).get("type", "")
    except (KeyError, IndexError, TypeError):
        pass
    return ""


def extract_result(jsonl_path: str):
    """Return the last successful result text from a JSONL file (or None)."""
    try:
        with open(jsonl_path, "r") as f:
            last = None
            for raw in f:
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") == "result":
                    if (
                        obj.get("subtype", "success") == "success"
                        and not obj.get("is_error", False)
                    ):
                        last = obj.get("result", "")
            return last
    except FileNotFoundError:
        return None


def resolve_jsonl(target: str, conn: sqlite3.Connection) -> str:
    """Turn user-supplied id / uuid / run_id / seq / *.jsonl into an absolute .jsonl path."""
    if target.endswith(".jsonl"):
        return target

    # run_id?
    row = conn.execute(
        "SELECT jsonl_path FROM runs WHERE run_id = ?", (target,)
    ).fetchone()
    if row:
        return row["jsonl_path"]

    # seq?
    try:
        seq = int(target)
    except ValueError:
        seq = None
    if seq is not None:
        row = conn.execute(
            "SELECT jsonl_path FROM runs WHERE seq = ? ORDER BY created_at DESC LIMIT 1",
            (seq,),
        ).fetchone()
        if row:
            return row["jsonl_path"]

    # uuid?
    row = conn.execute(
        "SELECT jsonl_path FROM runs WHERE uuid = ?", (target,)
    ).fetchone()
    if row:
        return row["jsonl_path"]

    return os.path.join(DB_DIR, f"{target}.jsonl")


def find_run(conn: sqlite3.Connection, selector: str | None):
    """Find a run by run_id, numeric seq, or latest."""
    if selector:
        row = conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (selector,)
        ).fetchone()
        if row:
            return row
        try:
            seq = int(selector)
        except ValueError:
            return None
        return conn.execute(
            "SELECT * FROM runs WHERE seq = ? ORDER BY created_at DESC LIMIT 1",
            (seq,),
        ).fetchone()

    return conn.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT 1").fetchone()


def task_paths(run_id: str):
    """Return (prompt, out, result) paths under TASKS_DIR using run_id as basename."""
    os.makedirs(TASKS_DIR, exist_ok=True)
    return (
        os.path.join(TASKS_DIR, f"{run_id}.prompt.txt"),
        os.path.join(TASKS_DIR, f"{run_id}.out.txt"),
        os.path.join(TASKS_DIR, f"{run_id}.result.md"),
    )
