# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import datetime
import gzip
import http.client
import http.server
import socket
import ssl
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import pytest_mock
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from requests.utils import DEFAULT_CA_BUNDLE_PATH
from urllib3.exceptions import NewConnectionError

from dd_license_attribution.utils.pinned_https import (
    PinnedHTTPSConnection,
    _ca_bundle_kwargs,
    stream_pinned_https_once,
)

RESOLVER = "dd_license_attribution.utils.pinned_https.resolve_host_ips"
CREATE_CONNECTION = (
    "dd_license_attribution.utils.pinned_https.urllib3_connection.create_connection"
)


def _write_test_pki(directory: Path) -> tuple[Path, Path, Path]:
    """Create a CA and a leaf certificate for `pinned.test`; return (ca, leaf cert, leaf key) paths."""
    now = datetime.datetime.now(datetime.timezone.utc)
    validity = (now - datetime.timedelta(days=1), now + datetime.timedelta(days=1))
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ddla test CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(validity[0])
        .not_valid_after(validity[1])
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    leaf_cert = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "pinned.test")])
        )
        .issuer_name(ca_name)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(validity[0])
        .not_valid_after(validity[1])
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("pinned.test")]), critical=False
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    ca_path = directory / "ca.pem"
    cert_path = directory / "leaf.pem"
    key_path = directory / "leaf.key"
    ca_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    cert_path.write_bytes(leaf_cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        leaf_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return ca_path, cert_path, key_path


class _TLSServer:
    """Local HTTPS server whose handler behavior is set per test; records requests and bytes written."""

    def __init__(self, cert: Path, key: Path) -> None:
        self.requests: list[tuple[str, dict[str, str]]] = []
        self.bytes_written = 0
        self.handler_done = threading.Event()
        self.respond: Callable[[http.server.BaseHTTPRequestHandler], None] = (
            lambda handler: None
        )
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:
                server.requests.append((self.path, dict(self.headers.items())))
                try:
                    server.respond(self)
                finally:
                    server.handler_done.set()

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        self.httpd.socket = context.wrap_socket(self.httpd.socket, server_side=True)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def write(self, handler: http.server.BaseHTTPRequestHandler, data: bytes) -> None:
        handler.wfile.write(data)
        self.bytes_written += len(data)

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def tls_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[_TLSServer]:
    ca_path, cert_path, key_path = _write_test_pki(tmp_path)
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(ca_path))
    server = _TLSServer(cert_path, key_path)
    try:
        yield server
    finally:
        server.close()


def _allow_loopback(ip: str) -> bool:
    return ip == "127.0.0.1"


