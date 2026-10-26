"""Capacity-aware session affinity routing on a single LiteLLM worker."""
from unittest.mock import AsyncMock, Mock
import pytest

from litellm.router_utils.client_initalization_utils import MaxParallelRequestsLimit
from litellm.router_utils.pre_call_checks.deployment_affinity_check import DeploymentAffinityCheck


def _deployment(model_id):
    return {
        "model_name": "test",
        "model_info": {"id": model_id},
        "litellm_params": {"model": "openai/test", "max_parallel_requests": 2},
    }


def _callback(counts, pinned="a", enabled=True):
    cache = Mock()
    cache.get_cache.side_effect = lambda key, local_only=False: counts.get(key.split("_max_parallel")[0])
    cache.async_get_cache = AsyncMock(return_value={"model_id": pinned})
    return DeploymentAffinityCheck(
        cache=cache,
        ttl_seconds=3600,
        enable_user_key_affinity=False,
        enable_responses_api_affinity=False,
        enable_session_id_affinity=True,
        capacity_aware=enabled,
    )


def _limit(model_id, in_flight=0):
    limit = MaxParallelRequestsLimit(2, model_id, "test")
    for _ in range(in_flight):
        limit.acquire()
    return limit


@pytest.mark.asyncio
async def test_pinned_deployment_keeps_affinity_while_capacity_remains():
    callback = _callback({"a": _limit("a", 1), "b": _limit("b", 0)})
    available = await callback.async_filter_deployments(
        model="test", healthy_deployments=[_deployment("a"), _deployment("b")],
        messages=None, request_kwargs={"metadata": {"session_id": "test"}},
    )
    assert [d["model_info"]["id"] for d in available] == ["a"]


@pytest.mark.asyncio
async def test_full_pinned_deployment_yields_to_router_candidate_selection():
    callback = _callback({"a": _limit("a", 2), "b": _limit("b", 0)})
    available = await callback.async_filter_deployments(
        model="test", healthy_deployments=[_deployment("a"), _deployment("b")],
        messages=None, request_kwargs={"metadata": {"session_id": "test"}},
    )
    assert [d["model_info"]["id"] for d in available] == ["b"]


@pytest.mark.asyncio
async def test_disabled_mode_preserves_strict_affinity_even_when_full():
    callback = _callback({"a": _limit("a", 2), "b": _limit("b", 0)}, enabled=False)
    available = await callback.async_filter_deployments(
        model="test", healthy_deployments=[_deployment("a"), _deployment("b")],
        messages=None, request_kwargs={"metadata": {"session_id": "test"}},
    )
    assert [d["model_info"]["id"] for d in available] == ["a"]
