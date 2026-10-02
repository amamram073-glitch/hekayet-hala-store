import hashlib
import hmac
import ipaddress
import json
import socket
import ssl
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlsplit
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import settings
from app.models import ThreatWebhook, WebhookDelivery

ALLOWED_WEBHOOK_EVENTS = {"ALERT_CREATED", "INCIDENT_CREATED", "SCAN_COMPLETED", "HIGH_SEVERITY_EVENT"}


def _cipher() -> Fernet:
    key = settings.webhook_encryption_key
    if not key:
        raise HTTPException(status_code=503, detail="Set WEBHOOK_ENCRYPTION_KEY before configuring webhooks")
    try: return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        raise HTTPException(status_code=503, detail="WEBHOOK_ENCRYPTION_KEY must be a valid Fernet key")


def encrypt_secret(secret: str) -> str:
    return _cipher().encrypt(secret.encode()).decode()


def decrypt_secret(value: str) -> str:
    try: return _cipher().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError): raise RuntimeError("Webhook encryption key is invalid or has changed")


def resolve_public_target(url: str):
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in url) or "\\" in url:
        raise ValueError("Webhook URL contains invalid control characters")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Webhook URL must use HTTPS and cannot include credentials")
    if parsed.port not in (None, 443): raise ValueError("Webhook URLs must use port 443")
    try: host = parsed.hostname.encode("idna").decode("ascii").rstrip(".").lower()
    except UnicodeError as error: raise ValueError("Webhook hostname is invalid") from error
    if not host or host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".internal", ".test", ".invalid")):
        raise ValueError("Webhook host must be a public DNS hostname")
    try:
        ipaddress.ip_address(host)
        raise ValueError("Webhook URL must use a DNS hostname, not an IP literal")
    except ValueError as error:
        if "IP literal" in str(error): raise
    try: records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as error: raise ValueError("Webhook host did not resolve") from error
    addresses = sorted({record[4][0] for record in records})
    if not addresses: raise ValueError("Webhook host did not resolve")
    for address in addresses:
        try: parsed_ip = ipaddress.ip_address(address.split("%", 1)[0])
        except ValueError: raise ValueError("Webhook DNS returned an invalid address")
        if not parsed_ip.is_global:
            raise ValueError("Webhook DNS must resolve only to public IP addresses")
    return parsed, host, addresses


def create_delivery_rows(db: Session, organization_id, event_type: str, payload: dict):
    hooks = db.scalars(select(ThreatWebhook).where(ThreatWebhook.organization_id == organization_id,
        ThreatWebhook.active.is_(True))).all()
    rows = []
    for hook in hooks:
        allowed = set(hook.event_types or [])
        if event_type not in allowed and "*" not in allowed: continue
        row = WebhookDelivery(organization_id=organization_id, webhook_id=hook.id,
            event_type=event_type, payload=payload, status="QUEUED")
        db.add(row)
        rows.append(row)
    return rows


def send_signed_webhook(url: str, secret: str, event_type: str, payload: dict) -> int:
    parsed, host, addresses = resolve_public_target(url)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str).encode()
    if len(body) > 256 * 1024: raise ValueError("Webhook payload exceeds 256 KB")
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    path = quote(parsed.path or "/", safe="/%:@-._~!$&'()*+,;=")
    if parsed.query: path += "?" + quote(parsed.query, safe="=&?/:@-._~!$'()*+,;[]%")
    # Pin TLS and the TCP socket to an address from the validated DNS answer. The
    # original hostname remains the TLS SNI and Host header; redirects are never followed.
    context = ssl.create_default_context()
    last_error = None
    for address in addresses:
        try:
            raw = socket.create_connection((address, 443), timeout=5)
            with context.wrap_socket(raw, server_hostname=host) as conn:
                request = (f"POST {path} HTTP/1.1\r\nHost: {host}\r\n"
                    f"User-Agent: CyberShieldOS-Webhook/1.0\r\nContent-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\nConnection: close\r\n"
                    f"X-CyberShield-Event: {event_type}\r\n"
                    f"X-CyberShield-Signature: sha256={signature}\r\n\r\n").encode("ascii")
                conn.sendall(request + body)
                stream = conn.makefile("rb")
                status_line = stream.readline(4096).decode("ascii", errors="replace").strip()
                parts = status_line.split(" ", 2)
                if len(parts) < 2 or not parts[1].isdigit(): raise OSError("Invalid HTTP response from webhook")
                # Bound header parsing and ignore response content; no redirects or response body processing.
                total = 0
                while True:
                    line = stream.readline(4096)
                    total += len(line)
                    if total > 16 * 1024: raise OSError("Webhook response headers are too large")
                    if not line or line in (b"\r\n", b"\n"): break
                return int(parts[1])
        except (OSError, ssl.SSLError) as error:
            last_error = error
    raise OSError("Webhook delivery failed") from last_error
