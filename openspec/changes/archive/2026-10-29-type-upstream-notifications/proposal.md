# Proposal

## Why

A member's notifications between calls (list changes, resource updates, log messages) reach the gateway as typed SDK
objects, and the gateway throws the types away:

- **The pool turns typed events into dicts.** The pooled upstream sessions dump each SDK notification to a JSON-RPC
  dict, and build dicts by hand for the events of a modern upstream's `subscriptions/listen` stream.
- **The application parses JSON-RPC by hand.** The notification router dispatches on an `if method == …` chain and
  digs `uri` and `level` out of `params` by key. A typo in a key, or a fifth method, fails silently. This is the
  pattern ADR-0027 removed from the MCP edge.
- **A member's own `_meta` rides along.** Because the dict is relayed as it arrived, whatever the member put in the
  notification's `_meta` reaches the client, although it describes the member's hop, not the client's.

Two things about resource subscriptions also need settling now that FastMCP 4.1.4 / MCP SDK 2.3 run on main:

- **Deprecated SDK calls.** For a handshake-era member the pool calls the SDK's `subscribe_resource` and
  `unsubscribe_resource`. The SDK marks both deprecated ("removed as of 2026-07-28; use `Client.listen()`"), for every
  session, so every test that subscribes warns, and a later SDK may drop the methods. The protocol request itself is
  not going away for those members: `resources/subscribe` is the only way a 2025-era server sends resource updates.
- **No replay after a lost listen stream.** For a modern member the pool already holds a `subscriptions/listen` stream,
  and re-opens it a second after it ends. The protocol replays nothing, so a list change or resource update made while
  the stream was down is never heard. The SDK's own guidance is "re-listen and refetch"; the pool only re-listens.

The 2026-10-29 code audit found the first and the deprecated calls (findings S8 and S23). No GitHub issue.

## What Changes

- **Notifications are typed once, at the infrastructure boundary.** The pool translates each SDK notification or listen
  event into one of three typed member notifications: a list change (which list), a resource update (the URI), or a
  log message (level, logger, data). Anything else is not passed on. The application's sink contract takes this typed
  union instead of a dict.
- **A registry, not a conditional, dispatches them.** The router keeps one handler per notification type, as the MCP
  edge's method registry does. Re-discovery, the cross-replica gate and stream delivery behave as today.
- **The gateway relays what the member said, not how it said it** (PROT-7, PROT-23, modified). The notification a
  client receives is built from the typed fields. A member's `_meta` is no longer forwarded.
- **The upstream mechanism for a resource subscription is stated per era** (PROT-23, modified). A handshake-era member
  is sent `resources/subscribe` and `resources/unsubscribe`; a modern member has the URI added to, or removed from,
  the gateway's standing listen filter. The handshake requests are sent as explicit protocol requests rather than
  through the deprecated SDK helpers, so no deprecation warning is raised and an SDK that drops the helpers does not
  break them.
- **A re-opened listen stream refetches** (PROT-30, added). When the gateway re-opens a lost listen stream to a modern
  member, it treats every list it listens for as changed and announces an update for every URI it watches, so changes
  made while the stream was down are not lost.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `protocol`: PROT-7 (relayed log messages carry the protocol fields, not the member's `_meta`), PROT-23 (the upstream
  mechanism per era, and the same rule for relayed resource updates), and PROT-30 (added: refetch after a modern
  member's listen stream is re-opened).

## Impact

- **Resolves:** audit findings S8 and S23 (2026-10-29). No GitHub issue.
- **Code:**
  - `application/contracts/upstream/`: the typed member notifications, and the sink contract taking them.
  - `application/serving/`: the router becomes a registry of three handlers.
  - `domain/sessions/log_levels.py`: a `LogLevel` type the log message carries.
  - `infrastructure/fastmcp/`: one translation from SDK notifications and listen events to the typed union; one
    resource-watch strategy per upstream era in the pooled sessions; refetch on a re-opened listen.
  - `main/composition_root.py`: wiring of the handlers.
- **API:** none. No DTO or route changes.
- **Behaviour:** clients stop seeing a member's `_meta` on relayed log messages and resource updates. After a modern
  member's listen stream is lost and re-opened, clients may see one list change and one resource update that carry no
  new content; MCP clients treat both as "fetch again".
- **Docs:**
  - A new ADR, ADR-0062 "Member notifications are typed at the pool boundary", which extends ADR-0027 and ADR-0054.
  - arc42 §6.5 (a member's notification between calls).
- **Overlaps:** change `model-session-pool-states` (audit S11) reshapes the same pool module, including
  `PooledLease`. Whichever lands second rebases onto the other; the resource-watch strategy here is chosen at connect
  and fits either lifecycle shape.
- **Not covered:**
  - `logging/setLevel` to handshake-era members still goes through the SDK helper the SDK marks deprecated in the same
    way. It is sent from the MCP edge, not the pool, and is a separate change.
  - Typing the capability dicts the listen filter reads (audit S9).
