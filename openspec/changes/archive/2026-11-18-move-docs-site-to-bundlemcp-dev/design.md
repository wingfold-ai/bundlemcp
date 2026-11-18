# Design

## Context

The site is static files on Infomaniak web hosting behind Apache, where `docs/public/.htaccess` already redirects
HTTP to HTTPS. TLS ends at Infomaniak's proxy, which passes the protocol in `X-Forwarded-Proto`. The hosting now
serves `bundlemcp.dev` and `bundlemcp.com`, each with its `www` name, under one certificate. Nothing here touches the
gateway's layers.

## Goals / Non-Goals

**Goals:** one canonical address, and old links that land on the right page.

**Non-Goals:** Search Console setup (outside the repository); changing which domain Infomaniak calls the main one.

## Decisions

- **The redirect lives in `.htaccess`, not in Infomaniak's domain-redirect feature.** It is versioned with the site,
  keeps path and query, and needs both domains on one hosting, which they are.
- **One rule, by host name, before the HTTPS rule.** Any host other than `bundlemcp.dev` (case-insensitive) gets
  `301` to `https://bundlemcp.dev/<path>`, so `http://bundlemcp.com/x` takes one hop rather than two.
- **The domain stays a constant** in `config.ts`, the sitemap check and the publish workflow, as before.

## Risks / Trade-offs

- [The rule is Apache-only and has no hermetic test] → Verified against a real Apache (`httpd:2.4`) with the built
  site, and against the live site after publishing.
- [Infomaniak's preview host names redirect too] → Intended: the site has one address.