def test_stream_connects_to_validated_address_and_verifies_tls_hostname(
    tls_server: _TLSServer,
    mocker: pytest_mock.MockFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    netrc = tmp_path / "netrc"
    netrc.write_text("machine pinned.test login user password secret\n")
    monkeypatch.setenv("NETRC", str(netrc))
    mock_resolve = mocker.patch(RESOLVER, return_value=["127.0.0.1"])
    body = (
        b'<meta name="go-import" content="pinned.test/pkg git https://github.com/o/r">'
    )

    def respond(handler: http.server.BaseHTTPRequestHandler) -> None:
        handler.send_response(404)
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        tls_server.write(handler, body)

    tls_server.respond = respond
    url = f"https://pinned.test:{tls_server.port}/pkg?go-get=1"

    with stream_pinned_https_once(
        url, {"User-Agent": "test-agent"}, 16, _allow_loopback
    ) as (status, headers, chunks):
        assert status == 404
        assert headers["content-length"] == str(len(body))
        assert b"".join(chunks) == body

    mock_resolve.assert_called_once_with("pinned.test", tls_server.port)
    [(path, request_headers)] = tls_server.requests
    assert path == "/pkg?go-get=1"
    assert request_headers["Host"] == f"pinned.test:{tls_server.port}"
    assert request_headers["User-Agent"] == "test-agent"
    assert "Authorization" not in request_headers


def test_stream_rejects_certificate_for_another_hostname(
    tls_server: _TLSServer, mocker: pytest_mock.MockFixture
) -> None:
    mocker.patch(RESOLVER, return_value=["127.0.0.1"])

    with pytest.raises(OSError, match="Failed to download https://wrong.test"):
        with stream_pinned_https_once(
            f"https://wrong.test:{tls_server.port}/pkg", {}, 16, _allow_loopback
        ):
            pass
    assert tls_server.requests == []


def test_stream_refuses_rejected_address_without_connecting(
    tls_server: _TLSServer, mocker: pytest_mock.MockFixture
) -> None:
    mocker.patch(RESOLVER, return_value=["127.0.0.1"])
    mock_create = mocker.patch(CREATE_CONNECTION)

    with pytest.raises(OSError, match="Refusing to connect to pinned.test"):
        with stream_pinned_https_once(
            f"https://pinned.test:{tls_server.port}/pkg", {}, 16, lambda ip: False
        ):
            pass
    mock_create.assert_not_called()
    assert tls_server.requests == []


def test_leaving_redirect_response_does_not_read_its_body(
    tls_server: _TLSServer, mocker: pytest_mock.MockFixture
) -> None:
    mocker.patch(RESOLVER, return_value=["127.0.0.1"])
    body_size = 32 * 1024 * 1024
    block = b"x" * 65536

    def respond(handler: http.server.BaseHTTPRequestHandler) -> None:
        handler.send_response(302)
        handler.send_header("Location", "/next")
        handler.send_header("Content-Length", str(body_size))
        handler.end_headers()
        try:
            for _ in range(body_size // len(block)):
                tls_server.write(handler, block)
        except OSError:
            pass

    tls_server.respond = respond

    with stream_pinned_https_once(
        f"https://pinned.test:{tls_server.port}/pkg", {}, 16, _allow_loopback
    ) as (status, headers, _):
        assert status == 302
        assert headers["location"] == "/next"

    assert tls_server.handler_done.wait(timeout=10)
    assert tls_server.bytes_written < body_size // 2


def test_stream_wraps_truncated_body_errors(
    tls_server: _TLSServer, mocker: pytest_mock.MockFixture
) -> None:
    mocker.patch(RESOLVER, return_value=["127.0.0.1"])

    def respond(handler: http.server.BaseHTTPRequestHandler) -> None:
        handler.send_response(200)
        handler.send_header("Content-Length", "100")
        handler.end_headers()
        tls_server.write(handler, b"short")
        handler.close_connection = True

    tls_server.respond = respond

    with pytest.raises(OSError, match="Failed to download https://pinned.test"):
        with stream_pinned_https_once(
            f"https://pinned.test:{tls_server.port}/pkg", {}, 16, _allow_loopback
        ) as (_, _, chunks):
            b"".join(chunks)


@pytest.mark.parametrize(
    "url", ["http://pinned.test/pkg", "https:///pkg", "ftp://pinned.test/pkg"]
)
def test_stream_requires_https_url_with_host(url: str) -> None:
    with pytest.raises(ValueError, match="requires an https URL with a host"):
        with stream_pinned_https_once(url, {}, 16, _allow_loopback):
            pass


def test_stream_rejects_port_zero() -> None:
    with pytest.raises(ValueError, match="requires a non-zero port"):
        with stream_pinned_https_once(
            "https://pinned.test:0/pkg", {}, 16, _allow_loopback
        ):
            pass


def test_stream_wraps_http_client_exceptions(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_connection_cls = mocker.patch(
        "dd_license_attribution.utils.pinned_https.PinnedHTTPSConnection"
    )
    connection = mock_connection_cls.return_value
    connection.getresponse.side_effect = http.client.BadStatusLine("NOT_HTTP")

    with pytest.raises(OSError, match="Failed to download https://pinned.test/pkg"):
        with stream_pinned_https_once(
            "https://pinned.test/pkg", {}, 16, _allow_loopback
        ):
            pass
    connection.close.assert_called_once_with()

    connection.reset_mock()
    connection.getresponse.side_effect = None
    connection.getresponse.return_value.status = 200
    connection.getresponse.return_value.headers = {}

    def failing_stream(amt: int, decode_content: bool = False) -> Iterator[bytes]:
        raise http.client.HTTPException("bad trailer")
        yield b""

    connection.getresponse.return_value.stream.side_effect = failing_stream
    with pytest.raises(OSError, match="Failed to download https://pinned.test/pkg"):
        with stream_pinned_https_once(
            "https://pinned.test/pkg", {}, 16, _allow_loopback
        ) as (_, _, chunks):
            b"".join(chunks)
    connection.close.assert_called_once_with()


def test_stream_does_not_decompress_gzip_body(
    tls_server: _TLSServer, mocker: pytest_mock.MockFixture
) -> None:
    mocker.patch(RESOLVER, return_value=["127.0.0.1"])
    compressed = gzip.compress(b"A" * 65536)

    def respond(handler: http.server.BaseHTTPRequestHandler) -> None:
        handler.send_response(200)
        handler.send_header("Content-Encoding", "gzip")
        handler.send_header("Content-Length", str(len(compressed)))
        handler.end_headers()
        tls_server.write(handler, compressed)

    tls_server.respond = respond
    with stream_pinned_https_once(
        f"https://pinned.test:{tls_server.port}/pkg", {}, 1024, _allow_loopback
    ) as (status, _, chunks):
        assert status == 200
        assert b"".join(chunks) == compressed


def test_stream_requests_root_path_when_url_has_none(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_connection_cls = mocker.patch(
        "dd_license_attribution.utils.pinned_https.PinnedHTTPSConnection"
    )
    connection = mock_connection_cls.return_value
    connection.getresponse.return_value.status = 200
    connection.getresponse.return_value.headers = {}
    connection.getresponse.return_value.stream.return_value = iter([b"ok"])

    with stream_pinned_https_once(
        "https://pinned.test", {"User-Agent": "a"}, 8, _allow_loopback, timeout=5
    ) as (_, _, chunks):
        assert list(chunks) == [b"ok"]

    assert mock_connection_cls.call_args.args == ("pinned.test",)
    assert mock_connection_cls.call_args.kwargs["port"] == 443
    assert mock_connection_cls.call_args.kwargs["timeout"] == 5
    assert mock_connection_cls.call_args.kwargs["ip_validator"] is _allow_loopback
    connection.request.assert_called_once_with(
        "GET",
        "/",
        headers={"User-Agent": "a"},
        preload_content=False,
        decode_content=False,
    )
    connection.getresponse.return_value.stream.assert_called_once_with(
        8, decode_content=False
    )
    connection.close.assert_called_once_with()


def _connection(
    ip_validator: Callable[[str], bool],
    *,
    source_address: tuple[str, int] | None = None,
    socket_options: list[tuple[int, int, int]] | None = None,
) -> PinnedHTTPSConnection:
    return PinnedHTTPSConnection(
        "pinned.test",
        port=8443,
        timeout=7,
        source_address=source_address,
        socket_options=socket_options,
        ip_validator=ip_validator,
    )


def test_new_conn_falls_back_to_next_validated_address(
    mocker: pytest_mock.MockFixture,
) -> None:
    mocker.patch(RESOLVER, return_value=["192.0.2.1", "198.51.100.1"])
    sock = Mock(spec=socket.socket)
    mock_create = mocker.patch(
        CREATE_CONNECTION, side_effect=[OSError("unreachable"), sock]
    )
    source_address = ("192.0.2.9", 0)
    socket_options = [(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)]
    conn = _connection(
        lambda ip: True,
        source_address=source_address,
        socket_options=socket_options,
    )

    assert conn._new_conn() is sock
    assert mock_create.call_args_list == [
        mocker.call(
            ("192.0.2.1", 8443),
            7,
            source_address=source_address,
            socket_options=socket_options,
        ),
        mocker.call(
            ("198.51.100.1", 8443),
            7,
            source_address=source_address,
            socket_options=socket_options,
        ),
    ]


def test_new_conn_reports_last_error_when_every_address_fails(
    mocker: pytest_mock.MockFixture,
) -> None:
    mocker.patch(RESOLVER, return_value=["192.0.2.1", "198.51.100.1"])
    mocker.patch(CREATE_CONNECTION, side_effect=[OSError("first"), OSError("second")])
    conn = _connection(lambda ip: True)

    with pytest.raises(NewConnectionError, match="second") as exc_info:
        conn._new_conn()
    assert exc_info.value.conn is conn


def test_new_conn_rejects_mixed_answers_and_empty_or_failed_resolution(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_create = mocker.patch(CREATE_CONNECTION)
    mock_resolve = mocker.patch(RESOLVER, return_value=["192.0.2.1", "10.0.0.1"])
    conn = _connection(lambda ip: ip == "192.0.2.1")
    with pytest.raises(
        NewConnectionError, match=r"include disallowed \['10.0.0.1'\]"
    ) as exc_info:
        conn._new_conn()
    assert exc_info.value.conn is conn

    mock_resolve.return_value = []
    conn_empty = _connection(lambda ip: True)
    with pytest.raises(NewConnectionError, match="Refusing to connect") as exc_info:
        conn_empty._new_conn()
    assert exc_info.value.conn is conn_empty

    mock_resolve.side_effect = OSError("Failed to resolve host pinned.test")
    conn_fail = _connection(lambda ip: True)
    with pytest.raises(NewConnectionError, match="Failed to resolve host") as exc_info:
        conn_fail._new_conn()
    assert exc_info.value.conn is conn_fail
    mock_create.assert_not_called()


def test_ca_bundle_follows_requests_environment_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)
    assert _ca_bundle_kwargs() == {"ca_certs": DEFAULT_CA_BUNDLE_PATH}

    monkeypatch.setenv("CURL_CA_BUNDLE", "/curl/ca.pem")
    assert _ca_bundle_kwargs() == {"ca_certs": "/curl/ca.pem"}

    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(tmp_path))
    assert _ca_bundle_kwargs() == {"ca_cert_dir": str(tmp_path)}
