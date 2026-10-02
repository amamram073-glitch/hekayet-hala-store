import ipaddress
import re
import socket
import ssl
from datetime import datetime, timezone
from app.config import settings

SAFE_HEADERS = {
    "strict-transport-security": ("HIGH", "Enable HSTS with a suitable max-age and includeSubDomains where appropriate."),
    "content-security-policy": ("MEDIUM", "Define a restrictive Content-Security-Policy for the application."),
    "x-content-type-options": ("LOW", "Set X-Content-Type-Options: nosniff."),
    "referrer-policy": ("LOW", "Set an explicit privacy-conscious Referrer-Policy."),
    "permissions-policy": ("LOW", "Restrict browser features not used by the application."),
}


def _validate_host(host: str) -> str:
    if not isinstance(host, str) or not host or host != host.strip() or len(host) > 253:
        raise ValueError("Only a plain hostname is accepted for authorized checks")
    if any(ch.isspace() or ord(ch) < 33 or ch in "/\\@?#[]" for ch in host):
        raise ValueError("Only a plain hostname is accepted for authorized checks")
    host = host.lower()
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            raise ValueError("Private, reserved, and loopback addresses are blocked")
        return ip.compressed
    except ValueError as error:
        if "blocked" in str(error):
            raise
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise ValueError("Invalid internationalized hostname") from error
    labels = host.split(".")
    label_pattern = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
    if (len(host) > 253 or len(labels) < 2 or host.endswith((".local", ".localhost", ".internal"))
            or any(len(label) > 63 or not label_pattern.fullmatch(label) for label in labels)):
        raise ValueError("A public fully-qualified hostname is required")
    return host


def _resolve_public(host: str) -> list[str]:
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as error:
        raise ValueError(f"DNS lookup failed: {error.__class__.__name__}")
    addresses = sorted({record[4][0] for record in records})
    if not addresses:
        raise ValueError("No DNS addresses found")
    for address in addresses:
        if not ipaddress.ip_address(address).is_global:
            raise ValueError("DNS resolved to a private or reserved address; scan blocked")
    return addresses


def _request_pinned(host: str, address: str, tls_context: ssl.SSLContext) -> tuple[dict, dict]:
    timeout = max(1, min(settings.scan_timeout_seconds, 8))
    raw = socket.create_connection((address, 443), timeout=timeout)
    try:
        with tls_context.wrap_socket(raw, server_hostname=host) as connection:
            cert = connection.getpeercert()
            try:
                ip_version = ipaddress.ip_address(host).version
            except ValueError:
                ip_version = 0
            host_header = f"[{host}]" if ip_version == 6 else host
            connection.sendall((f"HEAD / HTTP/1.1\r\nHost: {host_header}\r\nUser-Agent: CyberShieldOS-SafeCheck/1.0\r\nConnection: close\r\n\r\n").encode("ascii"))
            response = connection.recv(32768).decode("iso-8859-1", "replace")
        lines = response.split("\r\n")
        status = lines[0][:200] if lines else "No HTTP response"
        headers = {}
        for line in lines[1:]:
            if not line:
                break
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()[:1000]
        return cert, {"status": status, "headers": headers}
    finally:
        try: raw.close()
        except OSError: pass


def safe_scan(host: str) -> dict:
    """Read-only DNS/TLS/HTTP HEAD check against an organization-authorized public asset."""
    host = _validate_host(host)
    addresses = _resolve_public(host)
    context = ssl.create_default_context()
    certificate = None
    response = None
    errors = []
    for address in addresses[:3]:
        try:
            cert, response = _request_pinned(host, address, context)
            certificate = cert
            break
        except (OSError, ssl.SSLError, TimeoutError) as error:
            errors.append(error.__class__.__name__)
    if response is None:
        return {"hostname": host, "dns": addresses, "checked_at": datetime.now(timezone.utc).isoformat(),
                "tls": {"valid": False, "error": errors[0] if errors else "Connection unavailable"}, "http": None}
    expiry = certificate.get("notAfter") if certificate else None
    return {"hostname": host, "dns": addresses, "checked_at": datetime.now(timezone.utc).isoformat(),
            "tls": {"valid": certificate is not None, "expires_at": expiry, "issuer": dict(x[0] for x in certificate.get("issuer", [])) if certificate else {}},
            "http": response}


def findings_from_result(asset_id, organization_id, scan_id, result: dict) -> list[dict]:
    findings = []
    if result.get("tls", {}).get("valid") is False:
        findings.append({"asset_id": asset_id, "organization_id": organization_id, "scan_id": scan_id,
                         "title": "TLS connection could not be verified", "description": "The safe TLS check did not establish a valid TLS response.",
                         "severity": "HIGH", "category": "TLS", "evidence": result.get("tls", {}),
                         "remediation": "Verify the public TLS listener and certificate chain."})
    headers = result.get("http", {}).get("headers", {}) if result.get("http") else {}
    if headers:
        for name, (severity, remediation) in SAFE_HEADERS.items():
            if name not in headers:
                findings.append({"asset_id": asset_id, "organization_id": organization_id, "scan_id": scan_id,
                                 "title": f"Missing HTTP security header: {name}", "description": f"The authorized HTTPS endpoint did not return {name}.",
                                 "severity": severity, "category": "HTTP_HEADERS", "evidence": {"header": name, "http_status": result["http"]["status"]},
                                 "remediation": remediation})
    return findings
