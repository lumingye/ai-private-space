import base64
import hashlib
import json
import os
import sqlite3
import uuid
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from reference.vault import (
    MAX_CONTENT_BYTES,
    SCHEMA,
    PrivateVault,
    VaultIntegrityError,
    VaultKeyError,
    decode_master_key,
    derive_key,
    generate_master_key,
    now_iso,
)


def test_vault_roundtrip_uses_opaque_minimal_envelope(tmp_path: Path):
    key = generate_master_key()
    path = tmp_path / "vault.sqlite"
    with PrivateVault(path, master_key=key, user_id="u", persona_id="p") as vault:
        envelope = vault.create(title="t", content="c", kind="whisper")
        assert set(envelope) == {"id", "sealed"}
        assert len(envelope["id"]) == 32
        assert envelope["id"].isalnum()
        opened = vault.open(envelope["id"])
        assert opened["title"] == "t"
        assert opened["content"] == "c"
        assert opened["kind"] == "whisper"


def test_identity_is_bound_and_failed_construction_closes_cleanly(tmp_path: Path):
    key = generate_master_key()
    path = tmp_path / "vault.sqlite"
    with PrivateVault(path, master_key=key, user_id="u", persona_id="p"):
        pass
    with pytest.raises(ValueError):
        PrivateVault(path, master_key=key, user_id="u", persona_id="other")
    with PrivateVault(path, master_key=key, user_id="u", persona_id="p"):
        pass


def test_wrong_key_is_rejected_before_any_new_entry_can_be_written(tmp_path: Path):
    key_one = generate_master_key()
    key_two = generate_master_key()
    path = tmp_path / "vault.sqlite"
    with PrivateVault(path, master_key=key_one, user_id="u", persona_id="p") as vault:
        vault.create(title="one", content="first")

    with pytest.raises(VaultKeyError):
        PrivateVault(path, master_key=key_two, user_id="u", persona_id="p")

    with sqlite3.connect(path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM private_entries").fetchone()[0]
    assert count == 1


def test_wrong_key_is_rejected_even_when_vault_has_no_entries(tmp_path: Path):
    key_one = generate_master_key()
    key_two = generate_master_key()
    path = tmp_path / "vault.sqlite"
    with PrivateVault(path, master_key=key_one, user_id="u", persona_id="p"):
        pass
    with pytest.raises(VaultKeyError):
        PrivateVault(path, master_key=key_two, user_id="u", persona_id="p")


def test_metadata_tampering_is_detected_before_reminder_use(tmp_path: Path):
    key = generate_master_key()
    path = tmp_path / "vault.sqlite"
    with PrivateVault(path, master_key=key, user_id="u", persona_id="p") as vault:
        vault.create(
            title="dated",
            content="content",
            reminder_mode="date",
            review_at="2030-01-01T00:00:00Z",
        )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE private_entries SET review_at='2000-01-01T00:00:00.000Z'"
        )
        connection.commit()
    with PrivateVault(path, master_key=key, user_id="u", persona_id="p") as vault:
        with pytest.raises(VaultIntegrityError):
            vault.list_due(instant="2026-01-01T00:00:00Z")


def test_ciphertext_tampering_is_detected_on_open(tmp_path: Path):
    key = generate_master_key()
    path = tmp_path / "vault.sqlite"
    with PrivateVault(path, master_key=key, user_id="u", persona_id="p") as vault:
        entry_id = vault.create(title="t", content="c")["id"]
    with sqlite3.connect(path) as connection:
        ciphertext = bytearray(
            connection.execute(
                "SELECT ciphertext FROM private_entries WHERE entry_token=?",
                (entry_id,),
            ).fetchone()[0]
        )
        ciphertext[0] ^= 1
        connection.execute(
            "UPDATE private_entries SET ciphertext=? WHERE entry_token=?",
            (bytes(ciphertext), entry_id),
        )
        connection.commit()
    with PrivateVault(path, master_key=key, user_id="u", persona_id="p") as vault:
        with pytest.raises(VaultIntegrityError):
            vault.open(entry_id)


def test_date_reminder_is_normalized_and_requires_timezone(tmp_path: Path):
    key = generate_master_key()
    path = tmp_path / "vault.sqlite"
    with PrivateVault(path, master_key=key, user_id="u", persona_id="p") as vault:
        entry_id = vault.create(
            title="t",
            content="c",
            reminder_mode="date",
            review_at="2026-01-01T08:00:00+08:00",
        )["id"]
        assert vault.open(entry_id)["review_at"] == "2026-01-01T00:00:00.000Z"
        with pytest.raises(ValueError):
            vault.create(
                title="bad",
                content="bad",
                reminder_mode="date",
                review_at="2026-01-01T00:00:00",
            )


