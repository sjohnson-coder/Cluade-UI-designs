"""Bounded, DNS-pinned HTTPS client for operator-configurable external feeds.

The validated IP address is the address used for the TCP connection. TLS still uses
the original hostname for SNI and certificate verification. This closes the classic
"validate DNS, resolve again while connecting" rebinding window.
"""
from __future__ import annotations

import http.client
import io
import ipaddress
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


@dataclass(frozen=True)
class _PublicHttpsTarget:
    url: str
    host: str
    port: int
    addresses: tuple[str, ...]


def _resolve_public_https_target(url: str) -> _PublicHttpsTarget:
    value = str(url or "").strip()
    parts = urllib.parse.urlsplit(value)
    if parts.scheme.lower() != "https":
        raise ValueError("External feed URLs must use HTTPS.")
    if parts.username or parts.password:
        raise ValueError("Credentials embedded in feed URLs are prohibited.")
    host = (parts.hostname or "").strip().lower().rstrip(".")
    if not host or host == "localhost" or host.endswith(".localhost"):
        raise ValueError("External feed URL has no public hostname.")
    try:
        literal = ipaddress.ip_address(host)
        addresses = {literal}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(
                    host,
                    parts.port or 443,
                    type=socket.SOCK_STREAM,
                )
            }
        except OSError as exc:
            raise ValueError(
                f"External feed hostname cannot be resolved: {exc}"
            ) from exc
    if not addresses:
        raise ValueError("External feed hostname resolved to no address.")
    for address in addresses:
        if not address.is_global:
            raise ValueError(
                "External feed URL resolves to a non-public network address."
            )
    ordered = tuple(sorted((str(item) for item in addresses), key=str))
    return _PublicHttpsTarget(value, host, parts.port or 443, ordered)


def validate_public_https_url(url: str) -> str:
    return _resolve_public_https_target(url).url


def validate_connected_public_peer(peer_ip: str, expected_ip: str) -> str:
    """Verify the connected socket stayed on the exact validated public address."""
    try:
        peer = ipaddress.ip_address(str(peer_ip).split("%", 1)[0])
        expected = ipaddress.ip_address(str(expected_ip).split("%", 1)[0])
    except ValueError as exc:
        raise ValueError("Connected peer address is invalid.") from exc
    if not peer.is_global:
        raise ValueError("Connected peer is a non-public network address.")
    if peer != expected:
        raise ValueError(
            "Connected peer does not match the DNS address validated for this request."
        )
    return str(peer)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        host: str,
        port: int,
        address: str,
        timeout: float,
    ) -> None:
        super().__init__(
            host=host,
            port=port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        self._validated_address = address

    def connect(self) -> None:
        raw = socket.create_connection(
            (self._validated_address, self.port),
            self.timeout,
            self.source_address,
        )
        try:
            peer = raw.getpeername()[0]
            validate_connected_public_peer(peer, self._validated_address)
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


def _open_pinned_connection(
    host: str,
    port: int,
    address: str,
    timeout: float,
) -> _PinnedHTTPSConnection:
    return _PinnedHTTPSConnection(host, port, address, timeout)


def _request_parts(
    request_or_url: urllib.request.Request | str,
) -> tuple[str, str, bytes | None, dict[str, str]]:
    if isinstance(request_or_url, urllib.request.Request):
        return (
            request_or_url.full_url,
            request_or_url.get_method().upper(),
            request_or_url.data,
            dict(request_or_url.header_items()),
        )
    return str(request_or_url), "GET", None, {}


def _redirect_request(
    *,
    current_url: str,
    new_url: str,
    status: int,
    method: str,
    body: bytes | None,
    headers: dict[str, str],
) -> tuple[str, str, bytes | None, dict[str, str]]:
    next_url = urllib.parse.urljoin(current_url, new_url)
    old = urllib.parse.urlsplit(current_url)
    new = urllib.parse.urlsplit(next_url)
    next_headers = {
        key: value
        for key, value in headers.items()
        if key.lower() not in {"host", "connection", "proxy-authorization"}
    }
    if (old.hostname, old.port or 443) != (new.hostname, new.port or 443):
        next_headers = {
            key: value
            for key, value in next_headers.items()
            if key.lower() not in {"authorization", "cookie"}
        }
    if status == 303 and method != "HEAD":
        method, body = "GET", None
    elif status in {301, 302} and method == "POST":
        method, body = "GET", None
    if body is None:
        next_headers = {
            key: value
            for key, value in next_headers.items()
            if key.lower() not in {"content-length", "content-type"}
        }
    return next_url, method, body, next_headers


def read_public_https(
    request_or_url: urllib.request.Request | str,
    *,
    timeout: float = 8.0,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> bytes:
    current_url, method, body, headers = _request_parts(request_or_url)
    timeout_value = max(0.5, min(float(timeout), 30.0))
    try:
        requested_limit = int(max_bytes)
    except (TypeError, ValueError) as exc:
        raise ValueError("External feed response limit must be an integer.") from exc
    if requested_limit <= 0:
        raise ValueError("External feed response limit must be positive.")
    limit = min(requested_limit, MAX_RESPONSE_BYTES)

    for redirect_count in range(MAX_REDIRECTS + 1):
        target = _resolve_public_https_target(current_url)
        parts = urllib.parse.urlsplit(target.url)
        request_target = urllib.parse.urlunsplit(
            ("", "", parts.path or "/", parts.query, "")
        )
        request_headers = {
            key: value
            for key, value in headers.items()
            if key.lower() not in {"host", "connection", "proxy-authorization"}
        }
        request_headers["Host"] = (
            target.host if target.port == 443 else f"{target.host}:{target.port}"
        )
        request_headers["Connection"] = "close"

        last_connection_error: BaseException | None = None
        response: Any = None
        connection: Any = None
        for address in target.addresses:
            connection = _open_pinned_connection(
                target.host,
                target.port,
                address,
                timeout_value,
            )
            try:
                connection.request(
                    method,
                    request_target,
                    body=body,
                    headers=request_headers,
                )
                response = connection.getresponse()
                break
            except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
                last_connection_error = exc
                connection.close()
                connection = None
        if response is None or connection is None:
            raise urllib.error.URLError(
                last_connection_error or "No validated address accepted the connection."
            )

        try:
            status = int(getattr(response, "status", 0) or 0)
            if status in _REDIRECT_STATUSES:
                location = response.headers.get("Location")
                if not location:
                    raise ValueError("External feed redirect has no Location header.")
                if redirect_count >= MAX_REDIRECTS:
                    raise ValueError("External feed exceeded the redirect limit.")
                current_url, method, body, headers = _redirect_request(
                    current_url=current_url,
                    new_url=location,
                    status=status,
                    method=method,
                    body=body,
                    headers=headers,
                )
                continue
            declared = response.headers.get("Content-Length")
            if declared:
                try:
                    declared_size = int(str(declared).strip())
                except (TypeError, ValueError):
                    declared_size = None
                if declared_size is not None and declared_size > limit:
                    raise ValueError(
                        "External feed response exceeds the configured size limit."
                    )
            data = response.read(limit + 1)
            if len(data) > limit:
                raise ValueError(
                    "External feed response exceeds the configured size limit."
                )
            if status >= 400:
                raise urllib.error.HTTPError(
                    current_url,
                    status,
                    str(getattr(response, "reason", "HTTP error")),
                    response.headers,
                    io.BytesIO(data),
                )
        finally:
            response.close()
            connection.close()
        return data
    raise ValueError("External feed exceeded the redirect limit.")
