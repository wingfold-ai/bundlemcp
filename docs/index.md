---
layout: home

hero:
  text: One gateway for all your MCP servers
  tagline: Register Streamable HTTP MCP servers, compose them into bundles, and expose each bundle through endpoints shaped for claude.ai, ChatGPT or your own scripts. Self-hosted, restart-safe, horizontally scalable.
  image:
    src: /banner.svg
    alt: "bundlemcp: unified mcp server bundler"
  actions:
    - theme: brand
      text: Quickstart
      link: /guide/quickstart
    - theme: alt
      text: What is bundlemcp?
      link: /guide/what-is-bundlemcp
    - theme: alt
      text: GitHub
      link: https://github.com/mhoegger/bundlemcp

features:
  - icon: 🧩
    title: Bundle many servers into one
    details: A bundle aggregates the tools of several upstream MCP servers into a single virtual server, with per-bundle tool curation and overrides.
    link: /manage/bundles
    linkText: Bundles and curation
  - icon: 🎯
    title: Per-client endpoints
    details: Expose the same bundle several times, each with its own auth modes, client profile and rate limits. claude.ai gets OAuth, ChatGPT gets re-annotated tools, scripts get an API key.
    link: /manage/endpoints
    linkText: Endpoints
  - icon: 🔐
    title: OAuth 2.1 built in
    details: The gateway runs its own authorization server with dynamic client registration, PKCE, consent and introspection. Humans log in through any OIDC provider.
    link: /connect/claude
    linkText: Connect claude.ai
  - icon: ♻️
    title: Restarts are non-events
    details: Configuration lives in Postgres, live sessions in Valkey. Any replica serves any session, so you can roll out new versions and scale out without dropping clients.
    link: /self-hosting/deploy
    linkText: Deploy it
  - icon: 🛠️
    title: Everything is an API
    details: The admin UI is a client of the same versioned REST API you can script against. Provision from a declarative bootstrap file or drive it from CI.
    link: /integrate/management-api
    linkText: Management API
  - icon: 🧾
    title: Audit and metering
    details: Every tool call is recorded. A documented metering hook lets an application layer plug in billing without forking the gateway.
    link: /integrate/metering-hook
    linkText: Metering hook
---
