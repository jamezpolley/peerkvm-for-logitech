import logging
import re
import shutil
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DDCUTIL_TIMEOUT = 30.0


class DdcutilError(RuntimeError):
    pass


@dataclass(frozen=True)
class Monitor:
    id: str
    display_number: int
    bus: int
    connector: str
    description: str


@dataclass(frozen=True)
class InputSource:
    value: int
    name: str


@dataclass(frozen=True)
class MonitorCapabilities:
    mccs_version: str
    input_sources: list[InputSource]


def parse_detect_output(output: str) -> list[Monitor]:
    monitors: list[Monitor] = []
    blocks = re.split(r"(?=^Display\s+\d+\s*$)", output, flags=re.MULTILINE)
    for block in blocks:
        display_match = re.search(r"^Display\s+(\d+)\s*$", block, re.MULTILINE)
        bus_match = re.search(r"I2C bus:\s*/dev/i2c-(\d+)", block)
        if display_match is None or bus_match is None:
            continue
        connector_match = re.search(r"DRM connector:\s*(\S+)", block)
        monitor_match = re.search(r"Monitor:\s*(.*?)\s*$", block, re.MULTILINE)
        connector = connector_match.group(1) if connector_match else "unknown"
        description = monitor_match.group(1) if monitor_match else "Unknown monitor"
        monitor_id = f"{description}@{connector}"
        monitors.append(
            Monitor(
                id=monitor_id,
                display_number=int(display_match.group(1)),
                bus=int(bus_match.group(1)),
                connector=connector,
                description=description,
            )
        )
    return monitors


def parse_capabilities_output(output: str) -> MonitorCapabilities:
    version_match = re.search(r"^MCCS version:\s*(\S+)", output, re.MULTILINE)
    version = version_match.group(1) if version_match else "unknown"
    feature_match = re.search(
        r"^\s*Feature:\s*60\s*\(Input Source\)(.*?)(?=^\s*Feature:|\Z)",
        output,
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if feature_match is None:
        return MonitorCapabilities(version, [])
    feature = feature_match.group(1)
    parsed_match = re.search(
        r"Values\s*\(\s*parsed\):\s*\n(.*?)(?=^\s*Feature:|\Z)",
        feature,
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    sources: list[InputSource] = []
    if parsed_match is not None:
        for value, name in re.findall(
            r"^\s*([0-9a-fA-F]{2}):\s*(.+?)\s*$",
            parsed_match.group(1),
            re.MULTILINE,
        ):
            sources.append(InputSource(int(value, 16), name))
    if sources:
        return MonitorCapabilities(version, sources)
    unparsed_match = re.search(
        r"Values\s*\(unparsed\):\s*([0-9a-fA-F ]+)", feature, re.IGNORECASE
    )
    if unparsed_match is not None:
        sources = [
            InputSource(int(value, 16), f"Input 0x{value.lower()}")
            for value in unparsed_match.group(1).split()
        ]
    return MonitorCapabilities(version, sources)


class Ddcutil:
    def __init__(self, executable: str = "ddcutil"):
        self.executable = executable

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def detect(self) -> list[Monitor]:
        if not self.available():
            raise DdcutilError("ddcutil is not installed or not in PATH")
        result = self._run("detect", "--brief")
        monitors = parse_detect_output(result.stdout)
        if not monitors and result.stderr.strip():
            raise DdcutilError(result.stderr.strip())
        return monitors

    def capabilities(self, monitor: Monitor) -> MonitorCapabilities:
        result = self._run("capabilities", "--bus", str(monitor.bus), "--verbose")
        capabilities = parse_capabilities_output(result.stdout)
        if not capabilities.input_sources:
            detail = result.stderr.strip() or "Feature 0x60 has no advertised values"
            raise DdcutilError(f"{monitor.description}: {detail}")
        return capabilities

    def set_input(self, monitor: Monitor, value: int) -> None:
        self._run("setvcp", "60", f"0x{value:02x}", "--bus", str(monitor.bus))

    def _run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [self.executable, *arguments],
                capture_output=True,
                text=True,
                check=True,
                timeout=DDCUTIL_TIMEOUT,
            )
        except FileNotFoundError as error:
            raise DdcutilError("ddcutil is not installed or not in PATH") from error
        except subprocess.TimeoutExpired as error:
            raise DdcutilError(
                f"ddcutil {' '.join(arguments)} timed out after {DDCUTIL_TIMEOUT:g}s"
            ) from error
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or error.stdout or str(error)).strip()
            raise DdcutilError(detail) from error
