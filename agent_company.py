#!/usr/bin/env python3
"""Local-first multi-model task orchestrator. Standard library only."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get("AGENT_DB", str(ROOT / "agent_tasks.sqlite3")))
REVIEW_REQUIRED = True

def now():
    return datetime.now(timezone.utc).isoformat()

def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=15000")
    return db

def init():
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS tasks (
          id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT NOT NULL,
          backend TEXT NOT NULL, prompt TEXT NOT NULL, workspace TEXT,
          status TEXT NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0,
          max_attempts INTEGER NOT NULL DEFAULT 3, result TEXT,
          error TEXT, next_run REAL NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER,
          at TEXT NOT NULL, event TEXT NOT NULL, detail TEXT NOT NULL)""")

def event(db, task_id, kind, detail=""):
    db.execute("INSERT INTO events(task_id,at,event,detail) VALUES(?,?,?,?)",
               (task_id, now(), kind, str(detail)[:3000]))

def add(role, backend, prompt, workspace=None):
    if backend not in ("mock", "openai", "claude", "muse"):
        raise ValueError("Backend must be mock/openai/claude/muse")
    if backend == "muse" and not workspace:
        raise ValueError("Muse requires an explicit isolated workspace")
    with connect() as db:
        cur = db.execute("""INSERT INTO tasks(role,backend,prompt,workspace,created_at,updated_at)
                            VALUES(?,?,?,?,?,?)""",
                         (role, backend, prompt, workspace, now(), now()))
        event(db, cur.lastrowid, "queued")
        return cur.lastrowid

def api_json(url, headers, payload):
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type":"application/json", **headers}, method="POST")
    with urlopen(req, timeout=120) as response:
        return json.load(response)

def execute(task):
    backend = task["backend"]
    prompt = task["prompt"]
    if backend == "mock":
        return "[MOCK] Completed: " + prompt[:500]
    if backend == "openai":
        key, model = os.getenv("OPENAI_API_KEY"), os.getenv("OPENAI_MODEL")
        if not key or not model:
            raise RuntimeError("Set OPENAI_API_KEY and OPENAI_MODEL")
        data = api_json("https://api.openai.com/v1/responses",
                        {"Authorization": "Bearer " + key},
                        {"model": model, "input": prompt})
        parts = [p.get("text", "") for o in data.get("output", [])
                 for p in o.get("content", []) if p.get("type") == "output_text"]
        if not parts:
            raise RuntimeError("OpenAI returned no output_text; inspect response via provider logs")
        return "\n".join(parts)
    if backend == "claude":
        key, model = os.getenv("ANTHROPIC_API_KEY"), os.getenv("ANTHROPIC_MODEL")
        if not key or not model:
            raise RuntimeError("Set ANTHROPIC_API_KEY and ANTHROPIC_MODEL")
        data = api_json("https://api.anthropic.com/v1/messages",
                        {"x-api-key": key, "anthropic-version": "2023-06-01"},
                        {"model": model, "max_tokens": 1600,
                         "messages": [{"role": "user", "content": prompt}]})
        parts = [p.get("text", "") for p in data.get("content", []) if p.get("type") == "text"]
        if not parts:
            raise RuntimeError("Claude returned no text content")
        return "\n".join(parts)
    if backend == "muse":
        workspace = Path(task["workspace"] or "").expanduser().resolve()
        if not workspace.is_dir() or not (workspace / ".git").exists():
            raise RuntimeError("Muse workspace must be an existing isolated Git worktree/repository")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8") as fh:
            fh.write(prompt + "\n\nDo not push, merge, publish, deploy, or access credentials.")
            fh.flush()
            proc = subprocess.run(["muse", "exec", "--prompt-file", fh.name],
                                  cwd=workspace, capture_output=True, text=True, timeout=900,
                                  check=False)
        if proc.returncode:
            raise RuntimeError(("Muse exit " + str(proc.returncode) + ": " + proc.stderr)[-1200:])
        return (proc.stdout or "(Muse exited with no stdout; verify workspace changes and tests)")[-15000:]
    raise ValueError("Unknown backend")

def run_once():
    init()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("""SELECT * FROM tasks WHERE status IN ('queued','retry')
                            AND next_run<=? ORDER BY id LIMIT 1""", (time.time(),)).fetchone()
        if not row:
            print("No runnable tasks")
            return None
        task = dict(row)
        db.execute("UPDATE tasks SET status='running',attempts=attempts+1,updated_at=? WHERE id=?",
                   (now(), task["id"]))
        event(db, task["id"], "running", "attempt " + str(task["attempts"] + 1))
    try:
        result = execute(task)
        with connect() as db:
            db.execute("UPDATE tasks SET status='review',result=?,error=NULL,updated_at=? WHERE id=?",
                       (result[:50000], now(), task["id"]))
            event(db, task["id"], "review", "Awaiting human verification")
        print("Task", task["id"], "awaiting review")
    except Exception as ex:
        attempts = task["attempts"] + 1
        status = "failed" if attempts >= task["max_attempts"] else "retry"
        # Exponential backoff caps at 1 hour.
        next_run = time.time() + min(3600, 30 * 2 ** (attempts - 1))
        with connect() as db:
            db.execute("""UPDATE tasks SET status=?, error=?, next_run=?,updated_at=? WHERE id=?""",
                       (status, str(ex)[:3000], next_run, now(), task["id"]))
            event(db, task["id"], status, type(ex).__name__)
        print("Task", task["id"], status, file=sys.stderr)
    return task["id"]

def list_tasks():
    init()
    with connect() as db:
        return [dict(x) for x in db.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT 200")]

def approve(task_id):
    with connect() as db:
        cur = db.execute("UPDATE tasks SET status='done',updated_at=? WHERE id=? AND status='review'",
                         (now(), task_id))
        if cur.rowcount != 1:
            raise ValueError("Task must exist and be in review status")
        event(db, task_id, "approved", "Human approval via CLI")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/tasks":
            payload = json.dumps([{
                "id": t["id"], "role": t["role"], "backend": t["backend"],
                "status": t["status"], "attempts": t["attempts"],
                "updated_at": t["updated_at"]
            } for t in list_tasks()]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
        elif self.path in ("/", "/index.html"):
            payload = (ROOT / "web" / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_error(404)

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    a = sub.add_parser("add")
    a.add_argument("--role", required=True)
    a.add_argument("--backend", choices=["mock","openai","claude","muse"], default="mock")
    a.add_argument("--prompt", required=True)
    a.add_argument("--workspace")
    sub.add_parser("run-once")
    sub.add_parser("list")
    s = sub.add_parser("show"); s.add_argument("id", type=int)
    ap = sub.add_parser("approve"); ap.add_argument("id", type=int)
    sub.add_parser("serve")
    args = parser.parse_args()
    init()
    if args.command == "init":
        print("Initialized", DB)
    elif args.command == "add":
        print("Created task", add(args.role, args.backend, args.prompt, args.workspace))
    elif args.command == "run-once":
        run_once()
    elif args.command == "list":
        for t in list_tasks():
            print(t["id"], t["status"], t["backend"], t["role"])
    elif args.command == "show":
        with connect() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (args.id,)).fetchone()
            print(json.dumps(dict(row) if row else None, indent=2, ensure_ascii=False))
    elif args.command == "approve":
        approve(args.id); print("Approved", args.id)
    elif args.command == "serve":
        print("Dashboard: http://127.0.0.1:8765")
        ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()

if __name__ == "__main__":
    main()
