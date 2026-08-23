import argparse

import pytest

from logitech_flow_kvm.commands.flow_node import FlowNodeCommand


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    FlowNodeCommand.add_arguments(result)
    return result


def test_secret_is_the_only_runtime_setting():
    options = parser().parse_args(["--secret", "shared"])
    assert vars(options) == {"secret": "shared"}


def test_secret_is_required(capsys):
    with pytest.raises(SystemExit):
        parser().parse_args([])
    assert "--secret" in capsys.readouterr().err
