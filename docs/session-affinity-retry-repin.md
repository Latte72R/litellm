# Retry-aware session affinity repinning

This stacked PR builds on the capacity-aware affinity filter from PR #2.

- Failed deployments are excluded for an individual retry when
  `session_affinity_capacity_aware: true` **and** a session id is present.
- Existing non-session retry semantics are unchanged.
- When routing switches away from a pinned deployment because it is
  full, in cooldown, or has already failed this request, the prior pin
  id is placed in per-request metadata.
- On successful completion, a Redis Lua compare-and-swap updates
  the pin only if that original id is still current. An unsuccessful
  attempt does not move the pin.
- `previous_response_id` continuity remains a strict routing path.
- Single LiteLLM worker assumed; Redis failures do not fail the
  successful LLM call.
- Integration tests are still needed for acquire-time slot contention
  and streaming completion.
