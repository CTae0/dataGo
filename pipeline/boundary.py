"""
시군구 경계를 V-World에서 받아 dim.region_geom(PostGIS)에 넣는다.

[출처표시] 국토교통부 공간정보 오픈플랫폼(V-World) — meta.data_source 'vworld_sigungu'

사용법 (프로젝트 루트):
    python -m pipeline.boundary                 # 받아서 적재 (data/boundary/vworld_sigungu_YYYYMMDD.geojson 스냅샷)
    python -m pipeline.boundary --file data/boundary/vworld_sigungu_20261021.geojson   # 파일로 적재만

설정: .env 의 VWORLD_API_KEY, VWORLD_DOMAIN (키를 발급할 때 등록한 서비스 URL. 지금은 localhost)
웹 지도용으로 줄인 파일은 web/에서 `npm run boundaries` (mapshaper, 이웃 경계를 공유하며 단순화)
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg2.extras
import requests

import molit_rent as common
from pipeline.quota import KST

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "boundary"
URL = "https://api.vworld.kr/req/data"


def fetch():
    key = os.environ.get("VWORLD_API_KEY", "").strip()
    if not key:
        sys.exit("VWORLD_API_KEY가 비어 있습니다 (.env).")
    feats, page = [], 1
    while True:
        r = requests.get(URL, timeout=300, params={
            "service": "data", "request": "GetFeature", "data": "LT_C_ADSIGG_INFO", "key": key,
            "domain": os.environ.get("VWORLD_DOMAIN", "localhost"), "format": "json", "geometry": "true",
            "attribute": "true", "crs": "EPSG:4326", "size": "1000", "page": str(page),
            "geomFilter": "BOX(124,32,132,39.5)"})
        resp = r.json()["response"]
        if resp["status"] != "OK":
            sys.exit(f"V-World 오류: {resp.get('error')} — 키와 VWORLD_DOMAIN(등록한 서비스 URL)을 확인하세요.")
        feats += resp["result"]["featureCollection"]["features"]
        if int(resp["page"]["current"]) >= int(resp["page"]["total"]):
            break
        page += 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"vworld_sigungu_{datetime.now(KST):%Y%m%d}.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False), encoding="utf-8")
    print(f"받음: 시군구 {len(feats)}개 → {path}")
    return path


def load(path, conn):
    fs = json.loads(Path(path).read_text(encoding="utf-8"))["features"]
    fetched_on = datetime.strptime(Path(path).stem.split("_")[-1], "%Y%m%d").date()
    rows = [(f["properties"]["sig_cd"], f["properties"].get("full_nm"), json.dumps(f["geometry"]), fetched_on) for f in fs]
    with conn, conn.cursor() as cur:
        cur.execute("TRUNCATE dim.region_geom")
        psycopg2.extras.execute_values(cur, """
            INSERT INTO dim.region_geom (region_code, name, geom, fetched_on)
            -- ST_MakeValid가 선 조각이 섞인 GeometryCollection을 줄 때가 있어 면(3)만 남긴다
            SELECT v.code, v.name,
                   ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_GeomFromGeoJSON(v.gj)), 3))::geometry(MultiPolygon, 4326), v.d
            FROM (VALUES %s) AS v(code, name, gj, d)""", rows, template="(%s, %s, %s, %s::date)")
        cur.execute("""UPDATE dim.region_geom
                       SET label_point = ST_PointOnSurface(geom), area_km2 = round((ST_Area(geom::geography) / 1e6)::numeric, 2)""")
        cur.execute("""SELECT
              (SELECT count(*) FROM dim.region_geom),
              (SELECT count(*) FROM dim.region r WHERE r.is_leaf AND NOT EXISTS (SELECT 1 FROM dim.region_geom g WHERE g.region_code = r.region_code)),
              (SELECT count(*) FROM dim.region_geom g WHERE NOT EXISTS (SELECT 1 FROM dim.region r WHERE r.region_code = g.region_code AND r.is_leaf)),
              (SELECT count(*) FROM dim.region_geom WHERE NOT ST_IsValid(geom)),
              (SELECT round(sum(area_km2)) FROM dim.region_geom)""")
        n, leaf_missing, extra, invalid, area = cur.fetchone()
    print(f"dim.region_geom {n}곳 · 경계 없는 leaf {leaf_missing} · leaf 아닌 경계 {extra} · 잘못된 도형 {invalid} · 총면적 {area:,}㎢")
    return leaf_missing == 0 and extra == 0 and invalid == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    a = ap.parse_args()
    common.load_env()
    path = Path(a.file) if a.file else fetch()
    conn = common.connect()
    try:
        ok = load(path, conn)
    finally:
        conn.close()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
