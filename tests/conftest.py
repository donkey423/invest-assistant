import pytest


@pytest.fixture(autouse=True)
def _no_twse_network(monkeypatch):
    """測試不連證交所：預設一律失敗，需要的測試自己換成假資料。"""
    def offline(url):
        raise OSError("測試中不連網")
    monkeypatch.setattr("briefing.chips._get_json", offline)


@pytest.fixture(autouse=True)
def _no_yahoo_for_signals(monkeypatch):
    """產業鏈訊號的股價改用假資料，不連 Yahoo。"""
    from tests.fakes import fake_history
    monkeypatch.setattr("briefing.signals._history", fake_history)
    monkeypatch.setattr("briefing.signals._get_json", lambda url: (_ for _ in ()).throw(OSError("測試中不連網")))
