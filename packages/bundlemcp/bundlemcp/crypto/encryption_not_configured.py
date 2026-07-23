class EncryptionNotConfigured(RuntimeError):
    """Raised when an upstream-oauth server needs crypto but no keys are set."""
