# Design: an app starter where background work survives crashes

Status: demo of the durability pattern, with synthetic data. It does not
claim a web framework, SSO, Postgres, a worker cluster, or a model.

## 1. One origin

One origin serves the pages and the API, so cookies need no CORS and no
proxy. The API can also run on its own for other clients, with routing at
the ingress. In development the pages run on one port and forward `/api/*`
to the API on another.

## 2. Durable workflows

A workflow is a row: type, payload, state, steps completed, a lease, and
an idempotency key. The queue lives in the database, so a crash or restart
loses nothing.

States: `pending` → `claimed` → `done` (or `failed`). A worker claims a
workflow with a lease (bounded time). It records each step as it completes.
If the worker dies, the lease expires and another worker reclaims the
workflow and resumes it from the last completed step.

## 3. Transactional enqueue

Creating a todo and enqueueing its workflow happen in one transaction.
Either both commit or neither does. There is no window where the todo
exists but its work is lost, and no window where the work exists but the
todo does not.

The same rule applies to agent turns: storing the user's message, claiming
the conversation for the new turn, and enqueueing the turn's workflow
commit together.

## 4. Idempotency keys

Every workflow carries an idempotency key (e.g. `todo-created:<todo id>`).
Enqueueing the same key twice returns the existing workflow instead of
creating a second one. A double-submit, a retry, or a crash between the
write and the response can never duplicate the work.

## 5. Agent turns as workflows

An agent turn is a workflow with steps: read the conversation, plan, act,
reply. Each step is recorded as it completes, and each step's side effects
are idempotent (keyed by turn + step). A crash resumes at the last
completed step. The turn never repeats an action, and never loses the
conversation.

Until a model is configured, agent turns fail with a message that says so
— and everything else runs.

## 6. Advisory-lock migrations

Migrations run with an advisory lock: only one migrator runs at a time, so
overlapping deploys wait instead of colliding. The migrator applies schema
changes and creates the workflow tables. The apps only read and write rows.

## 7. What production adds

- **Web + API:** a real framework, typed API with OpenAPI docs, forms
  with schema validation on submit.
- **Auth:** SSO sign-in (no passwords), with an auth service behind the
  API.
- **Postgres:** one connection pool per process; the queue, the entities,
  and the app data all live there.
- **Workers:** a cluster of workers with a scheduler for cron workflows.
- **Telemetry:** traces, metrics, and logs exported via OTLP, off until an
  endpoint is set.
