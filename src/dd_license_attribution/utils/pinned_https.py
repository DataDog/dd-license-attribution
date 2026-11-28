# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

"""Single-hop HTTPS GETs whose sockets connect only to addresses a caller-supplied policy accepts.

The hostname is resolved once per connection, every resolved address is checked, and
the socket is opened to a checked address, so a DNS answer that changes between the
check and the connection cannot redirect it. TLS still verifies the certificate against
the hostname. Requests features are deliberately absent: there is no `.netrc` or other
ambient authentication, no environment proxy (a proxy would resolve the hostname itself
and defeat the address check), and no redirect handling, so a redirect body is never
read implicitly. CA bundle selection follows Requests (`REQUESTS_CA_BUNDLE`,
`CURL_CA_BUNDLE`, then certifi).
"""

import contextlib
import http.client
import socket
from collections.abc import Callable, Iterator, Mapping
from typing import Any
from urllib.parse import urlsplit

from requests.utils import DEFAULT_CA_BUNDLE_PATH
from urllib3.connection import HTTPSConnection
from urllib3.exceptions import HTTPError, NewConnectionError
from urllib3.util import connection as urllib3_connection

from dd_license_attribution.adaptors.os import get_env_var, is_dir, resolve_host_ips


class PinnedHTTPSConnection(HTTPSConnection):
    """HTTPS connection that only opens sockets to resolved addresses accepted by `ip_validator`."""

    def __init__(
        self, *args: Any, ip_validator: Callable[[str], bool], **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self._ip_validator = ip_validator

    def _new_conn(self) -> socket.socket:
        try:
            addresses = resolve_host_ips(self._dns_host, self.port)
        except OSError as e:
            raise NewConnectionError(self, str(e)) from e
        rejected = [ip for ip in addresses if not self._ip_validator(ip)]
        if not addresses or rejected:
            raise NewConnectionError(
                self,
                f"Refusing to connect to {self.host}: resolved addresses "
                f"{addresses} include disallowed {rejected}",
            )
        last_error: OSError | None = None
        for ip in addresses:
            try:
                return urllib3_connection.create_connection(
                    (ip, self.port),
                    self.timeout,
                    source_address=self.source_address,
                    socket_options=self.socket_options,
                )
            except OSError as e:
                last_error = e
        raise NewConnectionError(
            self, f"Failed to establish a new connection: {last_error}"
        ) from last_error


def _ca_bundle_kwargs() -> dict[str, str]:
    bundle = (
        get_env_var("REQUESTS_CA_BUNDLE")
        or get_env_var("CURL_CA_BUNDLE")
        or DEFAULT_CA_BUNDLE_PATH
    )
    if is_dir(bundle):
        return {"ca_cert_dir": bundle}
    return {"ca_certs": bundle}


def _wrap_stream_errors(url: str, chunks: Iterator[bytes]) -> Iterator[bytes]:
    try:
        yield from chunks
    except (HTTPError, http.client.HTTPException, OSError) as e:
        raise OSError(f"Failed to download {url}: {e}") from e


@contextlib.contextmanager
def stream_pinned_https_once(
    url: str,
    headers: Mapping[str, str],
    chunk_size: int,
    ip_validator: Callable[[str], bool],
    timeout: float = 30,
) -> Iterator[tuple[int, Mapping[str, str], Iterator[bytes]]]:
    """GET `url` once without following redirects; yield status, headers, and raw body chunks.

    HTTP error statuses are yielded, not raised; the caller decides what they mean.
    Leaving the context closes the socket without reading any unread body.
    """
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError(f"Pinned HTTPS fetch requires an https URL with a host: {url}")
    port = parts.port
    if port == 0:
        raise ValueError(f"Pinned HTTPS fetch requires a non-zero port: {url}")
    target = parts.path or "/"
    if parts.query:
        target = f"{target}?{parts.query}"
    connection = PinnedHTTPSConnection(
        parts.hostname,
        port=443 if port is None else port,
        timeout=timeout,
        ip_validator=ip_validator,
        **_ca_bundle_kwargs(),
    )
    try:
        try:
            connection.request(
                "GET",
                target,
                headers=dict(headers),
                preload_content=False,
                decode_content=False,
            )
            response = connection.getresponse()
        except (HTTPError, http.client.HTTPException, OSError) as e:
            raise OSError(f"Failed to download {url}: {e}") from e
        yield (
            response.status,
            response.headers,
            _wrap_stream_errors(url, response.stream(chunk_size, decode_content=False)),
        )
    finally:
        connection.close()
