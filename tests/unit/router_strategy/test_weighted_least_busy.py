"""Weighted least-busy regression tests."""
from unittest.mock import patch

from litellm.router_strategy.least_busy import _least_busy


def dep(name, weight):
    return {"model_info": {"id": name}, "litellm_params": {"weight": weight}}


def test_original_least_busy_tie_is_unchanged():
    a, b = dep("a", 1), dep("b", 3)
    assert _least_busy((a, b), (0, 0)) is a


def test_weighted_least_busy_draws_only_among_ties():
    a, b, c = dep("a", 1), dep("b", 3), dep("c", 100)
    with patch("litellm.router_strategy.simple_shuffle.random.choices", return_value=[b]) as choice:
        assert _least_busy((a, b, c), (0, 0, 1), weighted=True, model_group="test") is b
    assert list(choice.call_args.args[0]) == [a, b]


def test_weighted_least_busy_single_minimum():
    a, b = dep("a", 1), dep("b", 3)
    with patch("litellm.router_strategy.simple_shuffle.random.choices") as choice:
        assert _least_busy((a, b), (1, 0), weighted=True, model_group="test") is b
        choice.assert_not_called()
