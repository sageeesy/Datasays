"""SQLite persistence for conversations, messages, files, and analysis runs."""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional


def _database_path() -> Path:
    return Path(os.getenv("DATASAYS_DB_PATH", "./data/datasays.db"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _parse_json(value: Optional[str], fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _connect() -> sqlite3.Connection:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    connection = _connect()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database() -> None:
    with _connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                file_names_json TEXT NOT NULL DEFAULT '[]',
                llm_response_json TEXT,
                sandbox_response_json TEXT
            );

            CREATE TABLE IF NOT EXISTS analysis_runs (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                user_message_id TEXT REFERENCES messages(id) ON DELETE SET NULL,
                assistant_message_id TEXT REFERENCES messages(id) ON DELETE SET NULL,
                question TEXT NOT NULL,
                model TEXT,
                prompt_style TEXT NOT NULL,
                status TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS conversation_files (
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                file_id TEXT NOT NULL,
                added_at TEXT NOT NULL,
                PRIMARY KEY (conversation_id, file_id)
            );

            CREATE INDEX IF NOT EXISTS idx_messages_conversation
                ON messages(conversation_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_runs_conversation
                ON analysis_runs(conversation_id, created_at);
            """
        )


def create_conversation(
    title: str,
    file_ids: Optional[List[str]] = None,
    conversation_id: Optional[str] = None,
) -> Dict[str, Any]:
    initialize_database()
    identifier = conversation_id or str(uuid.uuid4())
    now = _now()
    with _connection() as connection:
        connection.execute(
            "INSERT INTO conversations(id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (identifier, title.strip() or "New analysis", now, now),
        )
        _replace_files(connection, identifier, file_ids or [], now)
    return get_conversation(identifier)  # type: ignore[return-value]


def _replace_files(
    connection: sqlite3.Connection,
    conversation_id: str,
    file_ids: List[str],
    now: str,
) -> None:
    connection.execute("DELETE FROM conversation_files WHERE conversation_id = ?", (conversation_id,))
    connection.executemany(
        "INSERT INTO conversation_files(conversation_id, file_id, added_at) VALUES (?, ?, ?)",
        [(conversation_id, file_id, now) for file_id in dict.fromkeys(file_ids)],
    )


def update_conversation(
    conversation_id: str,
    title: Optional[str] = None,
    file_ids: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    initialize_database()
    now = _now()
    with _connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if not exists:
            return None
        if title is not None:
            connection.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title.strip() or "New analysis", now, conversation_id),
            )
        else:
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id)
            )
        if file_ids is not None:
            _replace_files(connection, conversation_id, file_ids, now)
    return get_conversation(conversation_id)


def delete_conversation(conversation_id: str) -> bool:
    initialize_database()
    with _connection() as connection:
        cursor = connection.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        return cursor.rowcount > 0


def _message_from_row(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "type": "user" if row["role"] == "user" else "ai",
        "content": row["content"],
        "timestamp": row["created_at"],
        "filesUsed": _parse_json(row["file_names_json"], []),
        "llmResponse": _parse_json(row["llm_response_json"], None),
        "sandboxResponse": _parse_json(row["sandbox_response_json"], None),
    }


def _conversation_from_row(connection: sqlite3.Connection, row: sqlite3.Row) -> Dict[str, Any]:
    message_rows = connection.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at, rowid",
        (row["id"],),
    ).fetchall()
    file_rows = connection.execute(
        "SELECT file_id FROM conversation_files WHERE conversation_id = ? ORDER BY added_at, rowid",
        (row["id"],),
    ).fetchall()
    messages = [_message_from_row(message) for message in message_rows]
    return {
        "id": row["id"],
        "title": row["title"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "messageCount": len(messages),
        "messages": messages,
        "activeFileIds": [item["file_id"] for item in file_rows],
    }


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    initialize_database()
    with _connection() as connection:
        row = connection.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        return _conversation_from_row(connection, row) if row else None


def list_conversations() -> List[Dict[str, Any]]:
    initialize_database()
    with _connection() as connection:
        rows = connection.execute(
            "SELECT * FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
        return [_conversation_from_row(connection, row) for row in rows]


def save_message(
    conversation_id: str,
    role: str,
    content: str,
    message_id: Optional[str] = None,
    file_names: Optional[List[str]] = None,
    llm_response: Optional[Dict[str, Any]] = None,
    sandbox_response: Optional[Dict[str, Any]] = None,
    created_at: Optional[str] = None,
) -> str:
    initialize_database()
    identifier = message_id or str(uuid.uuid4())
    timestamp = created_at or _now()
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO messages(
                id, conversation_id, role, content, created_at, file_names_json,
                llm_response_json, sandbox_response_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                content = excluded.content,
                file_names_json = excluded.file_names_json,
                llm_response_json = excluded.llm_response_json,
                sandbox_response_json = excluded.sandbox_response_json
            """,
            (
                identifier, conversation_id, role, content, timestamp,
                _json(file_names or []),
                _json(llm_response) if llm_response is not None else None,
                _json(sandbox_response) if sandbox_response is not None else None,
            ),
        )
        connection.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?", (timestamp, conversation_id)
        )
    return identifier


def save_analysis_exchange(
    conversation_id: str,
    user_message_id: str,
    question: str,
    file_names: List[str],
    model: Optional[str],
    prompt_style: str,
    response: Dict[str, Any],
) -> Dict[str, str]:
    user_id = save_message(
        conversation_id=conversation_id,
        role="user",
        content=question,
        message_id=user_message_id,
        file_names=file_names,
    )
    assistant_id = str(uuid.uuid4())
    assistant_timestamp = _now()
    save_message(
        conversation_id=conversation_id,
        role="assistant",
        content="",
        message_id=assistant_id,
        llm_response=response.get("llmResponse"),
        sandbox_response=response.get("sandboxResponse"),
        created_at=assistant_timestamp,
    )
    run_id = str(uuid.uuid4())
    status = (response.get("sandboxResponse") or {}).get("status", "error")
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO analysis_runs(
                id, conversation_id, user_message_id, assistant_message_id, question,
                model, prompt_style, status, response_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, conversation_id, user_id, assistant_id, question, model,
                prompt_style, status, _json(response), assistant_timestamp,
            ),
        )
    return {"runId": run_id, "userMessageId": user_id, "assistantMessageId": assistant_id}


def list_analysis_runs(conversation_id: str, verified_only: bool = False) -> List[Dict[str, Any]]:
    initialize_database()
    query = "SELECT * FROM analysis_runs WHERE conversation_id = ?"
    parameters: List[Any] = [conversation_id]
    if verified_only:
        query += " AND status = ?"
        parameters.append("success")
    query += " ORDER BY created_at"
    with _connection() as connection:
        rows = connection.execute(query, parameters).fetchall()
        return [
            {
                "id": row["id"],
                "question": row["question"],
                "model": row["model"],
                "promptStyle": row["prompt_style"],
                "status": row["status"],
                "response": _parse_json(row["response_json"], {}),
                "createdAt": row["created_at"],
            }
            for row in rows
        ]
