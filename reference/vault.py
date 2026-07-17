"""Minimal encrypted, non-recallable persona vault.

Reference only. It intentionally contains no FTS, vector, recall, profile,
summary, API authentication, or production key-management integration.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
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
KEY_CHECK_PLAINTEXT = b"ai-private-space-key-check-v1"
KINDS = frozenset({"secret", "letter", "reflection", "unfinished", "whisper"})
REMINDERS = frozenset({"never", "date", "review"})
REMINDER_STATES = frozenset({"inactive", "pending", "delivered", "dismissed"})
MAX_TITLE_BYTES = 4 * 1024
MAX_CONTENT_BYTES = 1024 * 1024
MAX_LIST_LIMIT = 100
_ENTRY_TOKEN = re.compile(r"[0-9a-f]{32}\Z")


class VaultError(Exception):
    """Base error for vault operations."""


class VaultKeyError(VaultError):
    """The supplied key cannot authenticate this vault."""


class VaultIntegrityError(VaultError):
    """Authenticated vault data was modified or is incomplete."""


def now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def generate_master_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def decode_master_key(value: str | bytes) -> bytes:
    """Decode a canonical 32-byte key.

    Text values are URL-safe base64. Byte values are treated as raw key bytes,
    never as encoded text, so configuration mistakes fail instead of silently
    deriving a different vault key.
    """
    if isinstance(value, bytes):
        material = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("master key is empty")
        try:
            encoded = text.encode("ascii")
            encoded += b"=" * (-len(encoded) % 4)
            material = base64.b64decode(encoded, altchars=b"-_", validate=True)
        except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
            raise ValueError("master key must be valid URL-safe base64") from exc
    else:
        raise TypeError("master key must be URL-safe base64 text or 32 raw bytes")
    if len(material) != 32:
        raise ValueError("master key must contain exactly 32 random bytes")
    return material


def derive_key(material: bytes, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(material)


def _canonical_utc(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty ISO 8601 timestamp")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return (
        parsed.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _validated_identifier(value: str, *, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} is required")
    if len(normalized.encode("utf-8")) > 256:
        raise ValueError(f"{field} is too long")
    return normalized


def _validated_text(value: str, *, field: str, maximum_bytes: int) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} is required")
    if len(normalized.encode("utf-8")) > maximum_bytes:
        raise ValueError(f"{field} exceeds the {maximum_bytes}-byte limit")
    return normalized


def _validated_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("limit must be an integer")
    if limit < 0 or limit > MAX_LIST_LIMIT:
        raise ValueError(f"limit must be between 0 and {MAX_LIST_LIMIT}")
    return limit


class PrivateVault(AbstractContextManager["PrivateVault"]):
    def __init__(
        self,
        path: str | Path,
        *,
        master_key: str | bytes,
        user_id: str,
        persona_id: str,
    ):
        self.path = Path(path)
        self.user_id = _validated_identifier(user_id, field="user_id")
        self.persona_id = _validated_identifier(persona_id, field="persona_id")
        self.conn: sqlite3.Connection | None = None
        self._key: bytes | None = None
        self._metadata_key: bytes | None = None

        self._prepare_path()
        try:
            self.conn = sqlite3.connect(self.path, timeout=5.0)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.execute("PRAGMA busy_timeout=5000")
            self._init_schema()
            salt_row = self.conn.execute(
                "SELECT value FROM vault_meta WHERE key='salt'"
            ).fetchone()
            if salt_row is None:
                raise VaultIntegrityError("vault salt is missing")
            self._key = derive_key(decode_master_key(master_key), bytes(salt_row[0]))
            self._metadata_key = hmac.new(
                self._key,
                b"ai-private-space-metadata-key-v1",
                hashlib.sha256,
            ).digest()
            self._verify_or_initialize_key_check()
            self._migrate_metadata_tags()
            self._secure_database_permissions()
        except Exception:
            self._close_connection()
            self._key = None
            self._metadata_key = None
            raise

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        self._key = None
        self._metadata_key = None
        self._close_connection()

    def _close_connection(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def _require_connection(self) -> sqlite3.Connection:
        if self.conn is None or self._key is None or self._metadata_key is None:
            raise VaultError("vault is closed")
        return self.conn

    def _prepare_path(self) -> None:
        if self.path.is_symlink():
            raise PermissionError("vault path must not be a symbolic link")
        parent_existed = self.path.parent.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            try:
                if not parent_existed:
                    os.chmod(self.path.parent, 0o700)
                elif self.path.parent.stat().st_mode & 0o077:
                    raise PermissionError(
                        "an existing vault directory must be owner-only (0700)"
                    )
            except OSError as exc:
                raise PermissionError("cannot secure the vault directory") from exc

    def _secure_database_permissions(self) -> None:
        if os.name != "posix":
            return
        try:
            os.chmod(self.path, 0o600)
            if self.path.stat().st_mode & 0o077:
                raise PermissionError("vault database permissions are too broad")
        except OSError as exc:
            raise PermissionError("cannot secure the vault database") from exc

    def _init_schema(self) -> None:
        if self.conn is None:
            raise VaultError("vault connection is not available")
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS vault_meta (
              key TEXT PRIMARY KEY,
              value BLOB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS private_entries (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              entry_token TEXT NOT NULL UNIQUE,
              kind TEXT NOT NULL,
              reminder_mode TEXT NOT NULL,
              reminder_state TEXT NOT NULL DEFAULT 'pending',
              review_at TEXT,
              last_delivered_at TEXT,
              nonce BLOB NOT NULL,
              ciphertext BLOB NOT NULL,
              metadata_tag BLOB,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )
        columns = {
            str(row["name"])
            for row in self.conn.execute("PRAGMA table_info(private_entries)")
        }
        migrations = {
            "reminder_state": (
                "ALTER TABLE private_entries "
                "ADD COLUMN reminder_state TEXT NOT NULL DEFAULT 'pending'"
            ),
            "last_delivered_at": (
                "ALTER TABLE private_entries ADD COLUMN last_delivered_at TEXT"
            ),
            "metadata_tag": (
                "ALTER TABLE private_entries ADD COLUMN metadata_tag BLOB"
            ),
        }
        for column, statement in migrations.items():
            if column not in columns:
                self.conn.execute(statement)
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_private_due
            ON private_entries(reminder_state, reminder_mode, review_at)
            """
        )

        if self.conn.execute(
            "SELECT 1 FROM vault_meta WHERE key='salt'"
        ).fetchone() is None:
            self.conn.execute(
                "INSERT INTO vault_meta(key,value) VALUES('salt',?)",
                (os.urandom(16),),
            )

        identity_hash = hashlib.sha256(
            f"{self.user_id}\0{self.persona_id}".encode("utf-8")
        ).digest()
        row = self.conn.execute(
            "SELECT value FROM vault_meta WHERE key='identity_hash'"
        ).fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO vault_meta(key,value) VALUES('identity_hash',?)",
                (identity_hash,),
            )
        elif not hmac.compare_digest(bytes(row[0]), identity_hash):
            raise ValueError("vault belongs to another user/persona")
        self.conn.commit()

    def _key_check_aad(self) -> bytes:
        return (
            f"{SCHEMA}|key-check|{self.user_id}|{self.persona_id}"
        ).encode("utf-8")

    def _verify_or_initialize_key_check(self) -> None:
        conn = self._require_connection()
        nonce_row = conn.execute(
            "SELECT value FROM vault_meta WHERE key='key_check_nonce'"
        ).fetchone()
        ciphertext_row = conn.execute(
            "SELECT value FROM vault_meta WHERE key='key_check_ciphertext'"
        ).fetchone()
        if (nonce_row is None) != (ciphertext_row is None):
            raise VaultIntegrityError("vault key-check metadata is incomplete")

        if nonce_row is not None and ciphertext_row is not None:
            try:
                plaintext = AESGCM(self._key).decrypt(
                    bytes(nonce_row[0]),
                    bytes(ciphertext_row[0]),
                    self._key_check_aad(),
                )
            except InvalidTag as exc:
                raise VaultKeyError("wrong master key or modified vault") from exc
            if not hmac.compare_digest(plaintext, KEY_CHECK_PLAINTEXT):
                raise VaultKeyError("wrong master key or modified vault")
            return

        first_entry = conn.execute(
            "SELECT * FROM private_entries ORDER BY id LIMIT 1"
        ).fetchone()
        if first_entry is not None:
            try:
                self._decrypt_row_raw(first_entry)
            except (InvalidTag, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise VaultKeyError(
                    "cannot authenticate a legacy vault with this master key"
                ) from exc

        nonce = os.urandom(12)
        ciphertext = AESGCM(self._key).encrypt(
            nonce,
            KEY_CHECK_PLAINTEXT,
            self._key_check_aad(),
        )
        with conn:
            conn.execute(
                "INSERT INTO vault_meta(key,value) VALUES('key_check_nonce',?)",
                (nonce,),
            )
            conn.execute(
                "INSERT INTO vault_meta(key,value) VALUES('key_check_ciphertext',?)",
                (ciphertext,),
            )

    def _aad(self, token: str, kind: str) -> bytes:
        return (
            f"{SCHEMA}|{self.user_id}|{self.persona_id}|{token}|{kind}"
        ).encode("utf-8")

    def _metadata_payload(self, values: dict[str, Any]) -> bytes:
        payload = {
            "schema": SCHEMA,
            "entry_token": values["entry_token"],
            "kind": values["kind"],
            "reminder_mode": values["reminder_mode"],
            "reminder_state": values["reminder_state"],
            "review_at": values.get("review_at"),
            "last_delivered_at": values.get("last_delivered_at"),
            "created_at": values["created_at"],
            "updated_at": values["updated_at"],
        }
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def _metadata_tag_for(self, values: dict[str, Any]) -> bytes:
        if self._metadata_key is None:
            raise VaultError("vault is closed")
        return hmac.new(
            self._metadata_key,
            self._metadata_payload(values),
            hashlib.sha256,
        ).digest()

    def _verify_metadata(self, row: sqlite3.Row) -> None:
        if row["kind"] not in KINDS:
            raise VaultIntegrityError("entry kind is invalid")
        if row["reminder_mode"] not in REMINDERS:
            raise VaultIntegrityError("entry reminder mode is invalid")
        if row["reminder_state"] not in REMINDER_STATES:
            raise VaultIntegrityError("entry reminder state is invalid")
        stored = row["metadata_tag"]
        if stored is None:
            raise VaultIntegrityError("entry metadata authentication is missing")
        expected = self._metadata_tag_for(dict(row))
        if not hmac.compare_digest(bytes(stored), expected):
            raise VaultIntegrityError("entry metadata authentication failed")

    def _migrate_metadata_tags(self) -> None:
        conn = self._require_connection()
        rows = conn.execute(
            "SELECT * FROM private_entries WHERE metadata_tag IS NULL"
        ).fetchall()
        if not rows:
            return
        with conn:
            for row in rows:
                values = dict(row)
                if values["kind"] not in KINDS:
                    raise VaultIntegrityError("legacy entry kind is invalid")
                if values["reminder_mode"] not in REMINDERS:
                    raise VaultIntegrityError("legacy reminder mode is invalid")
                if values["reminder_mode"] == "never":
                    values["reminder_state"] = "inactive"
                    values["review_at"] = None
                elif values["reminder_mode"] == "date":
                    if values["review_at"] is None:
                        raise VaultIntegrityError(
                            "legacy date reminder has no review_at"
                        )
                    values["review_at"] = _canonical_utc(
                        str(values["review_at"]),
                        field="legacy review_at",
                    )
                    values["reminder_state"] = "pending"
                else:
                    values["review_at"] = None
                    values["reminder_state"] = "pending"
                values["last_delivered_at"] = None
                tag = self._metadata_tag_for(values)
                conn.execute(
                    """
                    UPDATE private_entries
                    SET reminder_state=?,review_at=?,last_delivered_at=NULL,metadata_tag=?
                    WHERE id=?
                    """,
                    (
                        values["reminder_state"],
                        values["review_at"],
                        tag,
                        int(row["id"]),
                    ),
                )

    def _validated_token(self, entry_id: str) -> str:
        if not isinstance(entry_id, str) or not _ENTRY_TOKEN.fullmatch(entry_id):
            raise ValueError("entry id must be an opaque 32-character token")
        return entry_id

    def _row_for(self, entry_id: str) -> sqlite3.Row:
        conn = self._require_connection()
        token = self._validated_token(entry_id)
        row = conn.execute(
            "SELECT * FROM private_entries WHERE entry_token=?",
            (token,),
        ).fetchone()
        if row is None:
            raise KeyError(entry_id)
        self._verify_metadata(row)
        return row

    def _decrypt_row_raw(self, row: sqlite3.Row) -> dict[str, Any]:
        if self._key is None:
            raise VaultError("vault is closed")
        plaintext = AESGCM(self._key).decrypt(
            bytes(row["nonce"]),
            bytes(row["ciphertext"]),
            self._aad(str(row["entry_token"]), str(row["kind"])),
        )
        data = json.loads(plaintext.decode("utf-8"))
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("title"), str)
            or not isinstance(data.get("content"), str)
        ):
            raise VaultIntegrityError("entry plaintext has an invalid structure")
        return data

    def _make_envelope(
        self,
        row: sqlite3.Row,
        *,
        include_private_metadata: bool,
    ) -> dict[str, Any]:
        envelope: dict[str, Any] = {
            "id": str(row["entry_token"]),
            "sealed": True,
        }
        if include_private_metadata:
            envelope.update(
                {
                    "kind": str(row["kind"]),
                    "reminder_mode": str(row["reminder_mode"]),
                    "reminder_state": str(row["reminder_state"]),
                    "review_at": row["review_at"],
                    "created_at": str(row["created_at"]),
                }
            )
        return envelope

    def create(
        self,
        *,
        title: str,
        content: str,
        kind: str = "secret",
        reminder_mode: str = "never",
        review_at: str | None = None,
    ) -> dict[str, Any]:
        conn = self._require_connection()
        title = _validated_text(
            title,
            field="title",
            maximum_bytes=MAX_TITLE_BYTES,
        )
        content = _validated_text(
            content,
            field="content",
            maximum_bytes=MAX_CONTENT_BYTES,
        )
        if kind not in KINDS:
            raise ValueError(f"unsupported kind: {kind}")
        if reminder_mode not in REMINDERS:
            raise ValueError(f"unsupported reminder mode: {reminder_mode}")
        if reminder_mode == "date":
            if review_at is None:
                raise ValueError("review_at is required for date reminders")
            review_at = _canonical_utc(review_at, field="review_at")
        elif review_at is not None:
            raise ValueError("review_at is only valid for date reminders")

        token = uuid.uuid4().hex
        nonce = os.urandom(12)
        now = now_iso()
        reminder_state = "inactive" if reminder_mode == "never" else "pending"
        plaintext = json.dumps(
            {"title": title, "content": content},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        ciphertext = AESGCM(self._key).encrypt(
            nonce,
            plaintext,
            self._aad(token, kind),
        )
        values: dict[str, Any] = {
            "entry_token": token,
            "kind": kind,
            "reminder_mode": reminder_mode,
            "reminder_state": reminder_state,
            "review_at": review_at,
            "last_delivered_at": None,
            "created_at": now,
            "updated_at": now,
        }
        metadata_tag = self._metadata_tag_for(values)
        with conn:
            conn.execute(
                """
                INSERT INTO private_entries(
                  entry_token,kind,reminder_mode,reminder_state,review_at,
                  last_delivered_at,nonce,ciphertext,metadata_tag,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    token,
                    kind,
                    reminder_mode,
                    reminder_state,
                    review_at,
                    None,
                    nonce,
                    ciphertext,
                    metadata_tag,
                    now,
                    now,
                ),
            )
        return self.envelope(token)

    def envelope(
        self,
        entry_id: str,
        *,
        include_private_metadata: bool = False,
    ) -> dict[str, Any]:
        row = self._row_for(entry_id)
        return self._make_envelope(
            row,
            include_private_metadata=include_private_metadata,
        )

    def list_envelopes(
        self,
        *,
        limit: int = 50,
        include_private_metadata: bool = False,
    ) -> list[dict[str, Any]]:
        conn = self._require_connection()
        limit = _validated_limit(limit)
        if limit == 0:
            return []
        rows = conn.execute(
            "SELECT * FROM private_entries ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        envelopes = []
        for row in rows:
            self._verify_metadata(row)
            envelopes.append(
                self._make_envelope(
                    row,
                    include_private_metadata=include_private_metadata,
                )
            )
        return envelopes

    def _due_rows(self, instant: str) -> list[sqlite3.Row]:
        conn = self._require_connection()
        rows = conn.execute("SELECT * FROM private_entries ORDER BY id").fetchall()
        due: list[sqlite3.Row] = []
        for row in rows:
            self._verify_metadata(row)
            if row["reminder_state"] != "pending":
                continue
            if row["reminder_mode"] == "review":
                due.append(row)
            elif (
                row["reminder_mode"] == "date"
                and row["review_at"] is not None
                and str(row["review_at"]) <= instant
            ):
                due.append(row)
        due.sort(key=lambda row: (str(row["review_at"] or ""), int(row["id"])))
        return due

    def list_due(
        self,
        *,
        instant: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        limit = _validated_limit(limit)
        if limit == 0:
            return []
        canonical_instant = (
            now_iso()
            if instant is None
            else _canonical_utc(instant, field="instant")
        )
        return [
            {**self._make_envelope(row, include_private_metadata=False), "due": True}
            for row in self._due_rows(canonical_instant)[:limit]
        ]

    def claim_due(
        self,
        *,
        instant: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Atomically mark due reminders delivered and return minimal envelopes."""
        conn = self._require_connection()
        limit = _validated_limit(limit)
        if limit == 0:
            return []
        canonical_instant = (
            now_iso()
            if instant is None
            else _canonical_utc(instant, field="instant")
        )
        now = now_iso()
        try:
            conn.execute("BEGIN IMMEDIATE")
            due_rows = self._due_rows(canonical_instant)[:limit]
            claimed: list[dict[str, Any]] = []
            for row in due_rows:
                values = dict(row)
                values["reminder_state"] = "delivered"
                values["last_delivered_at"] = now
                values["updated_at"] = now
                tag = self._metadata_tag_for(values)
                conn.execute(
                    """
                    UPDATE private_entries
                    SET reminder_state='delivered',last_delivered_at=?,updated_at=?,metadata_tag=?
                    WHERE entry_token=? AND reminder_state='pending'
                    """,
                    (now, now, tag, row["entry_token"]),
                )
                claimed.append(
                    {
                        **self._make_envelope(
                            row,
                            include_private_metadata=False,
                        ),
                        "due": True,
                    }
                )
            conn.commit()
            return claimed
        except Exception:
            conn.rollback()
            raise

    def snooze_reminder(self, entry_id: str, *, review_at: str) -> None:
        conn = self._require_connection()
        row = self._row_for(entry_id)
        canonical_review_at = _canonical_utc(review_at, field="review_at")
        now = now_iso()
        values = dict(row)
        values.update(
            {
                "reminder_mode": "date",
                "reminder_state": "pending",
                "review_at": canonical_review_at,
                "last_delivered_at": None,
                "updated_at": now,
            }
        )
        tag = self._metadata_tag_for(values)
        with conn:
            conn.execute(
                """
                UPDATE private_entries
                SET reminder_mode='date',reminder_state='pending',review_at=?,
                    last_delivered_at=NULL,updated_at=?,metadata_tag=?
                WHERE entry_token=?
                """,
                (canonical_review_at, now, tag, entry_id),
            )

    def dismiss_reminder(self, entry_id: str) -> None:
        conn = self._require_connection()
        row = self._row_for(entry_id)
        now = now_iso()
        values = dict(row)
        values["reminder_state"] = "dismissed"
        values["updated_at"] = now
        tag = self._metadata_tag_for(values)
        with conn:
            conn.execute(
                """
                UPDATE private_entries
                SET reminder_state='dismissed',updated_at=?,metadata_tag=?
                WHERE entry_token=?
                """,
                (now, tag, entry_id),
            )

    def open(self, entry_id: str) -> dict[str, Any]:
        row = self._row_for(entry_id)
        try:
            data = self._decrypt_row_raw(row)
        except (InvalidTag, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VaultIntegrityError("entry authentication failed") from exc
        return {
            **self._make_envelope(row, include_private_metadata=True),
            **data,
            "sealed": False,
        }
