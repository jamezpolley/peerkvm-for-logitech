import base64
import hashlib
import json
import os
import socket
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PROTOCOL_VERSION = 1
MAX_PACKET_SIZE = 65507


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


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def encode_packet(advertisement: NodeAdvertisement, secret: str) -> bytes:
    body = {
        "version": PROTOCOL_VERSION,
        "message_id": str(uuid.uuid4()),
        "sent_at": time.time(),
        "advertisement": asdict(advertisement),
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


def decode_packet(data: bytes, secret: str) -> NodeAdvertisement:
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
    advertised = body["advertisement"]
    return NodeAdvertisement(
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
    )


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
                message = decode_packet(data, self.secret)
            except TimeoutError:
                continue
            except OSError:
                if not self._stop.is_set():
                    raise
                return
            except Exception as error:
                if self.on_invalid_packet is not None:
                    self.on_invalid_packet(address[0], error)
                continue
            self.on_message(message, address[0])
