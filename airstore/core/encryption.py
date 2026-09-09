import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

class EncryptionError(Exception):
    """Exception raised when chunk encryption/decryption fails or authentication tag is invalid."""
    pass

class ChunkEncryptor:
    """
    AES-256-GCM chunk encryptor.
    Provides authenticated chunk encryption and decryption.
    """
    NONCE_SIZE = 12  # Standard 96-bit GCM nonce

    def __init__(self, key: bytes):
        if len(key) not in (16, 24, 32):
            raise ValueError("AES key must be 16, 24, or 32 bytes long.")
        self.key = key
        self._aesgcm = AESGCM(key)

    def encrypt_chunk(self, chunk_data: bytes, associated_data: bytes = None) -> bytes:
        """
        Encrypt chunk bytes using AES-GCM.
        Returns: nonce (12 bytes) + ciphertext_with_tag
        """
        nonce = os.urandom(self.NONCE_SIZE)
        ciphertext = self._aesgcm.encrypt(nonce, chunk_data, associated_data)
        return nonce + ciphertext

    def decrypt_chunk(self, encrypted_data: bytes, associated_data: bytes = None) -> bytes:
        """
        Decrypt payload using AES-GCM and verify integrity tag.
        Expects: nonce (12 bytes) + ciphertext_with_tag
        """
        if len(encrypted_data) < self.NONCE_SIZE + 16:
            raise EncryptionError("Encrypted payload is too short to contain nonce and authentication tag.")
        
        nonce = encrypted_data[:self.NONCE_SIZE]
        ciphertext = encrypted_data[self.NONCE_SIZE:]
        
        try:
            plaintext = self._aesgcm.decrypt(nonce, ciphertext, associated_data)
            return plaintext
        except InvalidTag as e:
            raise EncryptionError("Data corruption or tampered encryption key/tag detected (InvalidTag).") from e
        except Exception as e:
            raise EncryptionError(f"Decryption failed: {str(e)}") from e
