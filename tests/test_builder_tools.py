import backend.builder_tools as tools


class Session:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


def test_invalid_loadout_stops_before_calculation(monkeypatch):
    monkeypatch.setattr(tools, "SessionLocal", Session)
    monkeypatch.setattr(tools, "validate_loadout", lambda *args: {"valid": False, "errors": ["bad"]})
    monkeypatch.setattr(tools, "calculate_equipment", lambda *args: (_ for _ in ()).throw(AssertionError()))
    result = tools.calculate_stats("mage", "arcane", [])
    assert result["success"] is False
    assert result["error"] == "invalid_loadout"
