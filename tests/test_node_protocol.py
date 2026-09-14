import base64
import json
import time
from unittest.mock import Mock

import pytest

from logitech_flow_kvm import node_protocol
from logitech_flow_kvm.node_protocol import LIMITED_BROADCAST_ADDRESS
from logitech_flow_kvm.node_protocol import MAX_PADDING_BYTES
from logitech_flow_kvm.node_protocol import MIN_PADDING_BYTES
from logitech_flow_kvm.node_protocol import BroadcastTransport
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


def make_transport(**kwargs) -> tuple[BroadcastTransport, Mock]:
    transport = BroadcastTransport(
        secret="shared", port=24801, on_message=lambda *_a: None, **kwargs
    )
    sock = Mock()
    transport._socket = sock
    return transport, sock


def sent_destinations(sock: Mock) -> set[str]:
    return {call.args[1][0] for call in sock.sendto.call_args_list}


class TestBroadcastTransportSend:
    def test_sends_to_limited_broadcast_when_no_interfaces_found(self, monkeypatch):
        monkeypatch.setattr(
            node_protocol.util, "get_directed_broadcast_addresses", lambda: []
        )
        transport, sock = make_transport()

        transport.send(advertisement())

        assert sent_destinations(sock) == {LIMITED_BROADCAST_ADDRESS}

    def test_also_sends_to_each_directed_broadcast_address(self, monkeypatch):
        monkeypatch.setattr(
            node_protocol.util,
            "get_directed_broadcast_addresses",
            lambda: ["192.168.2.255", "10.0.0.255"],
        )
        transport, sock = make_transport()

        transport.send(advertisement())

        assert sent_destinations(sock) == {
            LIMITED_BROADCAST_ADDRESS,
            "192.168.2.255",
            "10.0.0.255",
        }

    def test_deduplicates_destinations(self, monkeypatch):
        monkeypatch.setattr(
            node_protocol.util,
            "get_directed_broadcast_addresses",
            lambda: [LIMITED_BROADCAST_ADDRESS, "192.168.2.255", "192.168.2.255"],
        )
        transport, sock = make_transport()

        transport.send(advertisement())

        assert sock.sendto.call_count == 2

    def test_records_the_destinations_it_tried(self, monkeypatch):
        monkeypatch.setattr(
            node_protocol.util,
            "get_directed_broadcast_addresses",
            lambda: ["192.168.2.255"],
        )
        transport, _sock = make_transport()

        transport.send(advertisement())

        assert transport.last_destinations == [
            "192.168.2.255",
            LIMITED_BROADCAST_ADDRESS,
        ]

    def test_a_failed_destination_does_not_stop_the_others(self, monkeypatch):
        monkeypatch.setattr(
            node_protocol.util,
            "get_directed_broadcast_addresses",
            lambda: ["192.168.2.255"],
        )
        errors = []
        transport, sock = make_transport(
            on_send_error=lambda destination, error: errors.append((destination, error))
        )
        sock.sendto.side_effect = [OSError("unreachable"), None]

        transport.send(advertisement())

        assert sock.sendto.call_count == 2
        assert errors == [("192.168.2.255", errors[0][1])]
        assert isinstance(errors[0][1], OSError)

    def test_send_error_without_a_callback_does_not_raise(self, monkeypatch):
        monkeypatch.setattr(
            node_protocol.util, "get_directed_broadcast_addresses", lambda: []
        )
        transport, sock = make_transport()
        sock.sendto.side_effect = OSError("unreachable")

        transport.send(advertisement())

    def test_caches_destinations_within_the_ttl(self, monkeypatch):
        calls = []

        def fake_get_directed_broadcast_addresses():
            calls.append(1)
            return ["192.168.2.255"]

        monkeypatch.setattr(
            node_protocol.util,
            "get_directed_broadcast_addresses",
            fake_get_directed_broadcast_addresses,
        )
        times = iter([0.0, 1.0, 40.0])
        monkeypatch.setattr(time, "monotonic", lambda: next(times))
        transport, _sock = make_transport()

        transport.send(advertisement())
        transport.send(advertisement())
        transport.send(advertisement())

        assert len(calls) == 2

    def test_enumeration_failure_falls_back_to_limited_broadcast(self, monkeypatch):
        def raise_error():
            raise OSError("enumeration failed")

        monkeypatch.setattr(
            node_protocol.util, "get_directed_broadcast_addresses", raise_error
        )
        transport, sock = make_transport()

        transport.send(advertisement())

        assert sent_destinations(sock) == {LIMITED_BROADCAST_ADDRESS}
