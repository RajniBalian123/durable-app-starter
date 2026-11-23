"""Demo walkthrough: durable todos, a worker crash, and an agent turn."""

from src.queue import DurableQueue
from src.todos import TodoApp


def main() -> None:
    app = TodoApp()
    todo_id = app.add_todo("Buy milk")
    print(f"1. Added todo {todo_id}; its workflow was enqueued in the same transaction")
    print(f"   Todos: {app.list_todos()}")

    # Worker 1 claims the workflow and dies before finishing.
    wf = app.queue.claim("worker-1")
    print(f"\n2. worker-1 claimed workflow {wf.id} ({wf.type}) and crashed")
    app.queue.record_step(wf.id, "notify")
    # Simulate the crash: force the lease to expire without completing.
    app.queue.conn.execute(
        "UPDATE workflows SET lease_until = 0 WHERE id = ?", (wf.id,))
    app.queue.conn.commit()

    # Worker 2 reclaims it and finishes.
    wf2 = app.queue.claim("worker-2")
    print(f"3. worker-2 reclaimed workflow {wf2.id}; steps already done: {wf2.steps_done}")
    app.queue.complete(wf2.id)
    print(f"   Workflow {wf2.id} is now {app.queue.get(wf2.id).state}")

    # Idempotency: same key twice, one workflow.
    q = DurableQueue()
    a = q.enqueue("todo-created", {"todo_id": 9}, "todo-created:9")
    b = q.enqueue("todo-created", {"todo_id": 9}, "todo-created:9")
    print(f"\n4. Same idempotency key twice -> one workflow: {a} == {b}")

    # Agent turn: steps recorded, resumable.
    turn_id = app.start_agent_turn("conv-1", "Add 'Call mum' to my list")
    ran = app.run_agent_turn(turn_id)
    print(f"\n5. Agent turn {turn_id} ran steps: {ran}")
    ran_again = app.run_agent_turn(turn_id)
    print(f"   Re-running the same turn runs nothing twice: {ran_again}")


if __name__ == "__main__":
    main()
