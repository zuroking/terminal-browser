import ast
from pathlib import Path
import socket
import ssl
import threading
from typing import cast

import pytest

from tests.support.tls import FixtureTlsContextFactory
from terminal_browser.core.clock import FakeClock
from terminal_browser.core.errors import (
    ConnectionLostError,
    ConnectTimeoutError,
    DnsTimeoutError,
    ReadTimeoutError,
    TlsError,
)
from terminal_browser.core.limits import Limits
from terminal_browser.net.transport import (
    SocketTransport,
    ThreadWaiter,
    TcpTarget,
    TlsPolicy,
)


CERT_DIR = Path(__file__).parent / "certs"
POLICY = TlsPolicy(min_tls_version=ssl.TLSVersion.TLSv1_2)


class TimeoutSocket:
    def __init__(self) -> None:
        self.closed = False
        self.timeout: float | None = None

    def settimeout(self, value: float | None) -> None:
        self.timeout = value

    def connect(self, _address: object) -> None:
        raise socket.timeout("fixture connect timeout")

    def close(self) -> None:
        self.closed = True


class RefusedSocket(TimeoutSocket):
    def connect(self, _address: object) -> None:
        raise ConnectionRefusedError("fixture connection refused")


class AdvancingTimeoutWaiter:
    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock

    def wait(
        self,
        _thread: threading.Thread,
        remaining_sec: float,
    ) -> bool:
        self._clock.advance(remaining_sec)
        return False


def start_server(
    certificate_name: str | None = None,
    response: bytes | None = None,
    stall_after_response: bool = False,
) -> tuple[int, threading.Thread, list[BaseException]]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(4)
    listener.settimeout(2.0)
    errors: list[BaseException] = []
    server_context: ssl.SSLContext | None = None
    if certificate_name is not None:
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.minimum_version = ssl.TLSVersion.TLSv1_2
        server_context.load_cert_chain(
            certfile=str(CERT_DIR / f"{certificate_name}.crt"),
            keyfile=str(CERT_DIR / f"{certificate_name}.key"),
        )

    def serve() -> None:
        connection: socket.socket | None = None
        try:
            raw_connection, _address = listener.accept()
            connection = raw_connection
            connection.settimeout(2.0)
            if server_context is not None:
                connection = server_context.wrap_socket(
                    raw_connection,
                    server_side=True,
                )
            if response is not None:
                connection.sendall(response)
            if stall_after_response:
                connection.recv(1)
        except BaseException as error:
            errors.append(error)
        finally:
            if connection is not None:
                try:
                    connection.close()
                except OSError:
                    pass
            listener.close()

    thread = threading.Thread(target=serve, name="test-listener", daemon=True)
    thread.start()
    return listener.getsockname()[1], thread, errors


def unused_local_port() -> int:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def transport() -> SocketTransport:
    return SocketTransport(Limits.defaults())


def tls_transport() -> SocketTransport:
    return SocketTransport(
        Limits.defaults(),
        context_factory=FixtureTlsContextFactory(CERT_DIR / "ca.crt"),
    )


def connect_local(transport_instance: SocketTransport, port: int) -> socket.socket:
    return transport_instance.connect(
        TcpTarget(host="127.0.0.1", port=port, use_tls=False),
        remaining_sec=1.0,
    )


def test_connect_success_to_local_listener() -> None:
    port, thread, errors = start_server()
    transport_instance = transport()

    sock = connect_local(transport_instance, port)
    transport_instance.close(sock)
    thread.join(timeout=2.0)

    assert not errors


def test_connect_refused_raises_connection_lost() -> None:
    fake_socket = RefusedSocket()
    fake_factory = lambda _family, _type, _protocol: cast(socket.socket, fake_socket)
    transport_instance = SocketTransport(
        Limits.defaults(),
        socket_factory=fake_factory,
    )

    with pytest.raises(ConnectionLostError):
        transport_instance.connect(
            TcpTarget(host="127.0.0.1", port=unused_local_port(), use_tls=False),
            remaining_sec=1.0,
        )


def test_connect_timeout_uses_injected_fake_socket() -> None:
    fake_socket = TimeoutSocket()
    fake_factory = lambda _family, _type, _protocol: cast(socket.socket, fake_socket)
    transport_instance = SocketTransport(
        Limits.defaults(),
        socket_factory=fake_factory,
    )

    with pytest.raises(ConnectTimeoutError):
        transport_instance.connect(
            TcpTarget(host="127.0.0.1", port=9, use_tls=False),
            remaining_sec=0.1,
        )

    assert fake_socket.closed is True


