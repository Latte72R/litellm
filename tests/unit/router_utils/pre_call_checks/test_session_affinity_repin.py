"""Session-affinity retry exclusions and successful Redis pin migration."""
from unittest.mock import AsyncMock, Mock, patch

import pytest

from litellm.router import Router
from litellm.router_utils.pre_call_checks.deployment_affinity_check import DeploymentAffinityCheck
from litellm.caching.affinity_cache import compare_and_swap_affinity_pin


def _callback():
    return DeploymentAffinityCheck(
        cache=Mock(), ttl_seconds=3600, enable_user_key_affinity=False,
        enable_responses_api_affinity=False, enable_session_id_affinity=True,
        capacity_aware=True,
    )


def test_retryable_deployment_error_can_be_skipped_when_enabled():
    error = Exception("backend unavailable")
    error.status_code = 500
    error.failed_deployment_id = "backend-a"
    assert Router._deployment_ids_to_skip_on_retry(error, (), include_retryable=False) == ()
    assert Router._deployment_ids_to_skip_on_retry(error, (), include_retryable=True) == ("backend-a",)


@pytest.mark.asyncio
async def test_repin_after_success_carries_original_and_replacement_model_ids():
    callback = _callback()
    kwargs = {
        "metadata": {
            "session_id": "session-1",
            "deployment_model_name": "group",
            "_session_affinity_repin_expected": "backend-a",
        },
        "model_info": {"id": "backend-b"},
    }
    with patch("litellm.caching.affinity_cache.compare_and_swap_affinity_pin", new_callable=AsyncMock) as cas:
        await callback.async_repin_after_success(kwargs)
    cas.assert_awaited_once()
    assert cas.await_args.kwargs["expected_model_id"] == "backend-a"
    assert cas.await_args.kwargs["new_model_id"] == "backend-b"


@pytest.mark.asyncio
async def test_unsuccessful_or_unmarked_request_does_not_repin():
    callback = _callback()
    with patch("litellm.caching.affinity_cache.compare_and_swap_affinity_pin", new_callable=AsyncMock) as cas:
        await callback.async_repin_after_success({"metadata": {"session_id": "session-1"}})
    cas.assert_not_called()


@pytest.mark.asyncio
async def test_in_memory_cas_never_overwrites_a_concurrent_pin():
    cache = Mock()
    cache.redis_cache = None
    cache.in_memory_cache.get_cache.return_value = {"model_id": "newer-backend"}
    moved = await compare_and_swap_affinity_pin(
        cache, "session:key", "old-backend", "candidate-backend", 3600
    )
    assert not moved
    cache.in_memory_cache.set_cache.assert_not_called()
