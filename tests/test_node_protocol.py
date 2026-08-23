import base64
import json

import pytest

from logitech_flow_kvm.node_protocol import MAX_PADDING_BYTES
from logitech_flow_kvm.node_protocol import MIN_PADDING_BYTES
from logitech_flow_kvm.node_protocol import DecodedPacket
from logitech_flow_kvm.node_protocol import DeviceAdvertisement
from logitech_flow_kvm.node_protocol import NodeAdvertisement
from logitech_flow_kvm.node_protocol import ReplayGuard
from logitech_flow_kvm.node_protocol import ReplayRejected
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


def test_packet_contains_random_length_encrypted_padding(monkeypatch):
    monkeypatch.setattr("secrets.randbelow", lambda _limit: 0)
    shortest = encode_packet(advertisement(), "shared")
    monkeypatch.setattr(
        "secrets.randbelow",
        lambda _limit: MAX_PADDING_BYTES - MIN_PADDING_BYTES,
    )
    longest = encode_packet(advertisement(), "shared")

    shortest_ciphertext = base64.b64decode(json.loads(shortest)["ciphertext"])
    longest_ciphertext = base64.b64decode(json.loads(longest)["ciphertext"])
    assert len(longest_ciphertext) > len(shortest_ciphertext)
    assert b"padding" not in shortest
    assert decode_packet(shortest, "shared") == advertisement()
    assert decode_packet(longest, "shared") == advertisement()


def decoded_packet(
    *,
    message_id: str = "00000000-0000-0000-0000-000000000001",
    sent_at: float = 100.0,
) -> DecodedPacket:
    return DecodedPacket(message_id, sent_at, advertisement())


def test_replay_guard_rejects_duplicate_packet():
    guard = ReplayGuard()
    packet = decoded_packet()

    guard.accept(packet, now=100.0)
    with pytest.raises(ReplayRejected, match="already been received"):
        guard.accept(packet, now=101.0)


@pytest.mark.parametrize(
    ("sent_at", "message"),
    [
        (69.9, "too old"),
        (105.1, "too far in the future"),
    ],
)
def test_replay_guard_rejects_packet_outside_time_window(sent_at, message):
    with pytest.raises(ReplayRejected, match=message):
        ReplayGuard().accept(decoded_packet(sent_at=sent_at), now=100.0)


def test_replay_guard_expires_cache_entries():
    guard = ReplayGuard(cache_ttl=60.0)
    first = decoded_packet(sent_at=100.0)
    guard.accept(first, now=100.0)

    # The timestamp window remains the primary protection after cache expiry.
    with pytest.raises(ReplayRejected, match="too old"):
        guard.accept(first, now=161.0)
