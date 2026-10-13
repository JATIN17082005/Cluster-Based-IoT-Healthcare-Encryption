"""Cryptographic engine for IoT healthcare data encryption.
Implements:
1. Production-grade AES-256-GCM authenticated encryption for high-sensitivity records.
2. Experimental lightweight XOR transformation with HMAC-SHA-256 integrity check.
3. Safe ephemeral key management with zero key leakage in logs or representations.
"""

import os
import time
import hmac
import hashlib
import secrets
import json
from datetime import datetime, timezone
from typing import Tuple, Optional, Set
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

from src.models import (
    SensorRecord,
    EncryptedEnvelope,
    EncryptionAlgorithm,
    SensitivityLevel,
)


class KeyManager:
    """Manages encryption keys with safe ephemeral fallback.
    Never exposes key bytes in __repr__ or __str__.
    """

    def __init__(
        self,
        aes_key: Optional[bytes] = None,
        xor_key: Optional[bytes] = None,
        hmac_key: Optional[bytes] = None,
    ):
        env_aes = os.environ.get("IOT_AES_KEY_HEX")
        env_xor = os.environ.get("IOT_XOR_KEY_HEX")
        env_hmac = os.environ.get("IOT_HMAC_KEY_HEX")

        self.is_ephemeral = False

        if aes_key:
            self._aes_key = aes_key
        elif env_aes:
            self._aes_key = bytes.fromhex(env_aes)
        else:
            self._aes_key = secrets.token_bytes(32)  # 256-bit AES key
            self.is_ephemeral = True

        if xor_key:
            self._xor_key = xor_key
        elif env_xor:
            self._xor_key = bytes.fromhex(env_xor)
        else:
            self._xor_key = secrets.token_bytes(32)
            self.is_ephemeral = True

        if hmac_key:
            self._hmac_key = hmac_key
        elif env_hmac:
            self._hmac_key = bytes.fromhex(env_hmac)
        else:
            self._hmac_key = secrets.token_bytes(32)
            self.is_ephemeral = True

        # Ensure proper key lengths
        if len(self._aes_key) != 32:
            raise ValueError(f"AES key must be 32 bytes (256 bits), got {len(self._aes_key)}")
        if len(self._xor_key) < 16:
            raise ValueError("XOR key must be at least 16 bytes")
        if len(self._hmac_key) < 16:
            raise ValueError("HMAC key must be at least 16 bytes")

    @property
    def aes_key(self) -> bytes:
        return self._aes_key

    @property
    def xor_key(self) -> bytes:
        return self._xor_key

    @property
    def hmac_key(self) -> bytes:
        return self._hmac_key

    def __repr__(self) -> str:
        status = "EPHEMERAL_DEV_KEYS" if self.is_ephemeral else "CONFIGURED_KEYS"
        return f"<KeyManager status={status} (Key material REDACTED)>"

    def __str__(self) -> str:
        return self.__repr__()


class AES256GCMService:
    """NIST-compliant AES-256-GCM authenticated encryption service.
    Enforces fresh 96-bit nonce generation and prevents nonce reuse.
    """

    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("AES-256-GCM requires exactly a 32-byte key")
        self._key = key
        self._cipher = AESGCM(self._key)
        self._used_nonces: Set[bytes] = set()

    def encrypt(
        self,
        plaintext: bytes,
        associated_data: Optional[bytes] = None,
    ) -> Tuple[bytes, bytes, bytes]:
        """Encrypt plaintext using AES-256-GCM.
        Returns: (nonce_12_bytes, ciphertext_bytes, tag_16_bytes)
        """
        # Generate cryptographically secure fresh 96-bit (12-byte) nonce
        nonce = secrets.token_bytes(12)
        while nonce in self._used_nonces:
            nonce = secrets.token_bytes(12)
        self._used_nonces.add(nonce)

        # AESGCM.encrypt returns ciphertext concatenated with 16-byte authentication tag
        ct_with_tag = self._cipher.encrypt(nonce, plaintext, associated_data)
        ciphertext = ct_with_tag[:-16]
        tag = ct_with_tag[-16:]

        return nonce, ciphertext, tag

    def decrypt(
        self,
        nonce: bytes,
        ciphertext: bytes,
        tag: bytes,
        associated_data: Optional[bytes] = None,
    ) -> bytes:
        """Decrypt and authenticate ciphertext using AES-256-GCM.
        Raises InvalidTag if ciphertext, tag, or associated_data has been tampered with.
        """
        ct_with_tag = ciphertext + tag
        return self._cipher.decrypt(nonce, ct_with_tag, associated_data)


