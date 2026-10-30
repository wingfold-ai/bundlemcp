class StoreConflict(Exception):
    """A write was refused because a concurrent write stored the same unique key first.

    Raised by a unit of work when the store rejects a transaction for breaking a
    uniqueness or integrity rule. The request lost a race; reading again and
    retrying can succeed. The message names the rule when the store reports it,
    never the values involved.
    """
