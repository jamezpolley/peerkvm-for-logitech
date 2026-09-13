import glob
import os

from .models import DirectDeviceInfo
from .models import ReceiverInfo

LOGITECH_VENDOR_ID = 0x046D

# Product IDs of receivers known to speak HID++ over a hidraw interface.
# See base_usb.py in solaar's logitech_receiver package for the authoritative list;
# these are the two kinds this project has been tested against.
KNOWN_RECEIVERS: dict[int, str] = {
    0xC548: "bolt",
    0xC52B: "unifying",
}

# Both known receiver kinds expose their HID++ interface on this USB interface number.
HIDPP_USB_INTERFACE = 2

HIDRAW_SYSFS_GLOB = "/sys/class/hidraw/hidraw*"
BLUETOOTH_BUS_ID = 0x0005


def _read_uevent(uevent_path: str) -> dict[str, str]:
    try:
        with open(uevent_path) as f:
            return dict(line.strip().split("=", 1) for line in f if "=" in line)
    except OSError:
        return {}


def _parse_interface_number(hid_phys: str) -> int | None:
    if "/input" not in hid_phys:
        return None
    tail = hid_phys.rsplit("/input", 1)[1]
    digits = ""
    for ch in tail:
        if not ch.isdigit():
            break
        digits += ch
    return int(digits) if digits else None


def find_receivers() -> list[ReceiverInfo]:
    """Enumerate Logitech receivers attached to the system via sysfs.

    No `pyudev` dependency: `/sys/class/hidraw/hidraw*/device/uevent` already
    exposes the vendor/product ID (`HID_ID`) and the USB interface number
    (embedded in `HID_PHYS`) that solaar's `hidapi.udev` module gets from pyudev.
    """
    found = []
    for node in sorted(glob.glob(HIDRAW_SYSFS_GLOB)):
        uevent = _read_uevent(os.path.join(node, "device", "uevent"))

        hid_id = uevent.get("HID_ID")
        if not hid_id:
            continue
        _bus, vendor_hex, product_hex = hid_id.split(":")
        vendor = int(vendor_hex, 16)
        product = int(product_hex, 16) & 0xFFFF
        if vendor != LOGITECH_VENDOR_ID or product not in KNOWN_RECEIVERS:
            continue

        interface = _parse_interface_number(uevent.get("HID_PHYS", ""))
        if interface != HIDPP_USB_INTERFACE:
            continue

        found.append(
            ReceiverInfo(
                path=f"/dev/{os.path.basename(node)}",
                product_id=product,
                kind=KNOWN_RECEIVERS[product],
                interface=interface,
            )
        )

    return found


def find_direct_devices() -> list[DirectDeviceInfo]:
    """Enumerate directly-connected Logitech Bluetooth HID++ devices.

    HID++ traffic needs a vendor report exposed by the device.  Bluetooth
    devices generally expose only the long (0x11) report, so reject ordinary
    Logitech HID devices that do not advertise it.
    """
    found = []
    for node in sorted(glob.glob(HIDRAW_SYSFS_GLOB)):
        device_dir = os.path.join(node, "device")
        uevent = _read_uevent(os.path.join(device_dir, "uevent"))
        hid_id = uevent.get("HID_ID")
        if not hid_id:
            continue
        try:
            bus_hex, vendor_hex, product_hex = hid_id.split(":")
            bus = int(bus_hex, 16)
            vendor = int(vendor_hex, 16)
            product = int(product_hex, 16) & 0xFFFF
        except ValueError:
            continue
        if bus != BLUETOOTH_BUS_ID or vendor != LOGITECH_VENDOR_ID:
            continue

        try:
            with open(os.path.join(device_dir, "report_descriptor"), "rb") as f:
                descriptor = f.read()
        except OSError:
            continue
        if b"\x85\x11" not in descriptor:
            continue

        found.append(
            DirectDeviceInfo(
                path=f"/dev/{os.path.basename(node)}",
                product_id=product,
                name=uevent.get("HID_NAME"),
                serial=uevent.get("HID_UNIQ") or None,
                bus_id=bus,
                hidpp_long=True,
            )
        )
    return found
