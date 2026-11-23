# Durable App Starter — Demo

A starter for apps where background work must survive crashes, rebuilt from
scratch with synthetic data. One origin serves the pages and the API; a
durable workflow queue runs the background work; an AI agent's turn is a
durable workflow too.

This is a personal demo project. It captures the pattern — durable
workflows, transactional enqueue, crash-safe resume, advisory-lock
migrations — without any client code, client data, or proprietary material.

## The problem

Background work that lives only in memory dies with the process. A todo
created and its notification enqueued in two separate steps can lose the
notification. An agent turn that crashes halfway restarts from scratch and
repeats its side effects. Durable workflows fix all three: the work, its
state, and its progress live in the database, in the same transaction as
the change that caused it.

## How it works

```
User adds a todo
  -> one transaction: insert the todo AND enqueue its workflow
  -> worker claims the workflow (with a lease)
  -> worker runs it, records each step, marks it done
  -> if the worker dies mid-run, the lease expires and another
     worker picks the workflow up and resumes it
```

- **Transactional enqueue.** The row and its workflow commit together, or
  neither does. There is no window where the todo exists but its work is
  lost.
- **Leased claims.** A worker claims a workflow for a bounded time. A
  crashed worker's lease expires and the work is reclaimed — no stuck jobs,
  no manual intervention.
- **Idempotency keys.** Retrying a workflow with the same key creates one
  workflow, not two. A double-submit is a no-op, not a duplicate.
- **Agent turns as workflows.** Each turn is a workflow with steps (read,
  plan, act, reply). A crash resumes at the last completed step instead of
  repeating the turn's side effects.
- **Advisory-lock migrations.** Only one migration runs at a time;
  overlapping deploys wait instead of colliding.

## Run it

```bash
python -m src.run_demo
```

Pure standard library, no dependencies (SQLite via `sqlite3`). It adds a
todo, runs its workflow, simulates a worker crash and the resume, and runs
an agent turn.

Run the checks:

```bash
python -m unittest discover -s tests -v
```

## What this proves

- **No lost work.** A todo and its workflow commit in one transaction;
  the test kills the process between enqueue and completion and the work
  still completes.
- **Crash-safe resume.** A claimed workflow whose worker dies is
  re-claimed after its lease expires, and resumes from its recorded steps.
- **No duplicates.** The same idempotency key twice yields one workflow.
- **Agent turns are durable.** A turn's steps are recorded as they
  complete, so a resume never repeats a side effect.

## Layout

- `src/queue.py` — the durable workflow queue (SQLite).
- `src/todos.py` — the todo list + agent turns as workflows.
- `src/run_demo.py` — the demo walkthrough.
- `docs/design.md` — the full design: one origin, durable workflows,
  agent turns, migrations, telemetry.
- `tests/` — checks for atomicity, crash resume, idempotency, and turns.

## What production adds

A real web framework and API layer, SSO sign-in, Postgres instead of
SQLite, a cluster of workers, a model behind the agent turns, and OTLP
telemetry. None of those are claimed here — the demo is the durability
mechanism, local only.
