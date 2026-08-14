from backend.stat_calculator import (
    apply_diminishing_returns,
    calculate_percentages,
    rating_for_percentage,
)


def test_arcane_mastery_uses_base_before_coefficient():
    result = calculate_percentages({}, 1.32)
    assert result["percentages"] == {
        "critical_strike": 5.0,
        "haste": 0.0,
        "mastery": 10.56,
        "versatility": 0.0,
    }


def test_destruction_example_from_reference():
    result = calculate_percentages({"mastery": 552}, 2)
    assert result["percentages"]["mastery"] == 40.0
    assert rating_for_percentage("mastery", 40, 2) == 552


def test_diminishing_returns_after_thirty_percent():
    assert float(apply_diminishing_returns(40)) == 38.9
    assert rating_for_percentage("haste", 38.9) == 1760


def test_arcane_mastery_rating_is_added_before_coefficient():
    result = calculate_percentages({"mastery": 46}, 1.32)
    assert result["percentages"]["mastery"] == 11.88
