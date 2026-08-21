"""Shared SSRF policy for server-side outbound media downloads."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import socket
from urllib.parse import SplitResult, parse_qs, urlsplit, urlunsplit


_SUPPORTED_MEDIA_PROXY_HOSTS = {"media.fastdl.app"}


def unwrap_supported_media_proxy_url(value: str) -> str:
    """Extract the public origin URL from a known media delivery wrapper.

    This is intentionally limited to explicitly supported hosts. The returned
    URL still passes through ``resolve_public_http_url`` before server-side
    download, so unwrapping does not bypass DNS/IP validation.
    """
    if not isinstance(value, str):
        return value
    text = value.strip()
    try:
        parsed = urlsplit(text)
    except ValueError:
        return text
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if hostname not in _SUPPORTED_MEDIA_PROXY_HOSTS or parsed.path.rstrip("/") != "/get":
        return text
    query = parse_qs(parsed.query, keep_blank_values=True)
    candidates = query.get("uri") or []
    if len(candidates) != 1 or not candidates[0].strip():
        raise ValueError("media_url wrapper must contain exactly one non-empty uri parameter")
    inner = candidates[0].strip()
    try:
        inner_parsed = urlsplit(inner)
    except ValueError as exc:
        raise ValueError("media_url wrapper contains an invalid uri parameter") from exc
    if (
        inner_parsed.scheme.lower() not in {"http", "https"}
        or not inner_parsed.hostname
        or inner_parsed.username is not None
        or inner_parsed.password is not None
    ):
        raise ValueError("media_url wrapper uri must be a valid public HTTP or HTTPS URL")
    return urlunsplit(SplitResult(inner_parsed.scheme.lower(), inner_parsed.netloc, inner_parsed.path or "/", inner_parsed.query, ""))


@dataclass(frozen=True, slots=True)
class PinnedPublicURL:
    """A public URL whose TCP destination no longer requires DNS resolution."""

    public_url: str
    connect_url: str
    host_header: str
    sni_hostname: str

    @property
    def request_headers(self) -> dict[str, str]:
        return {"Host": self.host_header}

    @property
    def request_extensions(self) -> dict[str, str]:
        # httpcore uses this hostname for TLS SNI and certificate validation
        # even though connect_url contains the already-validated IP address.
        return {"sni_hostname": self.sni_hostname}


def resolve_public_http_url(value: str, *, field_name: str) -> PinnedPublicURL:
    """Validate one URL and pin its HTTP connection to a checked public IP.

    Every DNS answer must be globally routable. The returned URL replaces the
    hostname with one validated numeric address, preventing the HTTP transport
    from performing a second attacker-controlled DNS lookup at connect time.
    """
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid public HTTP or HTTPS URL") from exc

    hostname = parsed.hostname
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError(f"{field_name} must be a valid public HTTP or HTTPS URL")

    normalized_hostname = hostname.lower().rstrip(".")
    try:
        hostname_ip = ipaddress.ip_address(normalized_hostname)
        transport_hostname = str(hostname_ip)
    except ValueError:
        try:
            transport_hostname = normalized_hostname.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError(f"{field_name} hostname is invalid") from exc
    try:
        addresses = socket.getaddrinfo(transport_hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"{field_name} host could not be resolved") from exc
    if not addresses:
        raise ValueError(f"{field_name} host resolved to zero addresses")

    public_ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    seen: set[str] = set()
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError(f"{field_name} must resolve only to public addresses")
        if str(ip) not in seen:
            seen.add(str(ip))
            public_ips.append(ip)

    # Prefer IPv4 when both families are advertised. This avoids selecting an
    # otherwise valid AAAA address on hosts without outbound IPv6 connectivity.
    selected_ip = min(public_ips, key=lambda item: item.version)
    ip_host = f"[{selected_ip}]" if selected_ip.version == 6 else str(selected_ip)
    connect_netloc = ip_host if port is None else f"{ip_host}:{port}"
    public_path = parsed.path or "/"
    public_url = urlunsplit(
        SplitResult(parsed.scheme.lower(), parsed.netloc, public_path, parsed.query, "")
    )
    connect_url = urlunsplit(
        SplitResult(parsed.scheme.lower(), connect_netloc, public_path, parsed.query, "")
    )

    host_header = transport_hostname
    if ":" in host_header and not host_header.startswith("["):
        host_header = f"[{host_header}]"
    if port is not None:
        host_header = f"{host_header}:{port}"

    return PinnedPublicURL(
        public_url=public_url,
        connect_url=connect_url,
        host_header=host_header,
        sni_hostname=transport_hostname,
    )
