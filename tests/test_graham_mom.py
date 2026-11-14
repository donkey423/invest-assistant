"""並行帳戶「葛拉漢＋動能」：等同研究假設 G2 的排名，不參加 Claude 判斷的投票。"""
from papertrade import config as C
from papertrade import methods


def _ctx(n=300):
    codes = ["1101", "2002", "2882", "1605", "2603", "9904"]
    px, value = {}, {}
    for i, code in enumerate(codes):
        closes = [100 * (1 + 0.0005 * (i + 1) * (-1) ** i) ** k for k in range(n)]
        px[f"{code}.TW"] = {"dates": [f"d{k:04d}" for k in range(n)], "close": closes, "open": closes, "volume": [1000] * n}
        value[code] = {"pe": 6 + i, "pb": 0.6 + 0.1 * i}
    return {"codes": codes, "sym": {c: f"{c}.TW" for c in codes}, "px": px, "value": value}


def test_graham_mom_equals_graham_with_g2_flag():
    ctx = _ctx()
    got = methods.graham_mom(ctx)
    want = methods.graham({**ctx, "variant": {"graham_value_momentum": True}})
    assert [r["code"] for r in got] == [r["code"] for r in want] and got
    assert "variant" not in ctx                      # 不改動共用的 ctx
    assert "動能百分位" in got[0]["reason"]


def test_graham_mom_is_registered_but_does_not_vote():
    ids = [m["id"] for m in C.METHODS]
    assert "graham_mom" in ids and ids.index("graham_mom") == ids.index("graham") + 1
    assert methods.METHOD_FNS["graham_mom"] is methods.graham_mom
    assert "graham_mom" not in methods.method_weights({}) and "graham_mom" not in methods.method_weights_long({})
    assert "graham" in methods.method_weights({})
