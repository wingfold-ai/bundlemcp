## MODIFIED Requirements

### Requirement: PROT-25 Built-in pipeline order
The gateway SHALL apply these steps in this order (list and call variants):

1. tool filter — drops stale tools ([UPS-19](../upstreams/spec.md)) and disabled tools / rejects calls to
   either ([BND-13](../bundles/spec.md))
2. profile transform ([EP-13](../endpoints/spec.md))
3. overrides — apply/reverse per-bundle overrides ([BND-14](../bundles/spec.md)), after the profile, so an
   explicit annotation override wins over the profile's rewrite ([BND-15](../bundles/spec.md))
4. **metering hook** (calls only; no-op unless configured)
5. audit ([operations](../operations/spec.md))

Steps 1–3 are applied when the endpoint's bundle view is composed; steps 4–5 are the `tools/call` pipeline. The order
is bundlemcp's contract regardless of the underlying library.

#### Scenario: Disabled tool never reaches metering
- **WHEN** a client calls a tool that is disabled in the bundle
- **THEN** the call is rejected without a `pre_call` to the metering hook and an audit record with status `denied` is
  written

#### Scenario: Stale tool never reaches metering
- **WHEN** a client calls a tool that the latest successful discovery of its upstream no longer listed
- **THEN** the call is rejected as an unknown tool without a `pre_call` to the metering hook or a request to the
  upstream, and an audit record with status `denied` is written

#### Scenario: Allowed call is metered then audited
- **WHEN** a client calls an enabled tool and the hook allows it
- **THEN** `pre_call` fires before the upstream call, `post_call` after it, and one audit record with status `success`
  is written
