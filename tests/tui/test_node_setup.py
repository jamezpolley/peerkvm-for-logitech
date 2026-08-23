import asyncio

from textual.widgets import Label
from textual.widgets import Select
from textual.widgets import SelectionList

from logitech_flow_kvm.node_config import NodeConfig
from logitech_flow_kvm.node_protocol import DeviceAdvertisement
from logitech_flow_kvm.tui.node_setup import NodeSetupApp


def run(coro):
    return asyncio.run(coro)


def device(device_id: str, name: str) -> DeviceAdvertisement:
    return DeviceAdvertisement(device_id, "B369", name, "unknown", True)


def test_remembers_configured_devices_that_are_temporarily_absent():
    async def body():
        current = NodeConfig(2, "KEYS", ["MOUSE"])
        app = NodeSetupApp(lambda: [], current)
        async with app.run_test():
            assert app.query_one("#leader", Select).value == "KEYS"
            assert app.query_one("#followers", SelectionList).selected == ["MOUSE"]

    run(body())


def test_discovery_failure_is_explained_in_the_ui():
    def fail():
        raise PermissionError("cannot open /dev/hidraw9")

    async def body():
        app = NodeSetupApp(fail)
        async with app.run_test():
            problem = str(app.query_one("#problem", Label).render())
            assert "cannot open /dev/hidraw9" in problem

    run(body())
