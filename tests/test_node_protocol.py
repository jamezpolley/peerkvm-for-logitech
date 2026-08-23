import pytest

from logitech_flow_kvm.node_protocol import DeviceAdvertisement
from logitech_flow_kvm.node_protocol import NodeAdvertisement
from logitech_flow_kvm.node_protocol import decode_packet
from logitech_flow_kvm.node_protocol import encode_packet


def advertisement() -> NodeAdvertisement:
    return NodeAdvertisement(
        node_id="alder",
        hostname="alder",
        host_number=2,
        devices=[DeviceAdvertisement("ABC", "1234", "Mouse", "mouse", True)],
        leader_id="KEYS",
        target_host=2,
    )


def test_authenticated_packet_round_trip():
    encoded = encode_packet(advertisement(), "shared")
    assert b"Mouse" not in encoded
    assert decode_packet(encoded, "shared") == advertisement()


def test_wrong_secret_is_reported_clearly():
    with pytest.raises(ValueError, match="shared secrets differ"):
        decode_packet(encode_packet(advertisement(), "correct"), "wrong")
