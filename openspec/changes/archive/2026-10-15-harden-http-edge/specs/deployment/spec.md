## MODIFIED Requirements

### Requirement: DEP-2 Trusted proxies decide the client IP
Trusted-proxy config (`BUNDLEMCP_TRUSTED_PROXIES`, CIDR list): `X-Forwarded-For` MUST be honored only when the direct
peer is in the list; otherwise it is ignored and the socket peer is the client IP. The client IP used for rate limiting
([EP-16](../endpoints/spec.md)), the auth-failure lockout and per-IP client-registration limits derives from this policy
— XFF from untrusted peers is never believed ([ADR-0018](../../../docs/adr/0018-rate-limiting.md)). When the peer is
trusted, the XFF list is read from the right and the first entry that is not itself a trusted proxy is the client IP;
the entries to its left were written by the client and are never used. When every entry is a trusted proxy, the leftmost
entry is taken. `X-Forwarded-Proto` and `X-Forwarded-Host` are ignored from every peer, trusted or not: every externally
visible URL derives from the public URL ([DEP-1](../deployment/spec.md)), so the request's own scheme and host are never
used to build one. No component other than this policy interprets forwarding headers.

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

#### Scenario: Forwarded scheme and host are ignored
- **GIVEN** `BUNDLEMCP_TRUSTED_PROXIES=["172.16.0.0/12"]`
- **WHEN** a request from `172.18.0.2` carries `X-Forwarded-Proto: http` and `X-Forwarded-Host: evil.example`
- **THEN** the OAuth metadata and every redirect the gateway issues still name the public URL's scheme and host
