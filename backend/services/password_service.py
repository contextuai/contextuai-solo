"""
Password Service for secure password hashing and verification.

Uses Python's built-in hashlib with PBKDF2-SHA256 for secure password storage.
No external dependencies required.
"""

import hashlib
import secrets
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# PBKDF2 Configuration
HASH_ALGORITHM = "sha256"
ITERATIONS = 100000  # OWASP recommended minimum
SALT_LENGTH = 32  # 256 bits
HASH_LENGTH = 32  # 256 bits


class PasswordService:
    """Service for password hashing and verification using PBKDF2."""

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a password using PBKDF2-SHA256.

        Args:
            password: Plain text password

        Returns:
            Hashed password in format: salt$hash (both hex encoded)
        """
        # Generate random salt
        salt = secrets.token_bytes(SALT_LENGTH)

        # Hash password with PBKDF2
        password_hash = hashlib.pbkdf2_hmac(
            HASH_ALGORITHM,
            password.encode('utf-8'),
            salt,
            ITERATIONS,
            dklen=HASH_LENGTH
        )

        # Return salt and hash as hex strings
        return f"{salt.hex()}${password_hash.hex()}"

    @staticmethod
    def verify_password(password: str, stored_hash: str) -> bool:
        """
        Verify a password against a stored hash.

        Args:
            password: Plain text password to verify
            stored_hash: Stored hash in format: salt$hash

        Returns:
            True if password matches, False otherwise
        """
        try:
            # Split stored hash into salt and hash
            parts = stored_hash.split('$')
            if len(parts) != 2:
                logger.error("Invalid hash format")
                return False

            salt_hex, hash_hex = parts
            salt = bytes.fromhex(salt_hex)
            stored_password_hash = bytes.fromhex(hash_hex)

            # Hash the provided password with the same salt
            password_hash = hashlib.pbkdf2_hmac(
                HASH_ALGORITHM,
                password.encode('utf-8'),
                salt,
                ITERATIONS,
                dklen=HASH_LENGTH
            )

            # Compare hashes using constant-time comparison
            return secrets.compare_digest(password_hash, stored_password_hash)

        except ValueError as e:
            logger.error(f"Error verifying password: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error verifying password: {str(e)}")
            return False

    @staticmethod
    def is_password_strong(password: str) -> Tuple[bool, str]:
        """
        Check if password meets strength requirements.

        Requirements:
        - At least 8 characters
        - Contains at least one uppercase letter
        - Contains at least one lowercase letter
        - Contains at least one digit

        Args:
            password: Password to check

        Returns:
            Tuple of (is_valid, error_message)
        """
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"

        if not any(c.isupper() for c in password):
            return False, "Password must contain at least one uppercase letter"

        if not any(c.islower() for c in password):
            return False, "Password must contain at least one lowercase letter"

        if not any(c.isdigit() for c in password):
            return False, "Password must contain at least one digit"

        return True, ""
