from briefing.inputs_file import validate


def test_pending_items_are_fine_and_filled_items_need_date_and_source():
    ok = {"_說明": "x", "memory": [
        {"name": "DRAM 合約價", "trend": None, "value": "待更新", "as_of": "", "url": "https://a"},
        {"name": "韓國出口", "trend": "up", "value": "10 月年增 20%", "as_of": "2026-10-21", "url": "https://b"}]}
    assert validate(ok, {"memory"}) == []
    bad = {"memory": [{"name": "DRAM 合約價", "trend": "up", "value": "待更新", "as_of": "上個月", "url": "x"}],
           "nope": []}
    problems = validate(bad, {"memory"})
    assert len(problems) == 4


def test_repo_inputs_file_is_valid():
    import json
    from pathlib import Path
    from briefing import config
    data = json.loads(Path("site/data/chain_inputs.json").read_text("utf-8"))
    assert validate(data, {c["id"] for c in config.CHAINS}) == []
