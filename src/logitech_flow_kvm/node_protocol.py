import base64
import hashlib
import json
import math
import os
import secrets
import socket
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import asdict
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PROTOCOL_VERSION = 1
MAX_PACKET_SIZE = 65507
MIN_PADDING_BYTES = 256
MAX_PADDING_BYTES = 1024
MAX_PACKET_AGE_SECONDS = 30.0
MAX_FUTURE_SKEW_SECONDS = 5.0
REPLAY_CACHE_TTL_SECONDS = 60.0
MAX_REPLAY_CACHE_ENTRIES = 4096


@dataclass(frozen=True)
class DeviceAdvertisement:
    id: str
    product: str
    name: str
    kind: str
    connected: bool


@dataclass(frozen=True)
class NodeAdvertisement:
    node_id: str
    hostname: str
    host_number: int
    devices: list[DeviceAdvertisement]
    leader_id: str
    target_host: int | None = None
    clipboard: str | None = None


@dataclass(frozen=True)
class DecodedPacket:
    message_id: str
    sent_at: float
    advertisement: NodeAdvertisement


class ReplayRejected(ValueError):
    """An authenticated packet was stale, premature, or already received."""


class ReplayGuard:
    def __init__(
        self,
        *,
        max_age: float = MAX_PACKET_AGE_SECONDS,
        max_future_skew: float = MAX_FUTURE_SKEW_SECONDS,
        cache_ttl: float = REPLAY_CACHE_TTL_SECONDS,
        max_entries: int = MAX_REPLAY_CACHE_ENTRIES,
    ):
        self.max_age = max_age
        self.max_future_skew = max_future_skew
        self.cache_ttl = cache_ttl
        self.max_entries = max_entries
        self._seen: OrderedDict[str, float] = OrderedDict()

    def accept(self, packet: DecodedPacket, *, now: float | None = None) -> None:
        current_time = time.time() if now is None else now
        while self._seen:
            _, expires_at = next(iter(self._seen.items()))
            if expires_at > current_time:
                break
            self._seen.popitem(last=False)

        if packet.sent_at < current_time - self.max_age:
            raise ReplayRejected("packet is too old")
        if packet.sent_at > current_time + self.max_future_skew:
            raise ReplayRejected("packet timestamp is too far in the future")
        if packet.message_id in self._seen:
            raise ReplayRejected("packet has already been received")

        self._seen[packet.message_id] = current_time + self.cache_ttl
        while len(self._seen) > self.max_entries:
            self._seen.popitem(last=False)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def encode_packet(advertisement: NodeAdvertisement, secret: str) -> bytes:
    padding_size = MIN_PADDING_BYTES + secrets.randbelow(
        MAX_PADDING_BYTES - MIN_PADDING_BYTES + 1
    )
    body = {
        "version": PROTOCOL_VERSION,
        "message_id": str(uuid.uuid4()),
        "sent_at": time.time(),
        "advertisement": asdict(advertisement),
        # Keep padding inside the authenticated ciphertext so it cannot be
        # stripped or changed and its contents do not reveal a packet marker.
        "padding": base64.b64encode(os.urandom(padding_size)).decode(),
    }
    nonce = os.urandom(12)
    key = hashlib.sha256(secret.encode()).digest()
    ciphertext = AESGCM(key).encrypt(
        nonce, _canonical_json(body), f"logitech-flow-kvm:{PROTOCOL_VERSION}".encode()
    )
    packet = {
        "version": PROTOCOL_VERSION,
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
    }
    return _canonical_json(packet)


def _decode_packet(data: bytes, secret: str) -> DecodedPacket:
    packet = json.loads(data)
    if packet.get("version") != PROTOCOL_VERSION:
        raise ValueError(f"unsupported protocol version: {packet.get('version')}")
    key = hashlib.sha256(secret.encode()).digest()
    try:
        plaintext = AESGCM(key).decrypt(
            base64.b64decode(packet["nonce"]),
            base64.b64decode(packet["ciphertext"]),
            f"logitech-flow-kvm:{PROTOCOL_VERSION}".encode(),
        )
    except (InvalidTag, ValueError, KeyError) as error:
        raise ValueError(
            "packet authentication failed (shared secrets differ)"
        ) from error
    body = json.loads(plaintext)
    if body.get("version") != PROTOCOL_VERSION:
        raise ValueError(f"unsupported inner protocol version: {body.get('version')}")
    message_id = str(body["message_id"])
    if str(uuid.UUID(message_id)) != message_id:
        raise ValueError("invalid message ID")
    sent_at = float(body["sent_at"])
    if not math.isfinite(sent_at):
        raise ValueError("invalid packet timestamp")
    advertised = body["advertisement"]
    return DecodedPacket(
        message_id=message_id,
        sent_at=sent_at,
        advertisement=NodeAdvertisement(
            node_id=str(advertised["node_id"]),
            hostname=str(advertised["hostname"]),
            host_number=int(advertised["host_number"]),
            devices=[DeviceAdvertisement(**device) for device in advertised["devices"]],
            leader_id=str(advertised["leader_id"]),
            target_host=(
                int(advertised["target_host"])
                if advertised.get("target_host") is not None
                else None
            ),
            clipboard=(
                str(advertised["clipboard"])
                if advertised.get("clipboard") is not None
                else None
            ),
        ),
    )


def decode_packet(data: bytes, secret: str) -> NodeAdvertisement:
    return _decode_packet(data, secret).advertisement


class BroadcastTransport:
    def __init__(
        self,
        *,
        secret: str,
        port: int,
        on_message: Callable[[NodeAdvertisement, str], None],
        on_invalid_packet: Callable[[str, Exception], None] | None = None,
    ):
        self.secret = secret
        self.port = port
        self.on_message = on_message
        self.on_invalid_packet = on_invalid_packet
        self._stop = threading.Event()
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._replay_guard = ReplayGuard()

    def start(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", self.port))
        sock.settimeout(1.0)
        self._socket = sock
        self._thread = threading.Thread(target=self._receive, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._socket is not None:
            self._socket.close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def send(self, advertisement: NodeAdvertisement) -> None:
        if self._socket is None:
            raise RuntimeError("broadcast transport has not been started")
        packet = encode_packet(advertisement, self.secret)
        if len(packet) > MAX_PACKET_SIZE:
            raise ValueError(
                f"broadcast is {len(packet)} bytes; maximum is {MAX_PACKET_SIZE}"
            )
        self._socket.sendto(packet, ("255.255.255.255", self.port))

    def _receive(self) -> None:
        assert self._socket is not None
        while not self._stop.is_set():
            try:
                data, address = self._socket.recvfrom(MAX_PACKET_SIZE)
                packet = _decode_packet(data, self.secret)
                self._replay_guard.accept(packet)
            except TimeoutError:
                continue
            except OSError:
                if not self._stop.is_set():
                    raise
                return
            except ReplayRejected:
                continue
            except Exception as error:
                if self.on_invalid_packet is not None:
                    self.on_invalid_packet(address[0], error)
                continue
            self.on_message(packet.advertisement, address[0])
