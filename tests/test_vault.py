from pathlib import Path

import pytest

from reference.vault import PrivateVault, generate_master_key


def test_vault_roundtrip(tmp_path: Path):
    key = generate_master_key()
    path = tmp_path / "vault.sqlite"
    with PrivateVault(path, master_key=key, user_id="u", persona_id="p") as vault:
        env = vault.create(title="t", content="c", kind="whisper")
        assert "content" not in env
        opened = vault.open(env["id"])
        assert opened["title"] == "t"
        assert opened["content"] == "c"


def test_identity_is_bound(tmp_path: Path):
    key = generate_master_key()
    path = tmp_path / "vault.sqlite"
    with PrivateVault(path, master_key=key, user_id="u", persona_id="p"):
        pass
    with pytest.raises(ValueError):
        PrivateVault(path, master_key=key, user_id="u", persona_id="other")
