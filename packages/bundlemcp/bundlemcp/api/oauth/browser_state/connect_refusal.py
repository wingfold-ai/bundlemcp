from enum import StrEnum


class ConnectRefusal(StrEnum):
    """Why a connect callback may not be completed by the browser session it arrived in."""

    NO_SESSION = "no_session"
    OTHER_USER = "other_user"
    NOT_ADMIN = "not_admin"
