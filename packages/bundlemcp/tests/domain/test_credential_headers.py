"""Which request headers the call stages never see (PROT-24)."""

from bundlemcp.domain.access.credential_headers import CredentialHeaders


def test_prot24_credential_headers_are_removed_and_the_rest_kept():
    """PROT-24: authorization, cookie, proxy-authorization and the API-key header are removed,
    whatever their case; other headers are kept with lower-cased names."""
    kept = CredentialHeaders.removed_from(
        {
            "Authorization": "Bearer secret",
            "Cookie": "session=1",
            "Proxy-Authorization": "Basic x",
            "X-API-Key": "bmcp_sk_x",
            "User-Agent": "probe/1",
            "x-request-source": "ci",
        }
    )
    assert kept == {"user-agent": "probe/1", "x-request-source": "ci"}
