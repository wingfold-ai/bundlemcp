"""Which subject a caller is named by, and that older stored records still read."""

import uuid
from datetime import UTC, datetime

from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.access.identity_subject import IdentitySubject
from bundlemcp.domain.access.user import User
from bundlemcp.domain.delegation.delegated_token import DelegatedToken
from bundlemcp.domain.sessions.session_record import SessionRecord

USER = User(oidc_issuer="http://idp", oidc_sub="kc-alice", email="alice@example.com")
KEY = uuid.uuid4()


def test_mid1_an_oauth_user_carries_the_idp_subject():
    identity = CallerIdentity.oauth_user(USER)
    assert (identity.sub, identity.oidc_issuer, identity.oidc_sub) == (
        str(USER.id),
        "http://idp",
        "kc-alice",
    )


def test_mid1_an_api_key_and_an_anonymous_caller_carry_no_idp_subject():
    for identity in (CallerIdentity.with_api_key(KEY), CallerIdentity.anonymous()):
        assert (identity.oidc_issuer, identity.oidc_sub) == (None, None)


def test_fwd3_a_user_is_named_in_the_chosen_namespace():
    identity = CallerIdentity.oauth_user(USER)
    assert identity.subject_for(IdentitySubject.INTERNAL) == str(USER.id)
    assert identity.subject_for(IdentitySubject.OIDC) == "kc-alice"


def test_fwd3_a_key_and_nobody_are_named_alike_in_either_namespace():
    for namespace in IdentitySubject:
        assert CallerIdentity.with_api_key(KEY).subject_for(namespace) == f"api_key:{KEY}"
        assert CallerIdentity.anonymous().subject_for(namespace) is None


def test_dep6_a_session_record_written_before_the_idp_subject_still_reads():
    stored = (
        '{"version": 2, "session_id": "s", "endpoint_name": "main", "bundle_name": "main", '
        '"protocol_version": "2025-11-25", "identity": {"auth_method": "oauth", '
        f'"user_id": "{USER.id}", "user_email": null, "api_key_id": null}}}}'
    )
    record = SessionRecord.model_validate_json(stored)
    assert record.identity.oidc_sub is None
    assert record.is_owned_by(CallerIdentity.oauth_user(USER))


def test_dep6_a_delegated_token_written_before_the_idp_subject_still_reads():
    stored = (
        '{"sub": "u1", "server_id": "' + str(uuid.uuid4()) + '", "audience": "http://s/mcp", '
        f'"expires_at": "{datetime(2026, 1, 1, tzinfo=UTC).isoformat()}"}}'
    )
    token = DelegatedToken.model_validate_json(stored)
    assert (token.oidc_issuer, token.oidc_sub) == (None, None)
