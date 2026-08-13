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

## Next memory layer

Persistence is not the same as model context. A later iteration should build a
bounded context packet from the saved data:

1. The most recent 3-5 message pairs.
2. A rolling conversation summary.
3. Verified findings extracted only from successful analysis runs.
4. Confirmed metric definitions, assumptions, filters, and unresolved questions.

Failed or low-confidence runs remain auditable in history but must not become
trusted Agent memory.

## Report generation

A conversation report should query successful `analysis_runs`, cite their run
IDs, and reuse their validated tables and visualizations. The first report
format should be HTML/Markdown; PDF and Word export can be added after the report
structure is stable.

For multi-user deployment, migrate SQLite to PostgreSQL, add user ownership to
all tables, and move uploaded files to object storage. The current normalized
schema is designed to make that migration straightforward.
