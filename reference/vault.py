"""Minimal encrypted, non-recallable persona vault.

Reference only. It intentionally contains no FTS, vector, recall, profile,
or summary integration.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

SCHEMA = "ai-private-space-v1"
KINDS = {"secret", "letter", "reflection", "unfinished", "whisper"}
REMINDERS = {"never", "date", "review"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def generate_master_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def decode_master_key(value: str | bytes) -> bytes:
    if isinstance(value, bytes):
        material = value
    else:
        text = value.strip()
        material = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    if len(material) < 32:
        raise ValueError("master key must contain at least 32 random bytes")
    return material


def derive_key(material: bytes, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(material)


class PrivateVault(AbstractContextManager["PrivateVault"]):
    def __init__(self, path: str | Path, *, master_key: str | bytes, user_id: str, persona_id: str):
        self.path = Path(path)
        self.user_id = user_id.strip()
        self.persona_id = persona_id.strip()
        if not self.user_id or not self.persona_id:
            raise ValueError("user_id and persona_id are required")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        salt = bytes(self.conn.execute("SELECT value FROM vault_meta WHERE key='salt'").fetchone()[0])
        self._key = derive_key(decode_master_key(master_key), salt)

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        self._key = b""
        self.conn.close()

    def _init_schema(self) -> None:
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS vault_meta (
          key TEXT PRIMARY KEY,
          value BLOB NOT NULL
        );
        CREATE TABLE IF NOT EXISTS private_entries (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          entry_token TEXT NOT NULL UNIQUE,
          kind TEXT NOT NULL,
          reminder_mode TEXT NOT NULL,
          review_at TEXT,
          nonce BLOB NOT NULL,
          ciphertext BLOB NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_private_due
          ON private_entries(reminder_mode, review_at);
        """)
        if self.conn.execute("SELECT 1 FROM vault_meta WHERE key='salt'").fetchone() is None:
            self.conn.execute("INSERT INTO vault_meta(key,value) VALUES('salt',?)", (os.urandom(16),))
        identity_hash = hashlib.sha256(f"{self.user_id}\0{self.persona_id}".encode()).digest()
        row = self.conn.execute("SELECT value FROM vault_meta WHERE key='identity_hash'").fetchone()
        if row is None:
            self.conn.execute("INSERT INTO vault_meta(key,value) VALUES('identity_hash',?)", (identity_hash,))
        elif bytes(row[0]) != identity_hash:
            raise ValueError("vault belongs to another user/persona")
        self.conn.commit()

    def _aad(self, token: str, kind: str) -> bytes:
        return f"{SCHEMA}|{self.user_id}|{self.persona_id}|{token}|{kind}".encode()

    def create(self, *, title: str, content: str, kind: str = "secret", reminder_mode: str = "never", review_at: str | None = None) -> dict[str, Any]:
        title, content = title.strip(), content.strip()
        if not title or not content:
            raise ValueError("title and content are required")
        if kind not in KINDS:
            raise ValueError(f"unsupported kind: {kind}")
        if reminder_mode not in REMINDERS:
            raise ValueError(f"unsupported reminder mode: {reminder_mode}")
        if reminder_mode == "date" and not review_at:
            raise ValueError("review_at is required for date reminders")

        token, nonce, now = uuid.uuid4().hex, os.urandom(12), now_iso()
        plaintext = json.dumps({"title": title, "content": content}, ensure_ascii=False).encode()
        ciphertext = AESGCM(self._key).encrypt(nonce, plaintext, self._aad(token, kind))
        cur = self.conn.execute("""
          INSERT INTO private_entries(entry_token,kind,reminder_mode,review_at,nonce,ciphertext,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?)
        """, (token, kind, reminder_mode, review_at, nonce, ciphertext, now, now))
        self.conn.commit()
        return self.envelope(cur.lastrowid)

    def envelope(self, entry_id: int) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM private_entries WHERE id=?", (int(entry_id),)).fetchone()
        if row is None:
            raise KeyError(entry_id)
        return {
            "id": int(row["id"]),
            "kind": row["kind"],
            "reminder_mode": row["reminder_mode"],
            "review_at": row["review_at"],
            "created_at": row["created_at"],
            "sealed": True,
        }

    def list_envelopes(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT id FROM private_entries ORDER BY id DESC LIMIT ?", (max(1, min(limit, 100)),)).fetchall()
        return [self.envelope(row[0]) for row in rows]

    def list_due(self, *, instant: str | None = None) -> list[dict[str, Any]]:
        instant = instant or now_iso()
        rows = self.conn.execute("""
          SELECT id FROM private_entries
          WHERE reminder_mode='review' OR (reminder_mode='date' AND review_at<=?)
          ORDER BY review_at,id
        """, (instant,)).fetchall()
        return [self.envelope(row[0]) for row in rows]

    def open(self, entry_id: int) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM private_entries WHERE id=?", (int(entry_id),)).fetchone()
        if row is None:
            raise KeyError(entry_id)
        try:
            plaintext = AESGCM(self._key).decrypt(bytes(row["nonce"]), bytes(row["ciphertext"]), self._aad(row["entry_token"], row["kind"]))
        except InvalidTag as exc:
            raise ValueError("wrong key or modified entry") from exc
        data = json.loads(plaintext.decode())
        return {**self.envelope(entry_id), **data, "sealed": False}
