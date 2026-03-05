"""
Secure Channel Configuration for Edge-Cloud Communication.

This module provides TLS/mTLS configuration for:
1. gRPC channels between edge schedulers and cloud orchestrator
2. Certificate management utilities
3. Secure tunnel establishment

In production deployments:
- Use proper PKI infrastructure (e.g., HashiCorp Vault PKI, AWS ACM)
- Implement certificate rotation
- Enable mTLS for mutual authentication
"""

import os
import ssl
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class TLSConfig:
    """TLS configuration for secure gRPC channels."""
    enabled: bool = False
    cert_file: Optional[str] = None      # Server/Client certificate
    key_file: Optional[str] = None       # Private key
    ca_file: Optional[str] = None        # CA certificate for verification
    verify_peer: bool = True             # Enable peer certificate verification
    server_name: Optional[str] = None    # Expected server name for SNI


class SecureChannelManager:
    """
    Manages secure communication channels between distributed components.

    Supports:
    - TLS for encrypted transport
    - mTLS for mutual authentication
    - Certificate validation
    """

    def __init__(self):
        self.tls_config = self._load_config_from_env()

    def _load_config_from_env(self) -> TLSConfig:
        """Load TLS configuration from environment variables."""
        return TLSConfig(
            enabled=os.getenv("TLS_ENABLED", "false").lower() == "true",
            cert_file=os.getenv("TLS_CERT_FILE"),
            key_file=os.getenv("TLS_KEY_FILE"),
            ca_file=os.getenv("TLS_CA_FILE"),
            verify_peer=os.getenv("TLS_VERIFY_PEER", "true").lower() == "true",
            server_name=os.getenv("TLS_SERVER_NAME"),
        )

    def get_grpc_credentials(self) -> Optional[object]:
        """
        Get gRPC credentials for secure channel creation.

        Returns:
            grpc.ChannelCredentials or None if TLS disabled
        """
        if not self.tls_config.enabled:
            logger.info("TLS disabled, using insecure channel")
            return None

        try:
            import grpc

            # Load certificates
            root_certs = None
            if self.tls_config.ca_file and os.path.exists(self.tls_config.ca_file):
                with open(self.tls_config.ca_file, "rb") as f:
                    root_certs = f.read()

            private_key = None
            cert_chain = None

            # For mTLS, load client certificate and key
            if self.tls_config.key_file and os.path.exists(self.tls_config.key_file):
                with open(self.tls_config.key_file, "rb") as f:
                    private_key = f.read()

            if self.tls_config.cert_file and os.path.exists(self.tls_config.cert_file):
                with open(self.tls_config.cert_file, "rb") as f:
                    cert_chain = f.read()

            credentials = grpc.ssl_channel_credentials(
                root_certificates=root_certs,
                private_key=private_key,
                certificate_chain=cert_chain,
            )

            logger.info("TLS credentials loaded successfully")
            return credentials

        except Exception as e:
            logger.error(f"Failed to load TLS credentials: {e}")
            return None

    def get_server_credentials(self) -> Optional[object]:
        """
        Get gRPC server credentials for accepting secure connections.

        Returns:
            grpc.ServerCredentials or None if TLS disabled
        """
        if not self.tls_config.enabled:
            return None

        try:
            import grpc

            # Load server certificate and key
            if not (self.tls_config.cert_file and self.tls_config.key_file):
                logger.error("Server cert/key files not configured")
                return None

            with open(self.tls_config.key_file, "rb") as f:
                private_key = f.read()

            with open(self.tls_config.cert_file, "rb") as f:
                certificate_chain = f.read()

            # Load CA for client verification (mTLS)
            root_certs = None
            require_client_auth = False

            if self.tls_config.ca_file and os.path.exists(self.tls_config.ca_file):
                with open(self.tls_config.ca_file, "rb") as f:
                    root_certs = f.read()
                require_client_auth = self.tls_config.verify_peer

            credentials = grpc.ssl_server_credentials(
                [(private_key, certificate_chain)],
                root_certificates=root_certs,
                require_client_auth=require_client_auth,
            )

            logger.info("Server TLS credentials loaded (mTLS: %s)", require_client_auth)
            return credentials

        except Exception as e:
            logger.error(f"Failed to load server TLS credentials: {e}")
            return None

    def create_secure_channel(self, target: str) -> object:
        """
        Create a secure gRPC channel to target.

        Args:
            target: Target address (host:port)

        Returns:
            grpc.Channel (secure or insecure based on config)
        """
        import grpc

        credentials = self.get_grpc_credentials()

        if credentials:
            options = []
            if self.tls_config.server_name:
                options.append(("grpc.ssl_target_name_override", self.tls_config.server_name))

            channel = grpc.secure_channel(target, credentials, options=options)
            logger.info(f"Created secure channel to {target}")
        else:
            channel = grpc.insecure_channel(target)
            logger.info(f"Created insecure channel to {target}")

        return channel


def generate_self_signed_certs(output_dir: str = "certs") -> Tuple[str, str, str]:
    """
    Generate self-signed certificates for development/testing.

    WARNING: Do not use in production! Use proper PKI.

    Args:
        output_dir: Directory to write certificate files

    Returns:
        Tuple of (ca_file, cert_file, key_file) paths
    """
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend
        import datetime

        os.makedirs(output_dir, exist_ok=True)

        # Generate CA key and certificate
        ca_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        ca_name = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "FI"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Edge Scheduler CA"),
            x509.NameAttribute(NameOID.COMMON_NAME, "edge-scheduler-ca"),
        ])

        ca_cert = (
            x509.CertificateBuilder()
            .subject_name(ca_name)
            .issuer_name(ca_name)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .sign(ca_key, hashes.SHA256(), default_backend())
        )

        # Generate server key and certificate
        server_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        server_name = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "FI"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Edge Scheduler"),
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ])

        server_cert = (
            x509.CertificateBuilder()
            .subject_name(server_name)
            .issuer_name(ca_name)
            .public_key(server_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("localhost"),
                    x509.DNSName("scheduler-1"),
                    x509.DNSName("scheduler-2"),
                    x509.DNSName("scheduler-3"),
                ]),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256(), default_backend())
        )

        # Write files
        ca_file = os.path.join(output_dir, "ca.pem")
        cert_file = os.path.join(output_dir, "server.pem")
        key_file = os.path.join(output_dir, "server-key.pem")

        with open(ca_file, "wb") as f:
            f.write(ca_cert.public_bytes(serialization.Encoding.PEM))

        with open(cert_file, "wb") as f:
            f.write(server_cert.public_bytes(serialization.Encoding.PEM))

        with open(key_file, "wb") as f:
            f.write(server_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))

        logger.info(f"Generated self-signed certificates in {output_dir}/")
        return ca_file, cert_file, key_file

    except ImportError:
        logger.error("cryptography package required for certificate generation")
        raise


# Global instance
secure_channel_manager = SecureChannelManager()
