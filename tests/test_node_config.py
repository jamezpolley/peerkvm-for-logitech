import json

import platformdirs

from logitech_flow_kvm.node_config import NodeConfig
from logitech_flow_kvm.node_config import load_node_config
from logitech_flow_kvm.node_config import save_node_config


def test_round_trip_does_not_include_a_secret(tmp_path, monkeypatch):
    monkeypatch.setattr(
        platformdirs, "user_config_dir", lambda *args, **kwargs: str(tmp_path)
    )
    expected = NodeConfig(2, "LEADER", ["MOUSE"], clipboard_enabled=False)

    save_node_config(expected)

    assert load_node_config() == expected
    stored = json.loads((tmp_path / "node.json").read_text())
    assert "secret" not in stored


def test_missing_or_invalid_config_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(
        platformdirs, "user_config_dir", lambda *args, **kwargs: str(tmp_path)
    )
    assert load_node_config() is None
    (tmp_path / "node.json").write_text("not json")
    assert load_node_config() is None
