"""Profile crypto operations in detail to investigate the performance regression."""

import time
import secrets
import hashlib
import hmac
import json
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def profile():
    plaintext = b'{"demo_patient_id": "SYNTH-PAT-001", "record_id": "REC-001", "value": 72.0, "unit": "bpm"}'
    aes_key = secrets.token_bytes(32)
    xor_key = secrets.token_bytes(32)
    hmac_key = secrets.token_bytes(32)
    aesgcm = AESGCM(aes_key)

    N = 5000

    # Warmup
    for _ in range(500):
        nonce = secrets.token_bytes(12)
        ct = aesgcm.encrypt(nonce, plaintext, b"AAD")

    # 1. AES-256-GCM
    t0 = time.perf_counter_ns()
    for _ in range(N):
        nonce = secrets.token_bytes(12)
        ct = aesgcm.encrypt(nonce, plaintext, b"AAD")
    t_aes = (time.perf_counter_ns() - t0) / N

    # 2. XOR Keystream expansion via SHA-256 in Python
    t0 = time.perf_counter_ns()
    for _ in range(N):
        iv = secrets.token_bytes(12)
        block = hashlib.sha256(xor_key + iv + (0).to_bytes(4, "big")).digest()[:len(plaintext)]
    t_keystream = (time.perf_counter_ns() - t0) / N

    # 3. XOR bitwise zip loop in Python
    iv = secrets.token_bytes(12)
    ks = hashlib.sha256(xor_key + iv + (0).to_bytes(4, "big")).digest()[:len(plaintext)]
    t0 = time.perf_counter_ns()
    for _ in range(N):
        ct = bytes(p ^ k for p, k in zip(plaintext, ks))
    t_xor_loop = (time.perf_counter_ns() - t0) / N

    # 4. HMAC-SHA-256
    ct = bytes(p ^ k for p, k in zip(plaintext, ks))
    t0 = time.perf_counter_ns()
    for _ in range(N):
        h = hmac.new(hmac_key, iv + ct, hashlib.sha256).digest()
    t_hmac = (time.perf_counter_ns() - t0) / N

    total_xor_route = t_keystream + t_xor_loop + t_hmac

    print("=== Cryptographic Profiling Results (N = 5000 runs) ===")
    print(f"1. AES-256-GCM (OpenSSL + AES-NI in C):     {t_aes/1000.0:8.3f} us ({t_aes/1e6:.6f} ms)")
    print(f"2. XOR Keystream Generation (SHA-256 block):{t_keystream/1000.0:8.3f} us ({t_keystream/1e6:.6f} ms)")
    print(f"3. XOR Bitwise Loop (bytes(p ^ k)):         {t_xor_loop/1000.0:8.3f} us ({t_xor_loop/1e6:.6f} ms)")
    print(f"4. HMAC-SHA-256 (Integrity Tag):            {t_hmac/1000.0:8.3f} us ({t_hmac/1e6:.6f} ms)")
    print(f"-----------------------------------------------------------------")
    print(f"Total Proposed XOR Route (2 + 3 + 4):       {total_xor_route/1000.0:8.3f} us ({total_xor_route/1e6:.6f} ms)")
    print(f"Ratio (Proposed / Baseline):                {total_xor_route / t_aes:8.2f}x")

if __name__ == "__main__":
    profile()
