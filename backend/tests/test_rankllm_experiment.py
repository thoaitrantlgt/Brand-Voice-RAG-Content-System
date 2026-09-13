import pytest

from scripts.run_rankllm_experiment import agreement, valid_permutation


@pytest.mark.parametrize("response,count,expected", [
    ("[2] > [1] > [3]", 3, True),
    (" [2]>[1]\n", 2, True),
    ("[1] > [1] > [3]", 3, False),
    ("[1] > [2]", 3, False),
    ("[0] > [1] > [2]", 3, False),
    ("[1] > [2] > [4]", 3, False),
    ("Explanation [1] > [2]", 2, False),
    ("", 2, False),
])
def test_rankllm_permutation_validation(response, count, expected):
    assert valid_permutation(response, count) is expected


def test_order_agreement_is_not_relevance_accuracy():
    assert agreement(["a", "b", "c"], ["a", "b", "c"]) == 1
    assert agreement(["a", "b", "c"], ["c", "b", "a"]) == 0
    assert agreement(["a", "b", "c"], ["a", "c", "b"]) == pytest.approx(2 / 3)
    with pytest.raises(ValueError):
        agreement(["a", "b"], ["a", "c"])
