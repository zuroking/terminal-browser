import socket
import ssl
import threading
from collections.abc import Callable
from typing import Protocol, Self, cast

from pydantic import BaseModel, ConfigDict, model_validator

from ..core.clock import Clock, SystemClock
from ..core.errors import (
    ConnectionLostError,
    ConnectTimeoutError,
    DnsError,
    DnsTimeoutError,
    ReadTimeoutError,
    TlsError,
)
from ..core.limits import Limits


class TcpTarget(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    host: str
    port: int
    use_tls: bool


class TlsPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    min_tls_version: ssl.TLSVersion

    @model_validator(mode="after")
    def validate_minimum_version(self) -> Self:
        if self.min_tls_version < ssl.TLSVersion.TLSv1_2:
            raise ValueError("TLS 1.2 is the minimum permitted version")
        return self


class TlsContextFactory(Protocol):
    def create(self, policy: TlsPolicy) -> ssl.SSLContext: ...


class ThreadWaiter(Protocol):
    def wait(
        self,
        thread: threading.Thread,
        remaining_sec: float,
    ) -> bool: ...


class Transport(Protocol):
    def resolve(
        self,
        host: str,
        port: int,
        dns_timeout_sec: float,
    ) -> list[socket.AddressInfo]: ...

    def connect(
        self,
        target: TcpTarget,
        remaining_sec: float,
    ) -> socket.socket: ...

    def upgrade_to_tls(
        self,
        sock: socket.socket,
        target: TcpTarget,
        policy: TlsPolicy,
        remaining_sec: float,
    ) -> ssl.SSLSocket: ...

    def send_all(
        self,
        sock: socket.socket,
        data: bytes,
        remaining_sec: float,
    ) -> None: ...

    def recv_bounded(
        self,
        sock: socket.socket,
        max_bytes: int,
        remaining_sec: float,
        chunk_size: int,
    ) -> bytes: ...

    def close(self, sock: socket.socket) -> None: ...


ResolvedAddress = tuple[
    socket.AddressFamily,
    socket.SocketKind,
    int,
    str,
    tuple[str, int] | tuple[str, int, int, int] | tuple[int, bytes],
]
SocketFactory = Callable[[socket.AddressFamily, socket.SocketKind, int], socket.socket]


class DefaultTlsContextFactory:
    def create(self, policy: TlsPolicy) -> ssl.SSLContext:
        context = ssl.create_default_context()
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        context.minimum_version = policy.min_tls_version
        return context


class DefaultThreadWaiter:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    def wait(
        self,
        thread: threading.Thread,
        remaining_sec: float,
    ) -> bool:
        if remaining_sec <= 0:
            return not thread.is_alive()
        deadline = self._clock.now_monotonic() + remaining_sec
        while thread.is_alive():
            current = self._clock.now_monotonic()
            if current >= deadline:
                return False
            thread.join(min(0.05, deadline - current))
        return True


class SocketTransport:
    def __init__(
        self,
        limits: Limits,
        clock: Clock | None = None,
        context_factory: TlsContextFactory | None = None,
        thread_waiter: ThreadWaiter | None = None,
        socket_factory: SocketFactory | None = None,
    ) -> None:
        self._limits = limits
        self._clock = clock or SystemClock()
        self._context_factory = context_factory or DefaultTlsContextFactory()
        self._thread_waiter = thread_waiter or DefaultThreadWaiter(self._clock)
        self._socket_factory = socket_factory or socket.socket

    def resolve(
        self,
        host: str,
        port: int,
        dns_timeout_sec: float,
    ) -> list[socket.AddressInfo]:
        if dns_timeout_sec <= 0:
            raise DnsTimeoutError("DNS resolution deadline exhausted")
        addresses: list[ResolvedAddress] = []
        failures: list[BaseException] = []

        def resolve_addresses() -> None:
            try:
                addresses.extend(
                    socket.getaddrinfo(
                        host,
                        port,
                        type=socket.SOCK_STREAM,
                    )
                )
            except BaseException as error:
                failures.append(error)

        thread = threading.Thread(
            target=resolve_addresses,
            name="terminal-browser-dns",
            daemon=True,
        )
        thread.start()
        if not self._thread_waiter.wait(thread, dns_timeout_sec):
            # The daemon resolver may still be running after timeout, but owns no socket or connection.
            raise DnsTimeoutError("DNS resolution timed out")
        if failures:
            raise DnsError("DNS resolution failed") from failures[0]
        return cast(list[socket.AddressInfo], addresses)

    def connect(
        self,
        target: TcpTarget,
        remaining_sec: float,
    ) -> socket.socket:
        if remaining_sec <= 0:
            raise ConnectTimeoutError("TCP connection deadline exhausted")
        operation_timeout = min(remaining_sec, self._limits.connect_timeout_sec)
        deadline = self._clock.now_monotonic() + operation_timeout
        addresses = cast(
            list[ResolvedAddress],
            self.resolve(
                target.host,
                target.port,
                min(remaining_sec, self._limits.dns_timeout_sec),
            ),
        )
        last_timeout = False
        last_error: OSError | None = None
        for family, socket_type, protocol, _canonical_name, address in addresses:
            current = deadline - self._clock.now_monotonic()
            if current <= 0:
                raise ConnectTimeoutError("TCP connection timed out")
            sock = self._socket_factory(family, socket_type, protocol)
            try:
                sock.settimeout(current)
                sock.connect(address)
                return sock
            except socket.timeout as error:
                last_timeout = True
                last_error = error
                self.close(sock)
            except OSError as error:
                last_error = error
                self.close(sock)
        if last_timeout and last_error is not None:
            raise ConnectTimeoutError("TCP connection timed out") from last_error
        raise ConnectionLostError("TCP connection failed") from last_error

    def upgrade_to_tls(
        self,
        sock: socket.socket,
        target: TcpTarget,
        policy: TlsPolicy,
        remaining_sec: float,
    ) -> ssl.SSLSocket:
        if remaining_sec <= 0:
            raise TlsError("TLS handshake deadline exhausted")
        if not target.use_tls:
            raise TlsError("TLS upgrade requested for a non-TLS target")
        context = self._context_factory.create(policy)
        try:
            context.minimum_version = policy.min_tls_version
            deadline = self._clock.now_monotonic() + remaining_sec
            sock.settimeout(remaining_sec)
            tls_sock = context.wrap_socket(
                sock,
                server_hostname=target.host,
                do_handshake_on_connect=False,
            )
            current = deadline - self._clock.now_monotonic()
            if current <= 0:
                raise TlsError("TLS handshake deadline exhausted")
            tls_sock.settimeout(current)
            tls_sock.do_handshake()
            return tls_sock
        except TlsError:
            raise
        except (OSError, ssl.SSLError, ValueError) as error:
            raise TlsError("TLS handshake or verification failed") from error

    def send_all(
        self,
        sock: socket.socket,
        data: bytes,
        remaining_sec: float,
    ) -> None:
        if remaining_sec <= 0:
            raise ReadTimeoutError("send deadline exhausted")
        deadline = self._clock.now_monotonic() + remaining_sec
        remaining_data = memoryview(data)
        while remaining_data:
            current = deadline - self._clock.now_monotonic()
            if current <= 0:
                raise ReadTimeoutError("send timed out")
            sock.settimeout(current)
            try:
                sent = sock.send(remaining_data)
            except socket.timeout as error:
                raise ReadTimeoutError("send timed out") from error
            except OSError as error:
                raise ConnectionLostError("connection lost while sending") from error
            if sent <= 0:
                raise ConnectionLostError("connection closed while sending")
            remaining_data = remaining_data[sent:]

    def recv_bounded(
        self,
        sock: socket.socket,
        max_bytes: int,
        remaining_sec: float,
        chunk_size: int,
    ) -> bytes:
        # remaining_sec is FakeClock-driven everywhere except this blocking recv, which uses a real short socket.settimeout because a blocking syscall cannot be advanced by a fake clock.
        if max_bytes <= 0:
            return b""
        if remaining_sec <= 0:
            raise ReadTimeoutError("receive deadline exhausted")
        read_size = min(max_bytes, max(1, chunk_size))
        sock.settimeout(remaining_sec)
        try:
            return sock.recv(read_size)
        except socket.timeout as error:
            raise ReadTimeoutError("receive timed out") from error
        except OSError as error:
            raise ConnectionLostError("connection lost while receiving") from error

    def close(self, sock: socket.socket) -> None:
        try:
            sock.close()
        except OSError:
            return

