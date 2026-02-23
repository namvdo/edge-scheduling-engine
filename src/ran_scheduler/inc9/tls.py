from __future__ import annotations

"""Minimal mTLS helpers (stdlib only).

"""

import ssl
from dataclasses import dataclass
from typing import Optional




@dataclass(frozen=True)
class ServerTLSConfig:
    ca_file: str
    cert_file: str
    key_file: str
    require_client_cert: bool = True




@dataclass(frozen=True)
class ClientTLSConfig:
    ca_file: str
    cert_file: str
    key_file: str
    #If set, enables hostname verification (recommended).
    server_hostname: Optional[str] = None




def build_server_ssl_context(cfg: ServerTLSConfig) -> ssl.SSLContext:
    """mTLS server context.

    - Verifies client certs against cfg.ca_file.
    - Uses TLSv1.2+ defaults.
    """

    ctx = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(certfile=cfg.cert_file, keyfile=cfg.key_file)
    ctx.load_verify_locations(cafile=cfg.ca_file)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    if cfg.require_client_cert:
        ctx.verify_mode = ssl.CERT_REQUIRED
    else:
        ctx.verify_mode = ssl.CERT_OPTIONAL
    #hostname validation is a *client* feature.
    return ctx




def build_client_ssl_context(cfg: ClientTLSConfig) -> ssl.SSLContext:
    """mTLS client context."""
    ctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH, cafile=cfg.ca_file)
    ctx.load_cert_chain(certfile=cfg.cert_file, keyfile=cfg.key_file)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    #enforce hostname verification only if server_hostname is provided.
    ctx.check_hostname = bool(cfg.server_hostname)
    return ctx
