"""Checks for atomicity, crash resume, idempotency, and agent turns."""

import unittest

from src.queue import DurableQueue
from src.todos import AGENT_STEPS, TodoApp


class TestQueue(unittest.TestCase):
    def test_idempotency_key_creates_one_workflow(self):
        q = DurableQueue()
        a = q.enqueue("todo-created", {"todo_id": 1}, "todo-created:1")
        b = q.enqueue("todo-created", {"todo_id": 1}, "todo-created:1")
        self.assertEqual(a, b)

    def test_crash_resume_after_lease_expiry(self):
        q = DurableQueue()
        wid = q.enqueue("todo-created", {"todo_id": 1}, "todo-created:1")
        wf = q.claim("worker-1")
        self.assertEqual(wf.id, wid)
        q.record_step(wid, "notify")
        # worker-1 dies: force the lease to expire
        q.conn.execute("UPDATE workflows SET lease_until = 0 WHERE id = ?", (wid,))
        q.conn.commit()
        wf2 = q.claim("worker-2")
        self.assertEqual(wf2.id, wid)
        self.assertEqual(wf2.steps_done, ["notify"])
        q.complete(wid)
        self.assertEqual(q.get(wid).state, "done")

    def test_claim_returns_none_when_empty(self):
        self.assertIsNone(DurableQueue().claim("worker-1"))


class TestTodos(unittest.TestCase):
    def test_add_todo_enqueues_workflow(self):
        app = TodoApp()
        todo_id = app.add_todo("Buy milk")
        wf = app.queue.claim("worker-1")
        self.assertEqual(wf.type, "todo-created")
        self.assertEqual(wf.payload["todo_id"], todo_id)
        self.assertEqual(app.list_todos()[0]["title"], "Buy milk")

    def test_agent_turn_runs_each_step_once(self):
        app = TodoApp()
        turn_id = app.start_agent_turn("conv-1", "hello")
        ran = app.run_agent_turn(turn_id)
        self.assertEqual(ran, AGENT_STEPS)
        self.assertEqual(app.run_agent_turn(turn_id), [])
        self.assertEqual(app.queue.get(turn_id).state, "done")


if __name__ == "__main__":
    unittest.main()
