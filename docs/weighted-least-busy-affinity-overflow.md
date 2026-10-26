# Capacity-aware session affinity and weighted least-busy (v1.106.4)

Experimental implementation on top of upstream tag `v1.106.4`.
This branch does **not** change the fork's `main` branch.

## Configuration

```yaml
router_settings:
  routing_strategy: weighted-least-busy
  redis_url: redis://redis:6379
  optional_pre_call_checks:
    - session_affinity
  session_affinity_capacity_aware: true
  deployment_affinity_ttl_seconds: 14400
  num_retries: 2
```

- `weighted-least-busy` is independent of `least-busy` and `simple-shuffle`.
  It selects among deployments tied for the lowest current in-flight request
  count using the existing `simple_shuffle` weight/RPM/TPM selection.
- `session_affinity_capacity_aware` is disabled by default.
  With it enabled, a pinned deployment is preferred only when it has
  worker-local `max_parallel_requests` capacity. Otherwise the remaining
  candidates are passed to the configured strategy.
- Retryable failures are tracked by deployment ID; a failed session pin
  yields to another eligible deployment within the same retry request.
- Successful replacement requests conditionally replace the Redis session
  pin (compare-and-swap) so that two concurrent replacement requests cannot
  blindly overwrite each other. A failed response does not repin.

## Reusing the existing Docker image without rebuilding

The Python files in this branch are written for the *same pinned version*
as your Docker image: `ghcr.io/berriai/litellm:v1.106.4`.
Clone this branch to the host and update your Compose service to keep the
original image. After editing Compose config, run:

```sh
# Stop and recreate, but do NOT start before copying the files.
sudo docker compose stop litellm
sudo docker compose rm -f litellm
sudo docker compose create litellm
CID=$(sudo docker compose ps -a -q litellm)
SITE=/app/.venv/lib/python3.13/site-packages/litellm
for file in \
  router.py \
  router_strategy/least_busy.py \
  router_utils/pre_call_checks/deployment_affinity_check.py \
  caching/affinity_cache.py \
  types/router.py \
  types/litellm_params.py; do
    sudo docker cp "litellm/$file" "$CID:$SITE/$file"
done
sudo docker compose start litellm
```

`docker cp` is preferable to an unguarded blind `sed` because the source
files on this branch are complete, version-pinned, and reviewable.
This is a **container-local** modification; recreating the container loses
the copied files. Do not run `docker compose up --force-recreate` without
applying the copies again. Confirm the image's actual `site-packages` path
if its Python version differs.

For an upstream PR, commit the Python source changes and tests normally,
not the `docker cp` or `sed` deployment procedure.

## Current limitations and review checklist

This is an experimental branch, not a production-verified release.

- `MaxParallelRequestsLimit.in_flight` is per Python process. **Do not set
  `NUM_WORKERS > 1`** without adding shared atomic slot reservations.
- Pre-filtering capacity and acquiring the real slot are separate operations.
  A racing request can consume the last slot. Retry may recover, but a
  concurrency-specific pre-send reroute needs an integration test.
- Repinning uses Redis compare-and-swap where Redis is available; under Redis
  failure it leaves the shared pin unchanged. Without Redis, updates are
  process-local.
- The implementation reuses existing asynchronous completion/failure
  callbacks; streaming and Responses API need end-to-end validation before
  production deployment.
- The existing `previous_response_id` continuity path retains priority.
- Do not count a provider's upstream HTTP 429 as a worker-local slot error
  when evaluating metrics.
- Validation targets: pinned healthy, pinned full, pinned 500, all full,
  concurrent overflow, Redis unavailable, stream cancellation, and
  `/v1/chat/completions`, `/v1/messages`, `/v1/responses`.

Related upstream work: #32309, #47514, #48134, #48206.
