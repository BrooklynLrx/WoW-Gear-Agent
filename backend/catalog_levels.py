"""Graduation levels for the 12.1.5 catalog; explicit historical levels stay exact."""


def graduation_level(raw, *, is_crafted=False):
    return int(raw.get("default_optimizer_item_level", 331 if is_crafted else 334))