class XORLightweightService:
    """Experimental lightweight XOR transformation module with HMAC-SHA-256 integrity tag.

    IMPORTANT SECURITY NOTICE:
    This module is provided strictly as an academic lightweight benchmark baseline.
    XOR stream transformations without authenticated AEAD do NOT provide production-grade
    confidentiality or forward secrecy for healthcare records. HMAC-SHA-256 provides
    tamper detection only, but does not remediate keystream leakage vulnerabilities.
    """

    def __init__(self, xor_key: bytes, hmac_key: bytes):
        self._xor_key = xor_key
        self._hmac_key = hmac_key
        self.last_auth_time_ns: float = 0.0

    def _generate_keystream(self, iv: bytes, length: int) -> bytes:
        """Derive record-specific keystream using key + IV expansion to avoid fixed mask reuse."""
        keystream = bytearray()
        counter = 0
        while len(keystream) < length:
            block = hashlib.sha256(
                self._xor_key + iv + counter.to_bytes(4, byteorder="big")
            ).digest()
            keystream.extend(block)
            counter += 1
        return bytes(keystream[:length])

    def encrypt(self, plaintext: bytes) -> Tuple[bytes, bytes, bytes]:
        """Encrypt plaintext using experimental XOR with HMAC-SHA-256 tag.
        Returns: (iv_12_bytes, ciphertext_bytes, hmac_32_bytes)
        """
        iv = secrets.token_bytes(12)
        keystream = self._generate_keystream(iv, len(plaintext))

        ciphertext = bytes(p ^ k for p, k in zip(plaintext, keystream))

        # Compute HMAC-SHA-256 over IV + ciphertext for integrity verification
        t_auth_0 = time.perf_counter_ns()
        h = hmac.new(self._hmac_key, iv + ciphertext, hashlib.sha256)
        hmac_tag = h.digest()
        self.last_auth_time_ns = float(time.perf_counter_ns() - t_auth_0)

        return iv, ciphertext, hmac_tag

    def decrypt(self, iv: bytes, ciphertext: bytes, hmac_tag: bytes) -> bytes:
        """Verify HMAC integrity and reverse XOR transformation.
        Raises ValueError if HMAC verification fails.
        """
        expected_h = hmac.new(self._hmac_key, iv + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(expected_h, hmac_tag):
            raise ValueError("XOR HMAC-SHA-256 integrity verification failed: envelope tampered")

        keystream = self._generate_keystream(iv, len(ciphertext))
        plaintext = bytes(c ^ k for c, k in zip(ciphertext, keystream))
        return plaintext


class EncryptionEngine:
    """Orchestrates record encryption into serialized EncryptedEnvelopes."""

    def __init__(self, key_manager: Optional[KeyManager] = None):
        self.key_manager = key_manager or KeyManager()
        self.aes_service = AES256GCMService(self.key_manager.aes_key)
        self.xor_service = XORLightweightService(
            self.key_manager.xor_key, self.key_manager.hmac_key
        )

    def encrypt_record(
        self,
        record: SensorRecord,
        run_id: str,
        algorithm: EncryptionAlgorithm,
        pre_serialized_bytes: Optional[bytes] = None,
    ) -> EncryptedEnvelope:
        """Serialize and encrypt a SensorRecord into an EncryptedEnvelope.
        If pre_serialized_bytes is supplied, avoids duplicate JSON serialization.
        """
        if pre_serialized_bytes is not None:
            serialized_bytes = pre_serialized_bytes
        else:
            serialized_bytes = json.dumps(
                record.model_dump(), sort_keys=True
            ).encode("utf-8")

        created_at = datetime.now(timezone.utc).isoformat()
        cluster_id = record.cluster_id or (
            "CLUSTER-HIGH"
            if record.sensitivity == SensitivityLevel.HIGH
            else "CLUSTER-LOW"
        )
        sensitivity = record.sensitivity or SensitivityLevel.LOW

        if algorithm == EncryptionAlgorithm.AES_256_GCM:
            # Associated authenticated data includes record ID and sensitivity
            aad = f"{record.record_id}:{sensitivity.value}".encode("utf-8")
            nonce, ct, tag = self.aes_service.encrypt(serialized_bytes, associated_data=aad)
            return EncryptedEnvelope(
                run_id=run_id,
                record_id=record.record_id,
                algorithm=algorithm,
                sensitivity=sensitivity,
                cluster_id=cluster_id,
                nonce_hex=nonce.hex(),
                ciphertext_hex=ct.hex(),
                tag_hex=tag.hex(),
                hmac_hex=None,
                payload_bytes=len(ct),
                created_at=created_at,
            )
        elif algorithm == EncryptionAlgorithm.XOR_LIGHTWEIGHT:
            iv, ct, hmac_tag = self.xor_service.encrypt(serialized_bytes)
            return EncryptedEnvelope(
                run_id=run_id,
                record_id=record.record_id,
                algorithm=algorithm,
                sensitivity=sensitivity,
                cluster_id=cluster_id,
                nonce_hex=iv.hex(),
                ciphertext_hex=ct.hex(),
                tag_hex=None,
                hmac_hex=hmac_tag.hex(),
                payload_bytes=len(ct),
                created_at=created_at,
            )
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")


def tamper_envelope(
    envelope: EncryptedEnvelope,
    target: str = "ciphertext",
) -> EncryptedEnvelope:
    """Creates a modified copy of an envelope for tamper rejection testing."""
    tampered_dict = envelope.model_dump()
    tampered_dict["tampered"] = True

    if target == "ciphertext":
        ct_bytes = bytearray(bytes.fromhex(envelope.ciphertext_hex))
        if ct_bytes:
            ct_bytes[0] ^= 0xFF  # Flip bits
        tampered_dict["ciphertext_hex"] = ct_bytes.hex()
    elif target == "tag" and envelope.tag_hex:
        tag_bytes = bytearray(bytes.fromhex(envelope.tag_hex))
        tag_bytes[0] ^= 0xFF
        tampered_dict["tag_hex"] = tag_bytes.hex()
    elif target == "hmac" and envelope.hmac_hex:
        hmac_bytes = bytearray(bytes.fromhex(envelope.hmac_hex))
        hmac_bytes[0] ^= 0xFF
        tampered_dict["hmac_hex"] = hmac_bytes.hex()
    elif target == "nonce":
        nonce_bytes = bytearray(bytes.fromhex(envelope.nonce_hex))
        nonce_bytes[0] ^= 0xFF
        tampered_dict["nonce_hex"] = nonce_bytes.hex()

    return EncryptedEnvelope(**tampered_dict)
