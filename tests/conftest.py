import pytest


@pytest.fixture(autouse=True)
def _no_twse_network(monkeypatch):
    """測試不連證交所：預設一律失敗，需要的測試自己換成假資料。"""
    def offline(url):
        raise OSError("測試中不連網")
    monkeypatch.setattr("briefing.chips._get_json", offline)
