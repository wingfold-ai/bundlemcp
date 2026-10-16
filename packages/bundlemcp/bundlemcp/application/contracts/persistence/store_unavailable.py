class StoreUnavailable(Exception):
    """The durable store could not be reached: the request can be retried, not answered.

    Raised by a unit of work for connection-level failures only, never for a
    query that ran and failed, so it never stands for "not found" or "not allowed".
    """
