from __future__ import annotations

from collections.abc import Callable

from textual.app import App
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Button
from textual.widgets import Checkbox
from textual.widgets import Footer
from textual.widgets import Input
from textual.widgets import Label
from textual.widgets import Select
from textual.widgets import SelectionList

from ..node_config import NodeConfig
from ..node_protocol import DeviceAdvertisement


class NodeSetupApp(App[NodeConfig | None]):
    TITLE = "Logitech Flow KVM setup"
    CSS = """
    VerticalScroll { padding: 1 2; }
    Label { margin-top: 1; }
    #problem { color: $error; height: auto; }
    Button { margin-top: 1; }
    """

    def __init__(
        self,
        discover: Callable[[], list[DeviceAdvertisement]],
        current: NodeConfig | None = None,
    ):
        super().__init__()
        self.discover = discover
        self.current = current
        self.discovery_problem: str | None = None
        try:
            self.devices = discover()
        except Exception as error:
            self.devices = []
            self.discovery_problem = f"Device discovery failed: {error}"

    def compose(self) -> ComposeResult:
        options = self._options()
        selected_followers = set(self.current.follower_ids if self.current else [])
        with VerticalScroll():
            yield Label(
                "Configure this node. Switch a device to this host and choose "
                "Refresh if it is not listed."
            )
            yield Label("Host number")
            yield Input(
                value=str(self.current.host_number) if self.current else "",
                placeholder="1",
                id="host-number",
                type="integer",
            )
            yield Label("Leader")
            yield Select(
                options,
                value=self.current.leader_id if self.current else Select.NULL,
                prompt="Choose the keyboard whose host button you press",
                id="leader",
            )
            yield Label("Followers")
            yield SelectionList(
                *[
                    (label, value, value in selected_followers)
                    for label, value in options
                ],
                id="followers",
            )
            yield Checkbox(
                "Synchronize clipboard",
                value=self.current.clipboard_enabled if self.current else True,
                id="clipboard",
            )
            yield Label(self.discovery_problem or "", id="problem")
            yield Button("Refresh devices", id="refresh")
            yield Button("Save and start", variant="primary", id="save")
        yield Footer()

    @staticmethod
    def _label(device: DeviceAdvertisement) -> str:
        state = "connected" if device.connected else "paired"
        return f"{device.name} — {device.id} ({state})"

    def _options(self) -> list[tuple[str, str]]:
        options = [(self._label(device), device.id) for device in self.devices]
        known = {value for _, value in options}
        if self.current is not None:
            configured = [self.current.leader_id, *self.current.follower_ids]
            options.extend(
                (f"{device_id} (not currently detected)", device_id)
                for device_id in configured
                if device_id not in known
            )
        return options

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh":
            self._refresh()
        elif event.button.id == "save":
            self._save()

    def _refresh(self) -> None:
        try:
            self.devices = self.discover()
        except Exception as error:
            self.query_one("#problem", Label).update(
                f"Device discovery failed: {error}"
            )
            return
        options = self._options()
        leader = self.query_one("#leader", Select)
        leader_value = leader.value
        leader.set_options(options)
        if leader_value in {value for _, value in options}:
            leader.value = leader_value
        followers = self.query_one("#followers", SelectionList)
        selected = set(followers.selected)
        followers.clear_options()
        followers.add_options(
            (label, value, value in selected) for label, value in options
        )
        self.query_one("#problem", Label).update(
            f"Found {len(self.devices)} device(s)."
        )

    def _save(self) -> None:
        problem = self.query_one("#problem", Label)
        try:
            host_number = int(self.query_one("#host-number", Input).value)
            if host_number < 1:
                raise ValueError
        except ValueError:
            problem.update("Host number must be a positive integer.")
            return
        leader = self.query_one("#leader", Select).value
        if leader is Select.NULL:
            problem.update("Choose one leader device.")
            return
        followers = list(self.query_one("#followers", SelectionList).selected)
        if str(leader) in followers:
            problem.update("The leader cannot also be a follower.")
            return
        if not followers:
            problem.update("Choose at least one follower device.")
            return
        self.exit(
            NodeConfig(
                host_number=host_number,
                leader_id=str(leader),
                follower_ids=[str(value) for value in followers],
                clipboard_enabled=self.query_one("#clipboard", Checkbox).value,
            )
        )
