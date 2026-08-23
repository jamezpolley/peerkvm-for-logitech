from __future__ import annotations

import json
import os
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field

import platformdirs

from . import constants


@dataclass(frozen=True)
class MonitorInputConfig:
    monitor_id: str
    input_source: int


@dataclass(frozen=True)
class NodeConfig:
    host_number: int
    leader_id: str
    follower_ids: list[str]
    clipboard_enabled: bool = True
    monitor_inputs: list[MonitorInputConfig] = field(default_factory=list)


def get_node_config_path() -> str:
    directory = platformdirs.user_config_dir(constants.APP_NAME, constants.APP_AUTHOR)
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, "node.json")


def load_node_config() -> NodeConfig | None:
    try:
        with open(get_node_config_path()) as source:
            data = json.load(source)
        return NodeConfig(
            host_number=int(data["host_number"]),
            leader_id=str(data["leader_id"]),
            follower_ids=[str(value) for value in data["follower_ids"]],
            clipboard_enabled=bool(data.get("clipboard_enabled", True)),
            monitor_inputs=[
                MonitorInputConfig(
                    monitor_id=str(item["monitor_id"]),
                    input_source=int(item["input_source"]),
                )
                for item in data.get("monitor_inputs", [])
            ],
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def save_node_config(config: NodeConfig) -> None:
    path = get_node_config_path()
    temporary = f"{path}.tmp"
    with open(temporary, "w") as destination:
        json.dump(asdict(config), destination, indent=2)
        destination.write("\n")
    os.replace(temporary, path)
