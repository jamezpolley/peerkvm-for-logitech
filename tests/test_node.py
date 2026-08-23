from unittest.mock import Mock

from logitech_flow_kvm.node import FlowNode
from logitech_flow_kvm.node_config import NodeConfig
from logitech_flow_kvm.node_protocol import NodeAdvertisement


def make_node() -> FlowNode:
    node = FlowNode(NodeConfig(2, "KEYS-LOCAL", ["MOUSE-LOCAL"]), "secret")
    node.devices = Mock()
    node.transport = Mock()
    node._transport_started = True
    return node


def test_local_leader_connection_announces_this_host():
    node = make_node()

    node._device_connected("KEYS-LOCAL")

    sent = node.transport.send.call_args.args[0]
    assert sent.target_host == 2


def test_follower_connection_does_not_announce_a_host_change():
    node = make_node()

    node._device_connected("MOUSE-LOCAL")

    node.transport.send.assert_not_called()


def test_remote_target_switches_only_configured_local_followers():
    node = make_node()
    message = NodeAdvertisement("birch", "birch", 3, [], "KEYS", target_host=3)

    node._message(message, "192.168.0.33")

    node.devices.switch_connected.assert_called_once_with(["MOUSE-LOCAL"], 3)
    assert node.peers["birch"].address == "192.168.0.33"


def test_own_broadcast_is_ignored():
    node = make_node()
    message = NodeAdvertisement(
        node.node_id, node.hostname, 2, [], "KEYS", target_host=2
    )

    node._message(message, "192.168.0.32")

    node.devices.switch_connected.assert_not_called()


def test_invalid_secret_problem_is_visible_in_status():
    changed = Mock()
    node = FlowNode(
        NodeConfig(2, "KEYS", ["MOUSE"]), "secret", on_change=changed
    )

    node._invalid_packet("192.168.0.33", ValueError("shared secrets differ"))

    assert "shared secrets differ" in (node.last_problem or "")
    changed.assert_called_once()
