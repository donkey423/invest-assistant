"""產生「今天的世界」用的世界地圖輪廓：site/worldmap.js

地圖資料：world-atlas 2.0.2 的 land-110m.json（Natural Earth，公有領域；world-atlas 為 ISC 授權）。
只需要在換地圖時跑一次：
    npm pack world-atlas@2.0.2 && tar xzf world-atlas-2.0.2.tgz
    python tools/make_world_map.py package/land-110m.json
投影：等距圓柱，經度 -180~180 → x 0~360，緯度 TOP~BOTTOM → y 0~(TOP-BOTTOM)。
"""
import json
import sys
from pathlib import Path

TOP, BOTTOM = 78, -56  # 去掉南極與北極海，手機上留更多高度給有人住的地方


def decode_arcs(topo):
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)
    return arcs


def ring_points(ring, arcs):
    pts = []
    for i in ring:
        a = arcs[i] if i >= 0 else arcs[~i][::-1]
        pts.extend(a if not pts else a[1:])
    return pts


def to_path(pts):
    # 跨過國際換日線（例如俄羅斯東端、斐濟）時從另一邊重新起筆，不然會畫出橫跨全圖的線
    segs, last = [[]], None
    for lon, lat in pts:
        lat = max(BOTTOM, min(TOP, lat))
        p = (round(lon + 180, 1), round(TOP - lat, 1))
        if p == last:
            continue
        if last and abs(p[0] - last[0]) > 180:
            segs.append([])
        segs[-1].append(f"{p[0]:g} {p[1]:g}")
        last = p
    return "".join("M" + "L".join(s) + "Z" for s in segs if len(s) >= 3)


def main(src):
    topo = json.loads(Path(src).read_text("utf-8"))
    arcs = decode_arcs(topo)
    parts = []
    for geom in topo["objects"]["land"]["geometries"]:
        polys = geom["arcs"] if geom["type"] == "MultiPolygon" else [geom["arcs"]]
        for poly in polys:
            for ring in poly:
                pts = ring_points(ring, arcs)
                if all(lat < BOTTOM for _, lat in pts):
                    continue  # 南極
                parts.append(to_path(pts))
    d = "".join(parts)
    js = ("// 自動產生：python tools/make_world_map.py（Natural Earth 110m 陸地，經 world-atlas）\n"
          f"window.WORLD_MAP = {{ width: 360, height: {TOP - BOTTOM}, top: {TOP}, land: \"{d}\" }};\n")
    out = Path(__file__).resolve().parent.parent / "site" / "worldmap.js"
    out.write_text(js, "utf-8")
    print(f"寫入 {out}（{len(js) // 1024} KB）")


if __name__ == "__main__":
    main(sys.argv[1])
