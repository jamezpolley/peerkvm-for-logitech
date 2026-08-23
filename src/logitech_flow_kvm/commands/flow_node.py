import sys
import time
from argparse import ArgumentParser

from .. import exceptions
from ..node import FlowNode
from ..node_config import NodeConfig
from ..node_config import load_node_config
from ..node_config import save_node_config
from ..node_devices import discover_device_advertisements
from ..tui import DeviceStatus
from ..tui import FlowTUIApp
from ..tui import NodeStatus
from ..tui import render_node_status
from ..tui.node_setup import NodeSetupApp
from . import LogitechFlowKvmCommand


class FlowNodeCommand(LogitechFlowKvmCommand):
    @classmethod
    def add_arguments(cls, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--secret",
            required=True,
            help=(
                "Shared secret used to authenticate broadcasts. It is used only "
                "in memory and is never saved."
            ),
        )

    def handle(self) -> None:
        config = self._configure()
        tui: FlowTUIApp | None = None

        def publish() -> None:
            if tui is None:
                return
            advertisements = node.devices.advertisements()
            tui.update_status(
                render_node_status(
                    NodeStatus(
                        hostname=node.hostname,
                        host_number=config.host_number,
                        leader_id=config.leader_id,
                        devices=[
                            DeviceStatus(
                                id=device.id,
                                label=device.name,
                                connected=device.connected,
                            )
                            for device in advertisements
                        ],
                        peers=[
                            f"{peer.hostname} ({peer.address}, host {peer.host_number})"
                            for peer in node.peer_statuses()
                        ],
                        problem=node.last_problem,
                    )
                )
            )

        node = FlowNode(config, self.options.secret, on_change=publish)
        if sys.stdout.isatty():

            def on_start(app: FlowTUIApp) -> None:
                nonlocal tui
                tui = app
                node.start()
                publish()

            FlowTUIApp("flow-node", on_start=on_start).run()
        else:
            node.start()
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        node.stop()

    def _configure(self) -> NodeConfig:
        current = load_node_config()
        if not sys.stdout.isatty():
            if current is None:
                raise exceptions.UserError(
                    "No node configuration exists. Run flow-node once in a "
                    "terminal and complete setup in the UI."
                )
            return current
        configured = NodeSetupApp(discover_device_advertisements, current).run()
        if configured is None:
            raise exceptions.UserError("Node setup was cancelled; nothing was saved.")
        save_node_config(configured)
        return configured
