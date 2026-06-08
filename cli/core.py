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
import re
from typing import Optional

STATE_DIR = os.path.expanduser("~/.ds-cli")
DB_DIR = os.path.join(STATE_DIR, "runs")
DB_PATH = os.path.join(DB_DIR, "dscli.db")
TASKS_DIR = os.path.join(STATE_DIR, "tasks")
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
            session_id  TEXT,
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
        # In-place migration: add session_id and backfill from uuid for old rows.
        if "session_id" not in cols:
            conn.execute("ALTER TABLE runs ADD COLUMN session_id TEXT")
            conn.execute(
                "UPDATE runs SET session_id = uuid WHERE session_id IS NULL OR session_id = ''"
            )
            cols.add("session_id")
        missing = {"run_id", "seq_code", "run_day", "backend"} - cols
        if missing:
            print(
                f"ds-cli: schema missing columns {missing}; "
                f"delete ~/.ds-cli/runs/dscli.db and retry",
                file=sys.stderr,
            )
            sys.exit(2)
    except sqlite3.Error:
        pass

    conn.commit()
    conn.row_factory = sqlite3.Row
    return conn


def create_run(
    conn: sqlite3.Connection,
    cwd: str,
    prompt_text: str,
    backend_name: str = "",
    session_id: Optional[str] = None,
):
    """Allocate a new run inside a BEGIN IMMEDIATE transaction.

    Assigns daily counter, seq_code, run_id, uuid, jsonl_path.
    Records the backend name used.

    `session_id` is the underlying claude session to associate this run with.
    For a fresh run it is None and defaults to the row's own uuid. For a
    `resume` continuation it is the parent conversation's session_id, so the new
    row (new run_id/seq/files) shares one claude session across turns.

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
    run_id = f"ds-{mmdd}-{seq_code}"
    uid = str(_uuid.uuid4()).lower()
    sess = session_id or uid
    jsonl_path = os.path.join(DB_DIR, f"{run_id}-{uid}.jsonl")

    conn.execute(
        "INSERT INTO runs (seq, seq_code, run_id, run_day, uuid, session_id, cwd, prompt, jsonl_path, backend) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (n, seq_code, run_id, today_iso, uid, sess, cwd, prompt_text, jsonl_path, backend_name),
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


def prompt_prefix(prompt: Optional[str], width: int = 30) -> str:
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


def find_run(conn: sqlite3.Connection, selector: Optional[str]):
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
