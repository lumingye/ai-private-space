from pathlib import Path
from tempfile import TemporaryDirectory

from reference.boundary import GatewayBoundary, PrivacyMode, notice_for
from reference.vault import PrivateVault, generate_master_key


def main() -> None:
    print(notice_for(PrivacyMode.SOFT).message)
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "private.sqlite"
        with PrivateVault(path, master_key=generate_master_key(), user_id="demo-user", persona_id="demo-persona") as vault:
            envelope = vault.create(title="演示信封", content="这是一段只用于本地演示的假内容。", kind="whisper")
            print("sealed metadata:", envelope)
            print("opened locally:", vault.open(envelope["id"]))

    boundary = GatewayBoundary(PrivacyMode.GATEWAY)
    private_event = {
        "event_id": "evt-demo",
        "tool_name": "private_create",
        "arguments": {"content": "must not reach browser"},
        "private": True,
        "status": "ok",
    }
    assert boundary.forward_event(private_event) is None
    print("safe log:", boundary.safe_log_record(private_event))


if __name__ == "__main__":
    main()
