"""The startup failure of an auth page that cannot be rendered."""


class BrokenAuthPage(RuntimeError):
    """An auth page's template did not load, compile or render with sample values.

    Raised while the gateway starts, so a broken operator override stops the
    start instead of failing a person's sign-in.
    """
