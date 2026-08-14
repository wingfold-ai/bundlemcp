class DecryptionError(RuntimeError):
    """Ciphertext could not be decrypted with any configured key (fail closed)."""