def test_due_claim_is_atomic_and_not_repeated(tmp_path: Path):
    key = generate_master_key()
    path = tmp_path / "vault.sqlite"
    with PrivateVault(path, master_key=key, user_id="u", persona_id="p") as vault:
        entry_id = vault.create(
            title="review",
            content="later",
            reminder_mode="review",
        )["id"]
        assert [item["id"] for item in vault.list_due()] == [entry_id]
        assert [item["id"] for item in vault.claim_due()] == [entry_id]
        assert vault.list_due() == []


def test_snooze_and_dismiss_update_authenticated_metadata(tmp_path: Path):
    key = generate_master_key()
    path = tmp_path / "vault.sqlite"
    with PrivateVault(path, master_key=key, user_id="u", persona_id="p") as vault:
        entry_id = vault.create(
            title="review",
            content="later",
            reminder_mode="review",
        )["id"]
        vault.snooze_reminder(entry_id, review_at="2030-01-01T00:00:00Z")
        assert vault.list_due(instant="2029-01-01T00:00:00Z") == []
        vault.dismiss_reminder(entry_id)
        assert vault.open(entry_id)["reminder_state"] == "dismissed"


def test_master_key_decoding_is_strict():
    assert len(decode_master_key(generate_master_key())) == 32
    raw = os.urandom(32)
    assert decode_master_key(raw) == raw
    with pytest.raises(ValueError):
        decode_master_key("not*valid*base64")
    with pytest.raises(ValueError):
        decode_master_key(base64.urlsafe_b64encode(os.urandom(31)).decode("ascii"))
    with pytest.raises(ValueError):
        decode_master_key(base64.urlsafe_b64encode(raw))


def test_size_and_list_limits_are_enforced(tmp_path: Path):
    key = generate_master_key()
    path = tmp_path / "vault.sqlite"
    with PrivateVault(path, master_key=key, user_id="u", persona_id="p") as vault:
        vault.create(title="t", content="c")
        assert vault.list_envelopes(limit=0) == []
        with pytest.raises(ValueError):
            vault.list_envelopes(limit=101)
        with pytest.raises(ValueError):
            vault.create(title="t", content="x" * (MAX_CONTENT_BYTES + 1))


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission check")
def test_existing_vault_directory_must_be_owner_only(tmp_path: Path):
    public_directory = tmp_path / "public"
    public_directory.mkdir()
    os.chmod(public_directory, 0o755)
    with pytest.raises(PermissionError):
        PrivateVault(
            public_directory / "vault.sqlite",
            master_key=generate_master_key(),
            user_id="u",
            persona_id="p",
        )


def _create_legacy_vault(path: Path, *, key: str) -> str:
    salt = os.urandom(16)
    derived = derive_key(decode_master_key(key), salt)
    token = uuid.uuid4().hex
    nonce = os.urandom(12)
    created_at = now_iso()
    aad = f"{SCHEMA}|u|p|{token}|secret".encode("utf-8")
    ciphertext = AESGCM(derived).encrypt(
        nonce,
        json.dumps({"title": "legacy", "content": "content"}).encode("utf-8"),
        aad,
    )
    identity_hash = hashlib.sha256(b"u\0p").digest()
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE vault_meta (key TEXT PRIMARY KEY, value BLOB NOT NULL);
            CREATE TABLE private_entries (
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
            """
        )
        connection.execute("INSERT INTO vault_meta VALUES('salt',?)", (salt,))
        connection.execute(
            "INSERT INTO vault_meta VALUES('identity_hash',?)",
            (identity_hash,),
        )
        connection.execute(
            """
            INSERT INTO private_entries(
              entry_token,kind,reminder_mode,review_at,nonce,ciphertext,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (token, "secret", "never", None, nonce, ciphertext, created_at, created_at),
        )
    return token


def test_legacy_vault_requires_key_proof_before_migration(tmp_path: Path):
    correct_key = generate_master_key()
    wrong_key = generate_master_key()
    path = tmp_path / "legacy.sqlite"
    entry_id = _create_legacy_vault(path, key=correct_key)

    with pytest.raises(VaultKeyError):
        PrivateVault(path, master_key=wrong_key, user_id="u", persona_id="p")
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM vault_meta WHERE key='key_check_nonce'"
            ).fetchone()
            is None
        )

    with PrivateVault(
        path,
        master_key=correct_key,
        user_id="u",
        persona_id="p",
    ) as vault:
        assert vault.open(entry_id)["title"] == "legacy"
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM vault_meta WHERE key='key_check_nonce'"
            ).fetchone()
            is not None
        )
        assert (
            connection.execute(
                "SELECT metadata_tag FROM private_entries WHERE entry_token=?",
                (entry_id,),
            ).fetchone()[0]
            is not None
        )
