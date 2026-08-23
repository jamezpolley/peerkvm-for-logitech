from types import SimpleNamespace

from logitech_flow_kvm import switch_hooks
from logitech_flow_kvm.switch_hooks import SwitchHookRunner


class ImmediateThread:
    def __init__(self, *, target, args, **kwargs):
        self.target = target
        self.args = args

    def start(self):
        self.target(*self.args)


def test_runs_commands_with_host_environment_in_order(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs["env"]))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(switch_hooks.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(switch_hooks.subprocess, "run", run)
    runner = SwitchHookRunner(["first", "second"], local_host=2)

    assert runner.trigger(1) is True
    assert runner.trigger(3) is True

    assert [command for command, _env in calls] == [
        "first",
        "second",
        "first",
        "second",
    ]
    assert calls[0][1]["LOGITECH_FLOW_LOCAL_HOST"] == "2"
    assert calls[0][1]["LOGITECH_FLOW_PREVIOUS_HOST"] == ""
    assert calls[0][1]["LOGITECH_FLOW_TARGET_HOST"] == "1"
    assert calls[2][1]["LOGITECH_FLOW_PREVIOUS_HOST"] == "1"
    assert calls[2][1]["LOGITECH_FLOW_TARGET_HOST"] == "3"


def test_ignores_repeated_host_state(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(switch_hooks.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(switch_hooks.subprocess, "run", run)
    runner = SwitchHookRunner(["command"], local_host=1)

    assert runner.trigger(2) is True
    assert runner.trigger(2) is False

    assert calls == ["command"]


def test_failure_does_not_prevent_later_commands(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1 if command == "bad" else 0)

    monkeypatch.setattr(switch_hooks.subprocess, "run", run)
    runner = SwitchHookRunner(["bad", "good"], local_host=1)

    runner._execute(1, 2)

    assert calls == ["bad", "good"]
