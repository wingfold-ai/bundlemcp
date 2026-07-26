class ServiceError(Exception):
    """Base class for domain errors; the message becomes the response detail."""
