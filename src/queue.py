"""Durable workflow queue backed by SQLite.

A workflow is a row: type, payload, state, completed steps, a lease, and
an idempotency key. Crash-safe by construction: a claimed workflow whose
lease expires is reclaimable, and the same idempotency key never creates
two workflows.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass

LEASE_SECONDS = 30


@dataclass
class Workflow:
    id: int
    type: str
    payload: dict
    state: str
    steps_done: list[str]
    idempotency_key: str


class DurableQueue:
    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS workflows (
                id INTEGER PRIMARY KEY,
                type TEXT, payload_json TEXT, state TEXT,
                steps_json TEXT, idempotency_key TEXT UNIQUE,
                claimed_by TEXT, lease_until REAL);
        """)

    def enqueue(self, workflow_type: str, payload: dict,
                idempotency_key: str) -> int:
        """Insert, or return the existing workflow for the same key."""
        cur = self.conn.execute(
            "SELECT id FROM workflows WHERE idempotency_key = ?",
            (idempotency_key,))
        row = cur.fetchone()
        if row:
            return row["id"]
        cur = self.conn.execute(
            "INSERT INTO workflows (type, payload_json, state, steps_json,"
            " idempotency_key) VALUES (?, ?, 'pending', '[]', ?)",
            (workflow_type, json.dumps(payload), idempotency_key))
        self.conn.commit()
        return cur.lastrowid

    def claim(self, worker: str) -> Workflow | None:
        """Claim one pending (or lease-expired) workflow for this worker."""
        now = time.time()
        cur = self.conn.execute(
            "SELECT * FROM workflows WHERE state = 'pending' OR "
            "(state = 'claimed' AND lease_until < ?) "
            "ORDER BY id LIMIT 1", (now,))
        row = cur.fetchone()
        if row is None:
            return None
        self.conn.execute(
            "UPDATE workflows SET state = 'claimed', claimed_by = ?, "
            "lease_until = ? WHERE id = ?",
            (worker, now + LEASE_SECONDS, row["id"]))
        self.conn.commit()
        return self._to_workflow(row)

    def record_step(self, workflow_id: int, step: str) -> None:
        cur = self.conn.execute(
            "SELECT steps_json FROM workflows WHERE id = ?", (workflow_id,))
        steps = json.loads(cur.fetchone()["steps_json"])
        steps.append(step)
        self.conn.execute(
            "UPDATE workflows SET steps_json = ? WHERE id = ?",
            (json.dumps(steps), workflow_id))
        self.conn.commit()

    def complete(self, workflow_id: int) -> None:
        self.conn.execute(
            "UPDATE workflows SET state = 'done' WHERE id = ?", (workflow_id,))
        self.conn.commit()

    def fail(self, workflow_id: int) -> None:
        self.conn.execute(
            "UPDATE workflows SET state = 'failed' WHERE id = ?",
            (workflow_id,))
        self.conn.commit()

    def get(self, workflow_id: int) -> Workflow:
        cur = self.conn.execute(
            "SELECT * FROM workflows WHERE id = ?", (workflow_id,))
        return self._to_workflow(cur.fetchone())

    @staticmethod
    def _to_workflow(row: sqlite3.Row) -> Workflow:
        return Workflow(id=row["id"], type=row["type"],
                        payload=json.loads(row["payload_json"]),
                        state=row["state"],
                        steps_done=json.loads(row["steps_json"]),
                        idempotency_key=row["idempotency_key"])
