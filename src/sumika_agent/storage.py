from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class Store:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                create table if not exists kv (
                    key text primary key,
                    value text not null,
                    updated_at real not null
                );
                create table if not exists world_memory (
                    id integer primary key autoincrement,
                    content text not null,
                    source text not null default 'manual',
                    created_at real not null
                );
                create table if not exists user_memory (
                    user_id text primary key,
                    display_name text,
                    summary text not null default '',
                    preferences text not null default '{}',
                    boundaries text not null default '{}',
                    favorability real not null default 0,
                    last_interaction real,
                    updated_at real not null
                );
                create table if not exists interaction_log (
                    id integer primary key autoincrement,
                    scope text not null,
                    target_id text not null,
                    user_id text not null,
                    message text not null,
                    reply text not null,
                    redaction_labels text not null default '[]',
                    metadata text not null default '{}',
                    created_at real not null
                );
                create table if not exists relationships (
                    subject_id text not null,
                    object_id text not null,
                    relation_type text not null default 'related',
                    strength real not null default 0,
                    summary text not null default '',
                    metadata text not null default '{}',
                    updated_at real not null,
                    primary key(subject_id, object_id, relation_type)
                );
                create table if not exists approvals (
                    id integer primary key autoincrement,
                    request_type text not null,
                    flag text,
                    user_id text,
                    group_id text,
                    comment text,
                    natural_reply text not null,
                    status text not null default 'pending',
                    created_at real not null,
                    decided_at real
                );
                create table if not exists counters (
                    bucket text not null,
                    name text not null,
                    value integer not null default 0,
                    updated_at real not null,
                    primary key(bucket, name)
                );
                create table if not exists whitelist (
                    target_type text not null,
                    target_id text not null,
                    label text,
                    enabled integer not null default 1,
                    primary key(target_type, target_id)
                );
                """
            )
            self._ensure_column("interaction_log", "redaction_labels", "text not null default '[]'")
            self._ensure_column("interaction_log", "metadata", "text not null default '{}'")

    def get_json(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute("select value from kv where key = ?", (key,)).fetchone()
            if not row:
                return default
            return json.loads(row["value"])

    def set_json(self, key: str, value: Any) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "insert into kv(key, value, updated_at) values(?, ?, ?) "
                "on conflict(key) do update set value=excluded.value, updated_at=excluded.updated_at",
                (key, json.dumps(value, ensure_ascii=False), time.time()),
            )

    def world_memories(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "select * from world_memory order by id desc limit ?", (limit,)
            ).fetchall()
            return [dict(row) for row in rows]

    def add_world_memory(self, content: str, source: str = "manual") -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "insert into world_memory(content, source, created_at) values(?, ?, ?)",
                (content.strip(), source, time.time()),
            )

    def get_user_memory(self, user_id: str, display_name: str | None = None) -> dict[str, Any]:
        now = time.time()
        with self._lock, self._conn:
            row = self._conn.execute(
                "select * from user_memory where user_id = ?", (user_id,)
            ).fetchone()
            if row:
                data = dict(row)
                data["preferences"] = json.loads(data["preferences"] or "{}")
                data["boundaries"] = json.loads(data["boundaries"] or "{}")
                return data
            self._conn.execute(
                "insert into user_memory(user_id, display_name, updated_at) values(?, ?, ?)",
                (user_id, display_name, now),
            )
            return {
                "user_id": user_id,
                "display_name": display_name,
                "summary": "",
                "preferences": {},
                "boundaries": {},
                "favorability": 0.0,
                "last_interaction": None,
                "updated_at": now,
            }

    def update_user_memory(self, user_id: str, **fields: Any) -> None:
        allowed = {"display_name", "summary", "preferences", "boundaries", "favorability", "last_interaction"}
        updates: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key in {"preferences", "boundaries"}:
                value = json.dumps(value or {}, ensure_ascii=False)
            updates.append(f"{key} = ?")
            values.append(value)
        if not updates:
            return
        updates.append("updated_at = ?")
        values.append(time.time())
        values.append(user_id)
        with self._lock, self._conn:
            self._conn.execute(
                f"update user_memory set {', '.join(updates)} where user_id = ?", values
            )

    def list_user_memories(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "select * from user_memory order by updated_at desc limit ?", (limit,)
            ).fetchall()
            result = []
            for row in rows:
                data = dict(row)
                data["preferences"] = json.loads(data["preferences"] or "{}")
                data["boundaries"] = json.loads(data["boundaries"] or "{}")
                result.append(data)
            return result

    def _columns(self, table: str) -> set[str]:
        rows = self._conn.execute(f"pragma table_info({table})").fetchall()
        return {str(row["name"]) for row in rows}

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        if column not in self._columns(table):
            self._conn.execute(f"alter table {table} add column {column} {definition}")

    def record_interaction(
        self,
        scope: str,
        target_id: str,
        user_id: str,
        message: str,
        reply: str,
        *,
        redaction_labels: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "insert into interaction_log(scope, target_id, user_id, message, reply, "
                "redaction_labels, metadata, created_at) values(?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    scope,
                    target_id,
                    user_id,
                    message[:2000],
                    reply[:2000],
                    json.dumps(redaction_labels or [], ensure_ascii=False),
                    json.dumps(metadata or {}, ensure_ascii=False),
                    time.time(),
                ),
            )

    def upsert_relationship(
        self, subject_id: str, object_id: str, patch: dict[str, Any]
    ) -> None:
        relation_type = str(patch.get("relation_type") or "related")
        strength = float(patch.get("strength") or 0)
        summary = str(patch.get("summary") or "")
        metadata = patch.get("metadata") or {}
        with self._lock, self._conn:
            self._conn.execute(
                "insert into relationships(subject_id, object_id, relation_type, strength, summary, metadata, updated_at) "
                "values(?, ?, ?, ?, ?, ?, ?) "
                "on conflict(subject_id, object_id, relation_type) do update set "
                "strength=excluded.strength, summary=excluded.summary, metadata=excluded.metadata, updated_at=excluded.updated_at",
                (
                    str(subject_id),
                    str(object_id),
                    relation_type,
                    strength,
                    summary,
                    json.dumps(metadata, ensure_ascii=False),
                    time.time(),
                ),
            )

    def list_relationships(self, subject_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "select * from relationships where subject_id = ? order by updated_at desc limit ?",
                (str(subject_id), limit),
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["metadata"] = json.loads(item["metadata"] or "{}")
                result.append(item)
            return result

    def export_user_memory(self, user_id: str) -> dict[str, Any]:
        with self._lock:
            profile = self.get_user_memory(user_id)
            interactions = [
                dict(row)
                for row in self._conn.execute(
                    "select * from interaction_log where user_id = ? order by created_at desc limit 500",
                    (str(user_id),),
                ).fetchall()
            ]
            relationships = self.list_relationships(user_id, limit=200)
            return {
                "profile": profile,
                "interactions": interactions,
                "relationships": relationships,
            }

    def delete_user_memory(self, user_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("delete from user_memory where user_id = ?", (str(user_id),))
            self._conn.execute("delete from interaction_log where user_id = ?", (str(user_id),))
            self._conn.execute(
                "delete from relationships where subject_id = ? or object_id = ?",
                (str(user_id), str(user_id)),
            )

    def enqueue_approval(self, request: dict[str, Any]) -> int:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "insert into approvals(request_type, flag, user_id, group_id, comment, natural_reply, "
                "status, created_at) values(?, ?, ?, ?, ?, ?, 'pending', ?)",
                (
                    request.get("request_type"),
                    request.get("flag"),
                    str(request.get("user_id") or ""),
                    str(request.get("group_id") or ""),
                    request.get("comment") or "",
                    request.get("natural_reply") or "我考虑考虑。",
                    time.time(),
                ),
            )
            return int(cur.lastrowid)

    def list_approvals(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("select * from approvals order by id desc limit 100").fetchall()
            return [dict(row) for row in rows]

    def set_approval_status(self, approval_id: int, status: str) -> dict[str, Any] | None:
        with self._lock, self._conn:
            self._conn.execute(
                "update approvals set status = ?, decided_at = ? where id = ?",
                (status, time.time(), approval_id),
            )
            row = self._conn.execute("select * from approvals where id = ?", (approval_id,)).fetchone()
            return dict(row) if row else None

    def increment_counter(self, bucket: str, name: str, amount: int = 1) -> int:
        now = time.time()
        with self._lock, self._conn:
            self._conn.execute(
                "insert into counters(bucket, name, value, updated_at) values(?, ?, ?, ?) "
                "on conflict(bucket, name) do update set value=value+excluded.value, updated_at=excluded.updated_at",
                (bucket, name, amount, now),
            )
            row = self._conn.execute(
                "select value from counters where bucket = ? and name = ?", (bucket, name)
            ).fetchone()
            return int(row["value"])

    def get_counter(self, bucket: str, name: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "select value from counters where bucket = ? and name = ?", (bucket, name)
            ).fetchone()
            return int(row["value"]) if row else 0

    def is_whitelisted(self, target_type: str, target_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "select enabled from whitelist where target_type = ? and target_id = ?",
                (target_type, target_id),
            ).fetchone()
            return bool(row and row["enabled"])

    def set_whitelist(self, target_type: str, target_id: str, enabled: bool, label: str | None = None) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "insert into whitelist(target_type, target_id, label, enabled) values(?, ?, ?, ?) "
                "on conflict(target_type, target_id) do update set label=excluded.label, enabled=excluded.enabled",
                (target_type, target_id, label, 1 if enabled else 0),
            )

    def list_whitelist(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "select * from whitelist order by target_type, target_id"
            ).fetchall()
            return [dict(row) for row in rows]
