from unittest.mock import Mock

from logitech_flow_kvm.monitors import Ddcutil
from logitech_flow_kvm.monitors import InputSource
from logitech_flow_kvm.monitors import Monitor
from logitech_flow_kvm.monitors import parse_capabilities_output
from logitech_flow_kvm.monitors import parse_detect_output

DETECT_OUTPUT = """
Display 1
   I2C bus:          /dev/i2c-13
   DRM connector:    card2-HDMI-A-5
   Monitor:          PHL:PHL 278E1:

Display 2
   I2C bus:          /dev/i2c-14
   DRM connector:    card2-DP-1
   Monitor:          DEL:DELL U2720Q:ABC123
"""

CAPABILITIES_OUTPUT = """
Model: 328E1C
MCCS version: 2.2
VCP Features:
   Feature: 60 (Input Source)
      Values (unparsed):  11 12 0F
      Values (  parsed):
         11: HDMI-1
         12: HDMI-2
         0f: DisplayPort-1
   Feature: 62 (Audio speaker volume)
"""


def test_parses_detected_monitors_with_stable_identity():
    monitors = parse_detect_output(DETECT_OUTPUT)

    assert monitors[0] == Monitor(
        id="PHL:PHL 278E1:@card2-HDMI-A-5",
        display_number=1,
        bus=13,
        connector="card2-HDMI-A-5",
        description="PHL:PHL 278E1:",
    )
    assert monitors[1].bus == 14


def test_parses_mccs_version_and_feature_60_values():
    capabilities = parse_capabilities_output(CAPABILITIES_OUTPUT)

    assert capabilities.mccs_version == "2.2"
    assert capabilities.input_sources == [
        InputSource(0x11, "HDMI-1"),
        InputSource(0x12, "HDMI-2"),
        InputSource(0x0F, "DisplayPort-1"),
    ]


def test_set_input_uses_feature_60_and_current_i2c_bus(monkeypatch):
    ddcutil = Ddcutil()
    run = Mock()
    monkeypatch.setattr(ddcutil, "_run", run)
    monitor = parse_detect_output(DETECT_OUTPUT)[0]

    ddcutil.set_input(monitor, 0x11)

    run.assert_called_once_with("setvcp", "60", "0x11", "--bus", "13")
