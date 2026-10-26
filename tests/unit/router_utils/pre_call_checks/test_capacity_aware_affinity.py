"""Targeted regressions for the capacity-aware affinity experiment.

Higher-level Router integration tests are required before production usage.
"""
from unittest.mock import Mock

from litellm.router_utils.client_initalization_utils import MaxParallelRequestsLimit
from litellm.router_utils.pre_call_checks.deployment_affinity_check import DeploymentAffinityCheck


def _row(model_id):
    return {"model_name": "test", "model_info": {"id": model_id},
            "litellm_params": {"model": "openai/test"}}


def test_capacity_aware_filter_detects_busy_and_free_workers():
    cache = Mock()
    limit = MaxParallelRequestsLimit(max_parallel_requests=2, model_id="a", model_group="test")
    cache.get_cache.return_value = limit
    check = DeploymentAffinityCheck(
        cache=cache, ttl_seconds=3600, enable_user_key_affinity=False,
        enable_responses_api_affinity=False, enable_session_id_affinity=True,
        capacity_aware=True,
    )
    assert check._has_capacity(_row("a"))
    limit.acquire()
    assert check._has_capacity(_row("a"))
    limit.acquire()
    assert not check._has_capacity(_row("a"))
    limit.release()
    assert check._has_capacity(_row("a"))


def test_capacity_check_treats_missing_limit_as_unlimited():
    cache = Mock()
    cache.get_cache.return_value = None
    check = DeploymentAffinityCheck(
        cache=cache, ttl_seconds=3600, enable_user_key_affinity=False,
        enable_responses_api_affinity=False, capacity_aware=True,
    )
    assert check._has_capacity(_row("a"))
