#!/usr/bin/env bash
# Patch official v1.106.4 image's STOPPED container; never rebuild the image.
set -Eeuo pipefail

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
trap 'printf "Patch application failed. Do not start the unpatched container.\n" >&2' ERR

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
compose_dir="$(cd -- "${COMPOSE_DIR:-$PWD}" && pwd -P)"
compose_file="${COMPOSE_FILE:-$compose_dir/compose.yaml}"
service="${LITELLM_SERVICE:-litellm}"
site_dir="/app/.venv/lib/python3.13/site-packages/litellm"
expected_image="ghcr.io/berriai/litellm:v1.106.4"

[[ -f "$compose_file" ]] || die "Compose file not found: $compose_file"
command -v docker >/dev/null || die "docker is not installed"
files=(
  router.py
  router_strategy/least_busy.py
  router_utils/pre_call_checks/deployment_affinity_check.py
  caching/affinity_cache.py
  types/router.py
  types/litellm_params.py
)
for rel in "${files[@]}"; do
  [[ -f "$repo_root/litellm/$rel" ]] || die "Missing patch: $repo_root/litellm/$rel"
done

compose=(docker compose --project-directory "$compose_dir" -f "$compose_file")

printf 'Starting dependency services ...\n'
"${compose[@]}" up -d --wait postgres redis

printf 'Creating stopped LiteLLM container ...\n'
"${compose[@]}" stop "$service"
"${compose[@]}" create --force-recreate --no-deps "$service"
cid="$("${compose[@]}" ps -a -q "$service")"
[[ -n "$cid" ]] || die "Unable to get container ID for $service"
image="$(docker container inspect --format '{{.Config.Image}}' "$cid")"
[[ "$image" == "$expected_image" ]] || die "Expected $expected_image but container uses $image"

# Check package layout before replacing any source files.
docker cp "$cid:$site_dir/router.py" - >/dev/null ||
  die "Python site-packages path not found: $site_dir"

for rel in "${files[@]}"; do
  printf 'Applying %s\n' "$rel"
  docker cp "$repo_root/litellm/$rel" "$cid:$site_dir/$rel"
done

"${compose[@]}" start "$service"
"${compose[@]}" exec -T "$service" /app/.venv/bin/python -c '
from litellm.types.router import RoutingStrategy
from litellm.router_utils.pre_call_checks.deployment_affinity_check import DeploymentAffinityCheck
assert RoutingStrategy.WEIGHTED_LEAST_BUSY.value == "weighted-least-busy"
assert hasattr(DeploymentAffinityCheck, "async_repin_after_success")
print("v1.106.4-patched: Python import OK")
'
printf 'Patched LiteLLM started. Re-run this script after any container recreation.\n'
