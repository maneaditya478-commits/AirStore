# AirStore Security Architecture

## 1. Integrity Verification
- Every chunk and overall file is hashed using **SHA-256**.
- Hashes are calculated on-the-fly via streaming read/write hooks without loading full files into RAM.
- Reconstruction compares computed file SHA-256 with original metadata. If a mismatch is detected, the corrupted file is automatically deleted and an `IntegrityError` is raised.

## 2. Authenticated Encryption
- Optional authenticated **AES-256-GCM** encryption for chunk payloads (`ChunkEncryptor`).
- Payload layout: `12-byte GCM Nonce` + `Ciphertext` + `16-byte GCM Tag`.
- Prevents silent chunk tampering or unauthorized disk access on storage nodes.

## 3. Node Authentication & Transport Security
- Shared cluster authorization secret (`AIRSTORE_AUTH_SECRET`) validates storage node registration.
- Modular HTTP client architecture allows enabling HTTPS/TLS endpoints for LAN transport security.
