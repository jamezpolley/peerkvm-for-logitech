from unittest.mock import Mock

from logitech_flow_kvm.node_devices import NodeDeviceManager


def manager() -> NodeDeviceManager:
    return NodeDeviceManager(lambda: None, lambda _device_id: None)


def test_missing_follower_is_a_normal_noop(monkeypatch):
    devices = manager()
    switch = Mock()
    monkeypatch.setattr("logitech_flow_kvm.node_devices.change_device_host", switch)

    devices.switch_connected(["MOUSE-ON-ANOTHER-HOST"], 2)

    switch.assert_not_called()


def test_only_a_connected_local_follower_is_switched(monkeypatch):
    devices = manager()
    mouse = Mock(id="MOUSE")
    devices._devices = {"MOUSE": mouse}
    devices._connected = {"MOUSE"}
    switch = Mock()
    monkeypatch.setattr("logitech_flow_kvm.node_devices.change_device_host", switch)

    devices.switch_connected(["MOUSE", "ABSENT"], 3)

    switch.assert_called_once_with(mouse, 3)
