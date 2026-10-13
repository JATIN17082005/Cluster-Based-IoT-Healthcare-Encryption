"""Phase 2 Unit Tests: Cryptographic Engines, Local Receiver, and Tamper Detection."""

import pytest
from src.models import (
    RecordType,
    SensitivityLevel,
    SensorRecord,
    EncryptionAlgorithm,
)
from src.crypto import (
    KeyManager,
    EncryptionEngine,
    tamper_envelope,
)
from src.receiver import LocalHealthcareReceiver


@pytest.fixture
def test_record() -> SensorRecord:
    return SensorRecord(
        record_id="REC-TEST-001",
        timestamp="2026-10-13T10:00:00Z",
        demo_patient_id="SYNTH-PAT-001",
        record_type=RecordType.HEART_RATE,
        value=78.5,
        unit="bpm",
        sensitivity=SensitivityLevel.LOW,
        classification_reason="Normal resting heart rate within physiological limits.",
        cluster_id="CLUSTER-LOW",
    )


@pytest.fixture
def high_record() -> SensorRecord:
    return SensorRecord(
        record_id="REC-TEST-002",
        timestamp="2026-10-13T10:00:01Z",
        demo_patient_id="SYNTH-PAT-001",
        record_type=RecordType.ECG_SUMMARY,
        value=1.42,
        unit="mV",
        sensitivity=SensitivityLevel.HIGH,
        classification_reason="Diagnostic ECG rhythm summary requires high protection.",
        cluster_id="CLUSTER-HIGH",
    )


def test_key_manager_redaction():
    """Verify that KeyManager never leaks secret keys in string/log representations."""
    km = KeyManager()
    rep = repr(km)
    st = str(km)
    assert km.aes_key.hex() not in rep
    assert km.xor_key.hex() not in rep
    assert km.hmac_key.hex() not in rep
    assert "REDACTED" in rep
    assert "REDACTED" in st


def test_aes256_gcm_roundtrip(high_record):
    """Verify that AES-256-GCM encryption and receiver verification reproduce the exact record."""
    km = KeyManager()
    engine = EncryptionEngine(km)
    receiver = LocalHealthcareReceiver(km)

    envelope = engine.encrypt_record(high_record, run_id="RUN-TEST-1", algorithm=EncryptionAlgorithm.AES_256_GCM)
    assert envelope.algorithm == EncryptionAlgorithm.AES_256_GCM
    assert envelope.tag_hex is not None
    assert envelope.hmac_hex is None

    result = receiver.receive_envelope(envelope)
    assert result.verified is True
    assert result.error_message is None
    assert result.decrypted_record is not None
    assert result.decrypted_record.record_id == high_record.record_id
    assert result.decrypted_record.value == high_record.value
    assert result.decrypted_record.record_type == high_record.record_type


def test_xor_roundtrip(test_record):
    """Verify that experimental XOR + HMAC encryption and receiver verification reproduce the exact record."""
    km = KeyManager()
    engine = EncryptionEngine(km)
    receiver = LocalHealthcareReceiver(km)

    envelope = engine.encrypt_record(test_record, run_id="RUN-TEST-2", algorithm=EncryptionAlgorithm.XOR_LIGHTWEIGHT)
    assert envelope.algorithm == EncryptionAlgorithm.XOR_LIGHTWEIGHT
    assert envelope.hmac_hex is not None
    assert envelope.tag_hex is None

    result = receiver.receive_envelope(envelope)
    assert result.verified is True
    assert result.error_message is None
    assert result.decrypted_record is not None
    assert result.decrypted_record.record_id == test_record.record_id
    assert result.decrypted_record.value == test_record.value


def test_aes_tamper_rejection(high_record):
    """Verify that altered AES ciphertext, tag, or nonce fails receiver verification."""
    km = KeyManager()
    engine = EncryptionEngine(km)
    receiver = LocalHealthcareReceiver(km)

    orig_envelope = engine.encrypt_record(high_record, run_id="RUN-TAMPER", algorithm=EncryptionAlgorithm.AES_256_GCM)

    # 1. Tamper ciphertext
    tampered_ct = tamper_envelope(orig_envelope, target="ciphertext")
    res1 = receiver.receive_envelope(tampered_ct)
    assert res1.verified is False
    assert "tampering detected" in res1.error_message

    # 2. Tamper tag
    tampered_tag = tamper_envelope(orig_envelope, target="tag")
    res2 = receiver.receive_envelope(tampered_tag)
    assert res2.verified is False
    assert "tampering detected" in res2.error_message

    # 3. Tamper nonce
    tampered_nonce = tamper_envelope(orig_envelope, target="nonce")
    res3 = receiver.receive_envelope(tampered_nonce)
    assert res3.verified is False
    assert "tampering detected" in res3.error_message


def test_xor_tamper_rejection(test_record):
    """Verify that altered XOR ciphertext or HMAC fails receiver verification."""
    km = KeyManager()
    engine = EncryptionEngine(km)
    receiver = LocalHealthcareReceiver(km)

    orig_envelope = engine.encrypt_record(test_record, run_id="RUN-TAMPER-XOR", algorithm=EncryptionAlgorithm.XOR_LIGHTWEIGHT)

    # 1. Tamper ciphertext
    tampered_ct = tamper_envelope(orig_envelope, target="ciphertext")
    res1 = receiver.receive_envelope(tampered_ct)
    assert res1.verified is False
    assert "integrity verification failed" in res1.error_message

    # 2. Tamper HMAC
    tampered_hmac = tamper_envelope(orig_envelope, target="hmac")
    res2 = receiver.receive_envelope(tampered_hmac)
    assert res2.verified is False
    assert "integrity verification failed" in res2.error_message


def test_nonce_uniqueness(high_record):
    """Verify that AES-256-GCM never reuses nonces across multiple encryptions."""
    km = KeyManager()
    engine = EncryptionEngine(km)
    nonces = set()

    for i in range(100):
        envelope = engine.encrypt_record(high_record, run_id="RUN-NONCE", algorithm=EncryptionAlgorithm.AES_256_GCM)
        assert envelope.nonce_hex not in nonces
        nonces.add(envelope.nonce_hex)

    assert len(nonces) == 100


def test_receiver_stats_tracking(high_record, test_record):
    """Verify that the receiver accurately tallies received, accepted, and rejected counts."""
    km = KeyManager()
    engine = EncryptionEngine(km)
    receiver = LocalHealthcareReceiver(km)
    run_id = "RUN-STATS-1"

    env_valid = engine.encrypt_record(high_record, run_id=run_id, algorithm=EncryptionAlgorithm.AES_256_GCM)
    env_tampered = tamper_envelope(env_valid, target="ciphertext")

    receiver.receive_envelope(env_valid)
    receiver.receive_envelope(env_tampered)

    stats = receiver.get_run_stats(run_id)
    assert stats["received"] == 2
    assert stats["accepted"] == 1
    assert stats["rejected"] == 1
