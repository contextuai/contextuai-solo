"""
Encryption & TLS Configuration Service — Enterprise security hardening.

Provides:
- TLS status reporting for all service connections
- MongoDB encryption-at-rest configuration audit
- Redis connection security audit
- Certificate expiry monitoring
- Field-level encryption helpers for sensitive data (AES-256-GCM)
"""

import os
import ssl
import uuid
import base64
import hashlib
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class EncryptionAlgorithm(str, Enum):
    AES_256_GCM = "aes-256-gcm"
    AES_256_CBC = "aes-256-cbc"


class TLSVersion(str, Enum):
    TLS_1_2 = "TLSv1.2"
    TLS_1_3 = "TLSv1.3"


# Fields that should always be encrypted at the application level
SENSITIVE_FIELD_PATTERNS = [
    "password", "secret", "token", "api_key", "private_key",
    "access_key", "credential", "certificate_key",
]


class EncryptionService:
    """Manages TLS configuration, encryption-at-rest, and field-level encryption."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.encryption_logs = db["encryption_audit_logs"]
        self._encryption_key = os.getenv("FIELD_ENCRYPTION_KEY")

    # ------------------------------------------------------------------
    # TLS Status
    # ------------------------------------------------------------------

    async def get_tls_status(self) -> Dict[str, Any]:
        """Report TLS status for all service connections."""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "mongodb": await self._check_mongodb_tls(),
            "redis": self._check_redis_tls(),
            "backend": self._check_backend_tls(),
            "certificates": self._check_certificates(),
            "summary": await self._build_tls_summary(),
        }

    async def _check_mongodb_tls(self) -> Dict[str, Any]:
        """Check MongoDB connection TLS status."""
        try:
            client = self.db.client
            # Check connection options for TLS
            options = client.options
            tls_enabled = getattr(options, "tls", False)

            # Get server info
            server_info = await self.db.command("serverStatus")
            security = server_info.get("security", {})

            # Check if WiredTiger encryption is enabled
            wt_encryption = server_info.get("wiredTiger", {}).get(
                "encryptionAtRest", {}
            )

            return {
                "tls_enabled": tls_enabled,
                "tls_version": os.getenv("MONGODB_TLS_VERSION", "not configured"),
                "tls_ca_file": bool(os.getenv("TLS_CA_CERT")),
                "tls_client_cert": bool(os.getenv("TLS_CLIENT_CERT")),
                "authentication": {
                    "enabled": bool(os.getenv("MONGO_ROOT_USERNAME")),
                    "mechanism": "SCRAM-SHA-256",
                },
                "encryption_at_rest": {
                    "enabled": bool(wt_encryption),
                    "engine": "WiredTiger",
                    "details": wt_encryption if wt_encryption else "Not configured",
                },
                "network_encryption": security.get("SSLServerSubjectName", "none"),
                "status": "secured" if tls_enabled else "unencrypted",
            }
        except Exception as e:
            logger.error(f"MongoDB TLS check failed: {e}")
            return {
                "tls_enabled": False,
                "status": "check_failed",
                "error": str(e),
            }

    def _check_redis_tls(self) -> Dict[str, Any]:
        """Check Redis connection TLS status."""
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        uses_tls = redis_url.startswith("rediss://")
        has_password = "@" in redis_url

        return {
            "tls_enabled": uses_tls,
            "protocol": "rediss" if uses_tls else "redis",
            "password_auth": has_password,
            "tls_ca_file": bool(os.getenv("REDIS_TLS_CA_CERT")),
            "tls_cert": bool(os.getenv("REDIS_TLS_CERT")),
            "tls_key": bool(os.getenv("REDIS_TLS_KEY")),
            "status": "secured" if uses_tls else "unencrypted",
        }

    def _check_backend_tls(self) -> Dict[str, Any]:
        """Check backend service TLS configuration."""
        ssl_keyfile = os.getenv("SSL_KEYFILE")
        ssl_certfile = os.getenv("SSL_CERTFILE")
        has_tls = bool(ssl_keyfile and ssl_certfile)

        return {
            "tls_enabled": has_tls,
            "ssl_keyfile": bool(ssl_keyfile),
            "ssl_certfile": bool(ssl_certfile),
            "min_tls_version": os.getenv("MIN_TLS_VERSION", "TLSv1.2"),
            "status": "secured" if has_tls else "terminated_upstream",
            "note": "TLS typically terminated at load balancer (ALB/nginx)",
        }

    def _check_certificates(self) -> Dict[str, Any]:
        """Check certificate file availability and expiry."""
        cert_files = {
            "ca_cert": os.getenv("TLS_CA_CERT"),
            "client_cert": os.getenv("TLS_CLIENT_CERT"),
            "client_key": os.getenv("TLS_CLIENT_KEY"),
            "mongo_cert": os.getenv("MONGODB_TLS_CERT"),
            "redis_cert": os.getenv("REDIS_TLS_CERT"),
        }

        results = {}
        for name, path in cert_files.items():
            if path and os.path.exists(path):
                results[name] = {
                    "path": path,
                    "exists": True,
                    "expiry": self._get_cert_expiry(path),
                }
            elif path:
                results[name] = {"path": path, "exists": False}
            else:
                results[name] = {"configured": False}

        return results

    def _get_cert_expiry(self, cert_path: str) -> Optional[str]:
        """Get certificate expiry date."""
        try:
            import subprocess
            result = subprocess.run(
                ["openssl", "x509", "-enddate", "-noout", "-in", cert_path],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip().replace("notAfter=", "")
        except Exception:
            pass
        return None

    async def _build_tls_summary(self) -> Dict[str, Any]:
        """Build overall TLS compliance summary."""
        mongo_tls = os.getenv("MONGODB_TLS_ENABLED", "false").lower() == "true"
        redis_tls = os.getenv("REDIS_TLS_ENABLED", "false").lower() == "true"
        backend_tls = bool(os.getenv("SSL_CERTFILE"))

        score = 0
        total = 5
        checks = []

        # 1. MongoDB TLS
        if mongo_tls:
            score += 1
            checks.append({"check": "MongoDB TLS", "status": "pass"})
        else:
            checks.append({"check": "MongoDB TLS", "status": "fail",
                          "recommendation": "Set MONGODB_TLS_ENABLED=true"})

        # 2. Redis TLS
        if redis_tls:
            score += 1
            checks.append({"check": "Redis TLS", "status": "pass"})
        else:
            checks.append({"check": "Redis TLS", "status": "fail",
                          "recommendation": "Use rediss:// URL and set REDIS_TLS_ENABLED=true"})

        # 3. Backend TLS (or upstream termination)
        if backend_tls or os.getenv("ENVIRONMENT") in ("prod", "staging"):
            score += 1
            checks.append({"check": "Backend TLS", "status": "pass"})
        else:
            checks.append({"check": "Backend TLS", "status": "warn",
                          "recommendation": "TLS should be terminated at ALB in production"})

        # 4. Field-level encryption key
        if self._encryption_key:
            score += 1
            checks.append({"check": "Field encryption key", "status": "pass"})
        else:
            checks.append({"check": "Field encryption key", "status": "fail",
                          "recommendation": "Set FIELD_ENCRYPTION_KEY for sensitive data"})

        # 5. MongoDB authentication
        mongo_url = os.getenv("MONGODB_URL", "")
        if os.getenv("MONGO_ROOT_USERNAME") or "@" in mongo_url:
            score += 1
            checks.append({"check": "MongoDB authentication", "status": "pass"})
        else:
            checks.append({"check": "MongoDB authentication", "status": "fail",
                          "recommendation": "Enable MongoDB authentication"})

        grade = "A" if score == total else "B" if score >= 4 else "C" if score >= 3 else "D" if score >= 2 else "F"

        return {
            "score": f"{score}/{total}",
            "grade": grade,
            "checks": checks,
        }

    # ------------------------------------------------------------------
    # Field-Level Encryption
    # ------------------------------------------------------------------

    def encrypt_field(self, plaintext: str) -> str:
        """Encrypt a sensitive field value using AES-256-GCM."""
        if not self._encryption_key:
            logger.warning("FIELD_ENCRYPTION_KEY not set — storing plaintext")
            return plaintext

        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            key = hashlib.sha256(self._encryption_key.encode()).digest()
            nonce = os.urandom(12)
            aesgcm = AESGCM(key)
            ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
            # Format: enc:v1:<base64(nonce + ciphertext)>
            payload = base64.b64encode(nonce + ciphertext).decode()
            return f"enc:v1:{payload}"
        except ImportError:
            logger.warning("cryptography package not installed — skipping encryption")
            return plaintext
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return plaintext

    def decrypt_field(self, encrypted: str) -> str:
        """Decrypt a field value."""
        if not encrypted.startswith("enc:v1:"):
            return encrypted  # Not encrypted

        if not self._encryption_key:
            raise ValueError("FIELD_ENCRYPTION_KEY required to decrypt")

        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            key = hashlib.sha256(self._encryption_key.encode()).digest()
            payload = base64.b64decode(encrypted[7:])  # Skip "enc:v1:"
            nonce = payload[:12]
            ciphertext = payload[12:]
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext.decode()
        except ImportError:
            raise ValueError("cryptography package required for decryption")

    def is_encrypted(self, value: str) -> bool:
        """Check if a value is encrypted."""
        return isinstance(value, str) and value.startswith("enc:v1:")

    # ------------------------------------------------------------------
    # Sensitive Field Detection
    # ------------------------------------------------------------------

    def detect_sensitive_fields(
        self, document: Dict[str, Any], path: str = ""
    ) -> List[Dict[str, Any]]:
        """Scan a document for potentially sensitive unencrypted fields."""
        findings = []
        for key, value in document.items():
            full_path = f"{path}.{key}" if path else key
            key_lower = key.lower()

            if isinstance(value, dict):
                findings.extend(self.detect_sensitive_fields(value, full_path))
            elif isinstance(value, str):
                is_sensitive = any(p in key_lower for p in SENSITIVE_FIELD_PATTERNS)
                if is_sensitive and not self.is_encrypted(value):
                    findings.append({
                        "field": full_path,
                        "encrypted": False,
                        "recommendation": "Encrypt this field using encrypt_field()",
                    })
                elif is_sensitive and self.is_encrypted(value):
                    findings.append({
                        "field": full_path,
                        "encrypted": True,
                    })
        return findings

    # ------------------------------------------------------------------
    # Audit Logging
    # ------------------------------------------------------------------

    async def log_encryption_event(
        self,
        event_type: str,
        details: Dict[str, Any],
        user_id: Optional[str] = None,
    ):
        """Log an encryption-related event for audit."""
        doc = {
            "log_id": str(uuid.uuid4()),
            "event_type": event_type,
            "details": details,
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
        }
        try:
            await self.encryption_logs.insert_one(doc)
        except Exception as e:
            logger.error(f"Failed to log encryption event: {e}")

    async def get_encryption_logs(
        self, event_type: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get encryption audit logs."""
        query: Dict[str, Any] = {}
        if event_type:
            query["event_type"] = event_type

        cursor = self.encryption_logs.find(query).sort("timestamp", -1).limit(limit)
        docs = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            docs.append(doc)
        return docs

    # ------------------------------------------------------------------
    # Collection Encryption Audit
    # ------------------------------------------------------------------

    async def audit_collections(self) -> Dict[str, Any]:
        """Audit all collections for sensitive unencrypted data."""
        collections = await self.db.list_collection_names()
        results = []

        # Collections likely to contain sensitive data
        sensitive_collections = [
            "users", "api_keys", "sso_configurations",
            "mfa_secrets", "personas",
        ]

        for coll_name in collections:
            if coll_name not in sensitive_collections:
                continue

            coll = self.db[coll_name]
            sample = await coll.find_one()
            if not sample:
                continue

            sample.pop("_id", None)
            findings = self.detect_sensitive_fields(sample)
            if findings:
                results.append({
                    "collection": coll_name,
                    "findings": findings,
                    "sample_scanned": True,
                })

        return {
            "total_collections": len(collections),
            "sensitive_collections_checked": len(sensitive_collections),
            "collections_with_findings": len(results),
            "details": results,
            "scanned_at": datetime.utcnow().isoformat(),
        }
