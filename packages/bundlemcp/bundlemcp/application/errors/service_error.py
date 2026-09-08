class ServiceError(Exception):
    """Base class for domain errors; the message becomes the response detail.

    ``status`` is the HTTP status the error maps to when it reaches an HTTP
    edge. Declared on the class so a subclass of a subclass inherits its
    parent's status instead of falling through to a 500.
    """

    status: int = 500
