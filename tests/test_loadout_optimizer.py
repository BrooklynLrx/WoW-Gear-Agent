from backend.loadout_optimizer import choose_auto_flask, crafted_budget_allows, optimize_loadout, preference_key, remainder_score, score_stats, supplement_stats
from backend.loadout_optimizer import expand_candidate


def test_acquisition_preference_order():
    ordinary = preference_key(4, 4, 0, 0, 0, embellished=2)
    late_effect = preference_key(4, 4, 1, 0, 999, embellished=2)
    boe = preference_key(4, 4, 0, 0, 0, embellished=2, boe=1)
    assert late_effect < ordinary < boe


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


def test_auto_flask_fills_the_final_gear_ratio_gap():
    objectives = [{
        "rule": "rating_ratio",
        "weights": {"critical_strike": 1, "haste": 1, "mastery": 1, "versatility": 1},
    }]
    ratings = {"critical_strike": 100, "haste": 100, "mastery": 0, "versatility": 100}
    assert choose_auto_flask(ratings, 1.0, objectives) == 241322


def test_remainder_only_breaks_equal_primary_objective_scores():
    objectives = [
        {"rule": "sheet_percent_range", "stat": "haste", "minimum": 19, "maximum": 21},
        {"rule": "remainder", "stat": "mastery"},
    ]
    lower = {"critical_strike": 0, "haste": 880, "mastery": 100, "versatility": 0}
    higher = {"critical_strike": 0, "haste": 880, "mastery": 200, "versatility": 0}

    assert score_stats(lower, 1.0, objectives) == score_stats(higher, 1.0, objectives) == 0
    assert remainder_score(higher, objectives) < remainder_score(lower, objectives)


def test_auto_flask_respects_remainder_tiebreaker():
    ratings = {"critical_strike": 100, "haste": 100, "mastery": 100, "versatility": 100}
    assert choose_auto_flask(ratings, 1.0, [{"rule": "remainder", "stat": "versatility"}]) == 241320


def test_auto_flask_uses_current_ratings_for_increase_objective():
    ratings = {"critical_strike": 100, "haste": 100, "mastery": 100, "versatility": 100}
    current = {**ratings, "haste": 200}
    assert choose_auto_flask(ratings, 1.0, [{"rule": "increase", "stat": "haste"}], current) == 241324


def test_crafted_weapon_uses_the_same_two_item_budget():
    assert crafted_budget_allows({"crafted": 1}, {"crafted": 1})
    assert not crafted_budget_allows({"crafted": 1}, {"crafted": 2})


def test_engineering_cogwheel_expands_one_selected_stat():
    item = {
        "item_id": 1, "item_level": 331, "stats": {}, "customizable_secondaries": True,
        "customizable_secondary_amounts": [198],
        "secondary_stat_choices": ["critical_strike", "haste", "mastery", "versatility"],
        "is_tier": False, "is_embellished": False, "is_crafted": True,
        "is_late_raid_special_effect": False, "is_raid_boe": False,
        "is_penultimate_boss_drop": False, "is_final_boss_drop": False,
        "is_unique_equipped": False,
        "slot_key": "head",
    }

    variants = expand_candidate(item)

    assert len(variants) == 4
    assert all(list(value["equipment"]["crafted_secondary_stats"].values()) == [198] for value in variants)