def test_recv_bounded_never_reads_past_max_bytes() -> None:
    port, thread, _errors = start_server(response=b"0123456789")
    transport_instance = transport()
    sock = connect_local(transport_instance, port)

    received = transport_instance.recv_bounded(
        sock,
        max_bytes=4,
        remaining_sec=1.0,
        chunk_size=100,
    )
    transport_instance.close(sock)
    thread.join(timeout=2.0)

    assert received == b"0123"


def test_recv_timeout_uses_real_socket_timeout_without_sleep() -> None:
    port, thread, _errors = start_server(response=b"x", stall_after_response=True)
    clock = FakeClock(monotonic_start=0.0, epoch_start=0.0)
    transport_instance = SocketTransport(Limits.defaults(), clock=clock)
    sock = connect_local(transport_instance, port)

    first = transport_instance.recv_bounded(
        sock,
        max_bytes=4,
        remaining_sec=0.05,
        chunk_size=1,
    )
    assert first == b"x"

    # recv is a real blocking syscall, so FakeClock cannot interrupt it; the
    # short socket timeout is intentional and the fixture uses no time.sleep.
    with pytest.raises(ReadTimeoutError):
        transport_instance.recv_bounded(
            sock,
            max_bytes=4,
            remaining_sec=0.05,
            chunk_size=4,
        )
    transport_instance.close(sock)
    thread.join(timeout=2.0)


def test_tls_handshake_with_valid_fixture_certificate_succeeds() -> None:
    port, thread, _errors = start_server(certificate_name="valid")
    transport_instance = tls_transport()
    target = TcpTarget(host="127.0.0.1", port=port, use_tls=True)
    sock = transport_instance.connect(target, remaining_sec=1.0)

    tls_sock = transport_instance.upgrade_to_tls(sock, target, POLICY, 1.0)
    transport_instance.close(tls_sock)
    thread.join(timeout=2.0)

    assert isinstance(tls_sock, ssl.SSLSocket)


@pytest.mark.parametrize("certificate_name", ("untrusted", "mismatch", "expired"))
def test_tls_handshake_failures_raise_tls_error(certificate_name: str) -> None:
    port, thread, _errors = start_server(certificate_name=certificate_name)
    transport_instance = tls_transport()
    target = TcpTarget(host="127.0.0.1", port=port, use_tls=True)
    sock = transport_instance.connect(target, remaining_sec=1.0)

    with pytest.raises(TlsError):
        transport_instance.upgrade_to_tls(sock, target, POLICY, 1.0)
    transport_instance.close(sock)
    thread.join(timeout=2.0)


def test_close_is_idempotent() -> None:
    port, thread, _errors = start_server()
    transport_instance = transport()
    sock = connect_local(transport_instance, port)

    transport_instance.close(sock)
    transport_instance.close(sock)
    thread.join(timeout=2.0)


def test_dns_resolve_success_returns_addresses() -> None:
    addresses = transport().resolve("127.0.0.1", 80, 1.0)

    assert addresses
    assert any(address[4][0] == "127.0.0.1" for address in addresses)


def test_dns_timeout_uses_fake_clock_and_injected_waiter() -> None:
    clock = FakeClock(monotonic_start=0.0, epoch_start=0.0)
    waiter = AdvancingTimeoutWaiter(clock)
    transport_instance = SocketTransport(
        Limits.defaults(),
        clock=clock,
        thread_waiter=cast(ThreadWaiter, waiter),
    )

    with pytest.raises(DnsTimeoutError):
        transport_instance.resolve("localhost", 80, 1.0)

    assert clock.now_monotonic() == 1.0


def test_tls_policy_rejects_versions_below_tls12() -> None:
    with pytest.raises(ValueError):
        TlsPolicy(min_tls_version=ssl.TLSVersion.TLSv1_1)


def test_transport_models_reject_structurally_removed_fields() -> None:
    with pytest.raises(ValueError):
        TcpTarget(
            host="example.com",
            port=443,
            use_tls=True,
            server_hostname="other.example.com",
        )
    with pytest.raises(ValueError):
        TlsPolicy(
            min_tls_version=ssl.TLSVersion.TLSv1_2,
            verify=False,
        )
    with pytest.raises(ValueError):
        TlsPolicy(
            min_tls_version=ssl.TLSVersion.TLSv1_2,
            check_hostname=False,
        )


def test_transport_source_has_no_forbidden_imports() -> None:
    source_path = (
        Path(__file__).parents[1]
        / "src"
        / "terminal_browser"
        / "net"
        / "transport.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    allowed_modules = {
        "socket",
        "ssl",
        "threading",
        "collections.abc",
        "typing",
        "pydantic",
        "core.clock",
        "core.errors",
        "core.limits",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name in allowed_modules
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module in allowed_modules
