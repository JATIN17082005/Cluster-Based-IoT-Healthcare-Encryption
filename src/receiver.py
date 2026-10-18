"""Local healthcare receiver service.
Receives encrypted envelopes, authenticates integrity/tags, decrypts payloads,
and verifies reconstructed sensor records.
"""

import json
from datetime import datetime, timezone
from typing import List, Dict, Optional
from cryptography.exceptions import InvalidTag

from src.models import (
    EncryptedEnvelope,
    ReceiverVerificationResult,
    SensorRecord,
    EncryptionAlgorithm,
)
from src.crypto import KeyManager, AES256GCMService, XORLightweightService


class LocalHealthcareReceiver:
    """Local healthcare-server receiver simulating the clinical IoT ingestion endpoint."""

    def __init__(self, key_manager: Optional[KeyManager] = None):
        self.key_manager = key_manager or KeyManager()
        self.aes_service = AES256GCMService(self.key_manager.aes_key)
        self.xor_service = XORLightweightService(
            self.key_manager.xor_key, self.key_manager.hmac_key
        )

        # Run-level tracking: run_id -> stats
        self._stats: Dict[str, Dict[str, int]] = {}
        self._results_by_run: Dict[str, List[ReceiverVerificationResult]] = {}

    def reset_stats(self, run_id: Optional[str] = None):
        """Reset receiver statistics for a specific run or all runs."""
        if run_id:
            self._stats.pop(run_id, None)
            self._results_by_run.pop(run_id, None)
        else:
            self._stats.clear()
            self._results_by_run.clear()

    def receive_envelope(self, envelope: EncryptedEnvelope) -> ReceiverVerificationResult:
        """Receive, authenticate, and decrypt an incoming encrypted envelope."""
        now_iso = datetime.now(timezone.utc).isoformat()
        run_id = envelope.run_id

        if run_id not in self._stats:
            self._stats[run_id] = {"received": 0, "accepted": 0, "rejected": 0}
            self._results_by_run[run_id] = []

        self._stats[run_id]["received"] += 1

        try:
            if envelope.algorithm == EncryptionAlgorithm.AES_256_GCM:
                if not envelope.tag_hex:
                    raise ValueError("Missing AES-256-GCM authentication tag")

                nonce = bytes.fromhex(envelope.nonce_hex)
                ciphertext = bytes.fromhex(envelope.ciphertext_hex)
                tag = bytes.fromhex(envelope.tag_hex)
                aad = f"{envelope.record_id}:{envelope.sensitivity.value}".encode("utf-8")

                try:
                    decrypted_bytes = self.aes_service.decrypt(
                        nonce, ciphertext, tag, associated_data=aad
                    )
                except InvalidTag:
                    raise ValueError("AES-256-GCM authentication tag mismatch (tampering detected)")

            elif envelope.algorithm == EncryptionAlgorithm.XOR_LIGHTWEIGHT:
                if not envelope.hmac_hex:
                    raise ValueError("Missing XOR HMAC-SHA-256 integrity tag")

                iv = bytes.fromhex(envelope.nonce_hex)
                ciphertext = bytes.fromhex(envelope.ciphertext_hex)
                hmac_tag = bytes.fromhex(envelope.hmac_hex)

                decrypted_bytes = self.xor_service.decrypt(iv, ciphertext, hmac_tag)
            else:
                raise ValueError(f"Unknown encryption algorithm '{envelope.algorithm}'")

            # Parse decrypted JSON back to SensorRecord
            record_data = json.loads(decrypted_bytes.decode("utf-8"))
            reconstructed_record = SensorRecord(**record_data)

            self._stats[run_id]["accepted"] += 1
            result = ReceiverVerificationResult(
                record_id=envelope.record_id,
                verified=True,
                algorithm=envelope.algorithm,
                decrypted_record=reconstructed_record,
                error_message=None,
                arrival_timestamp=now_iso,
            )
            self._results_by_run[run_id].append(result)
            return result

        except Exception as e:
            self._stats[run_id]["rejected"] += 1
            result = ReceiverVerificationResult(
                record_id=envelope.record_id,
                verified=False,
                algorithm=envelope.algorithm,
                decrypted_record=None,
                error_message=str(e),
                arrival_timestamp=now_iso,
            )
            self._results_by_run[run_id].append(result)
            return result

    def get_run_stats(self, run_id: str) -> Dict[str, int]:
        """Return counts of received, accepted, and rejected packets for a run."""
        return self._stats.get(run_id, {"received": 0, "accepted": 0, "rejected": 0})

    def get_stats(self) -> Dict[str, Any]:
        """Return total aggregated receiver statistics across all runs."""
        total_recv = sum(s.get("received", 0) for s in self._stats.values())
        total_acc = sum(s.get("accepted", 0) for s in self._stats.values())
        total_rej = sum(s.get("rejected", 0) for s in self._stats.values())
        return {
            "total_received": total_recv,
            "total_accepted": total_acc,
            "total_rejected": total_rej,
            "active_runs": list(self._stats.keys()),
        }

    def get_run_results(self, run_id: str) -> List[ReceiverVerificationResult]:
        """Return detailed verification results for a run."""
        return self._results_by_run.get(run_id, [])

