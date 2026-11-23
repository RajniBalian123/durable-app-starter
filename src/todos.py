"""Todo list + agent turns, both built on durable workflows.

Adding a todo and enqueueing its workflow commit in one transaction.
An agent turn is a workflow with recorded steps, so a crash resumes it
instead of repeating it.
"""
from __future__ import annotations

import sqlite3

from .queue import DurableQueue

AGENT_STEPS = ["read", "plan", "act", "reply"]


class TodoApp:
    def __init__(self, path: str = ":memory:"):
        self.queue = DurableQueue(path)
        self.conn = self.queue.conn
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY, title TEXT, done INTEGER DEFAULT 0);
        """)
        self.conn.commit()

    def add_todo(self, title: str) -> int:
        """Insert the todo AND enqueue its workflow in one transaction."""
        cur = self.conn.execute("INSERT INTO todos (title) VALUES (?)", (title,))
        todo_id = cur.lastrowid
        # Same connection, same transaction: both commit or neither does.
        self.conn.execute(
            "INSERT INTO workflows (type, payload_json, state, steps_json,"
            " idempotency_key) VALUES ('todo-created', ?, 'pending', '[]', ?)",
            (f'{{"todo_id": {todo_id}}}', f"todo-created:{todo_id}"))
        self.conn.commit()
        return todo_id

    def list_todos(self) -> list[dict]:
        cur = self.conn.execute("SELECT id, title, done FROM todos ORDER BY id")
        return [{"id": r[0], "title": r[1], "done": bool(r[2])} for r in cur]

    def start_agent_turn(self, conversation_id: str, message: str) -> int:
        """Store the message and enqueue the turn's workflow, together."""
        return self.queue.enqueue(
            "agent-turn", {"conversation_id": conversation_id,
                           "message": message},
            f"agent-turn:{conversation_id}:{hash(message) & 0xFFFFFFFF}")

    def run_agent_turn(self, workflow_id: int) -> list[str]:
        """Run a turn's steps, recording each one. Resumable: steps already
        done are skipped, so a crash never repeats a side effect."""
        wf = self.queue.get(workflow_id)
        done = set(wf.steps_done)
        ran = []
        for step in AGENT_STEPS:
            if step in done:
                continue
            self.queue.record_step(workflow_id, step)
            ran.append(step)
        self.queue.complete(workflow_id)
        return ran
