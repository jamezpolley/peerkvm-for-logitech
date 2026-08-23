"""Run local commands when the Flow leader moves to another host."""

from __future__ import annotations

import logging
import os
import subprocess
import threading

logger = logging.getLogger(__name__)


class SwitchHookRunner:
    """Launch configured shell commands without blocking Flow event handling."""

    def __init__(self, commands: list[str], *, local_host: int):
        self._commands = commands
        self._local_host = local_host
        self._last_host: int | None = None
        self._lock = threading.Lock()

    def trigger(self, target_host: int) -> bool:
        """Run hooks once per observed host change, including initial sync."""
        with self._lock:
            if target_host == self._last_host:
                return False
            previous_host = self._last_host
            self._last_host = target_host

        if self._commands:
            threading.Thread(
                target=self._execute,
                args=(previous_host, target_host),
                daemon=True,
                name="switch-hooks",
            ).start()
        return True

    def _execute(self, previous_host: int | None, target_host: int) -> None:
        env = os.environ.copy()
        env.update(
            {
                "LOGITECH_FLOW_LOCAL_HOST": str(self._local_host),
                "LOGITECH_FLOW_PREVIOUS_HOST": (
                    "" if previous_host is None else str(previous_host)
                ),
                "LOGITECH_FLOW_TARGET_HOST": str(target_host),
            }
        )
        for command in self._commands:
            try:
                result = subprocess.run(command, shell=True, env=env, check=False)
            except OSError:
                logger.exception("Could not execute switch hook: %s", command)
                continue
            if result.returncode == 0:
                logger.info("Switch hook completed: %s", command)
            else:
                logger.warning(
                    "Switch hook failed with status %d: %s",
                    result.returncode,
                    command,
                )
