from backend.loadout_optimizer import optimize_loadout, preference_key, score_stats, supplement_stats


def test_ratio_score_prefers_matching_distribution():
    objective = [{
        "rule": "rating_ratio",
        "weights": {"critical_strike": 3, "haste": 3, "mastery": 1, "versatility": 3},
    }]
    matching = {"critical_strike": 300, "haste": 300, "mastery": 100, "versatility": 300}
    wrong = {"critical_strike": 100, "haste": 100, "mastery": 700, "versatility": 100}
    assert score_stats(matching, 1.32, objective) < score_stats(wrong, 1.32, objective)


def test_sheet_range_has_no_penalty_inside_range():
    objective = [{"rule": "sheet_percent_range", "stat": "haste", "minimum": 19, "maximum": 21}]
    assert score_stats({"critical_strike": 0, "haste": 880, "mastery": 0, "versatility": 0}, 1.32, objective) == 0


def test_optimizer_rejects_non_graduation_target_before_database():
    result = optimize_loadout(
        "mage", "arcane",
        [{"rule": "rating_ratio", "weights": {"haste": 1, "mastery": 1}}],
        {}, default_item_level=321,
    )
    assert result["error"] == "optimizer_only_supports_graduation_levels"


def test_optimizer_uses_hard_acquisition_priorities_before_stats():
    assert preference_key(4, 4, 1, 0, 10) < preference_key(4, 4, 0, 0, 0)
    assert preference_key(4, 4, 0, 0, 5) < preference_key(4, 4, 0, 1, 0)
    assert preference_key(4, 4, 0, 1, 0) < preference_key(4, 4, 0, 2, 0)


def test_highest_quality_flask_rating_is_counted():
    assert supplement_stats([241326])["critical_strike"] == 165
