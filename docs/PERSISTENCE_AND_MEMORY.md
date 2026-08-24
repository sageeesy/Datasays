# DataSays Persistence and Memory

## Current persistence

DataSays uses SQLite for local, single-user persistence. The default database is:

```text
server/data/datasays.db
```

Set `DATASAYS_DB_PATH` to override this location. Uploaded CSV files remain in
`server/uploads`; the database stores their IDs and conversation associations.

The database contains four core tables:

- `conversations`: title and lifecycle timestamps.
- `messages`: user messages and complete assistant response payloads.
- `analysis_runs`: model, prompt style, status, Trace, validation, code, and dashboard artifacts.
- `conversation_files`: files currently attached to each conversation.

The frontend restores conversations and uploaded-file metadata on startup. A
saved assistant response contains the full structured `AnalysisResult`, so its
evidence section, execution Trace, and interactive Dashboard remain available
after a refresh or backend restart.

## API

```text
GET    /api/conversations
POST   /api/conversations
GET    /api/conversations/{id}
PATCH  /api/conversations/{id}
DELETE /api/conversations/{id}
POST   /api/conversations/{id}/messages
GET    /api/conversations/{id}/runs?verified_only=true
```

`POST /api/query` accepts `conversationId` and `userMessageId`. The user message
is persisted before analysis begins; the assistant response and analysis run are
persisted when execution finishes.

`POST /api/query/stream` accepts the same payload and returns Server-Sent Events.
It emits public node progress first and the same stable response envelope as the
final `result` event.

## Agent checkpoints

LangGraph state is stored separately from product conversation data:

```text
server/data/agent-checkpoints.db
```

Set `DATASAYS_CHECKPOINT_PATH` to override this location. Each analysis run uses
a unique `graph_thread_id`, and a checkpoint is written after each graph step.
The response metadata records the thread ID, backend type, and checkpoint count.
The current API does not yet expose pause/resume, replay, or approval controls;
the checkpoints provide the durable foundation for those capabilities.

## Current bounded memory layer

Persistence is not the same as model context. DataSays now builds a bounded
context packet from saved data for each follow-up:

1. At most eight recent messages, excluding the active user message.
2. At most five findings extracted from successful, validation-passing runs.
3. Only findings associated with the current dataset names.
4. Source run IDs so memory use remains auditable.

Failed or low-confidence runs remain auditable in history but must not become
trusted Agent memory.

The planner and code generator receive this packet with explicit instructions
to recompute requested values from current files. The packet is bounded by a
character limit and does not contain full prior datasets.

## Next memory upgrades

- Rolling conversation summaries for long threads.
- Explicit user confirmation of business definitions and assumptions.
- Resume and approval endpoints backed by existing LangGraph checkpoints.
- Semantic retrieval only after the stored knowledge volume justifies it.

## Report generation

A conversation report should query successful `analysis_runs`, cite their run
IDs, and reuse their validated tables and visualizations. The first report
format should be HTML/Markdown; PDF and Word export can be added after the report
structure is stable.

For multi-user deployment, migrate SQLite to PostgreSQL, add user ownership to
all tables, and move uploaded files to object storage. The current normalized
schema is designed to make that migration straightforward.
