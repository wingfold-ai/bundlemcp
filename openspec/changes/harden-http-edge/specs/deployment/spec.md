## MODIFIED Requirements

### Requirement: DEP-2 Trusted proxies decide the client IP
Trusted-proxy config (`BUNDLEMCP_TRUSTED_PROXIES`, CIDR list): `X-Forwarded-For`, `X-Forwarded-Proto` and
`X-Forwarded-Host` MUST be honored only when the direct peer is in the list; otherwise they are ignored and the socket
peer is the client IP. The client IP used for rate limiting ([EP-16](../../../../specs/endpoints/spec.md)), the
auth-failure lockout and per-IP client-registration limits derives from this policy — XFF from untrusted peers is never
believed ([ADR-0018](../../../../../docs/adr/0018-rate-limiting.md)). When the peer is trusted, the XFF list is read
from the right and the first entry that is not itself a trusted proxy is the client IP; the entries to its left were
written by the client and are never used. When every entry is a trusted proxy, the leftmost entry is taken. From a
trusted peer, `X-Forwarded-Proto` and `X-Forwarded-Host` set the scheme and host of the request as the gateway sees
it; every published URL still derives from the public URL ([DEP-1](../../../../specs/deployment/spec.md)). No
component other than this policy interprets forwarding headers.

#### Scenario: Untrusted peer cannot spoof its IP
- **GIVEN** `BUNDLEMCP_TRUSTED_PROXIES` is empty
- **WHEN** a request from `203.0.113.7` carries `X-Forwarded-For: 10.0.0.1`
- **THEN** the client IP is `203.0.113.7`

#### Scenario: Trusted proxy forwards the client IP
- **GIVEN** `BUNDLEMCP_TRUSTED_PROXIES=["172.16.0.0/12"]`
- **WHEN** a request from `172.18.0.2` carries `X-Forwarded-For: 198.51.100.4, 172.18.0.1`
- **THEN** the client IP is `198.51.100.4`

#### Scenario: Client-written entries are ignored
- **GIVEN** `BUNDLEMCP_TRUSTED_PROXIES=["172.16.0.0/12"]`
- **WHEN** a request from `172.18.0.2` carries `X-Forwarded-For: 1.2.3.4, 198.51.100.4` because the client sent
  `X-Forwarded-For: 1.2.3.4` and the proxy appended the address it saw
- **THEN** the client IP is `198.51.100.4`, and rate limits and lockouts count against it

#### Scenario: Forwarded scheme and host from a trusted proxy
- **GIVEN** `BUNDLEMCP_TRUSTED_PROXIES=["172.16.0.0/12"]`
- **WHEN** a request from `172.18.0.2` carries `X-Forwarded-Proto: https` and `X-Forwarded-Host: gw.example.com`
- **THEN** the request's scheme is `https` and its host `gw.example.com`, while the same headers from an untrusted
  peer change nothing
