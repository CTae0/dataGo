"""
안전·의료·환경 수집기  → raw.poi (병원·의원·약국·응급·소아과), raw.air_sigungu_hourly, raw.crime_region

사용법:
    python health_env.py hospital    # 국립중앙의료원 병·의원 FullData (병원·의원 + 이름으로 고른 소아과)
    python health_env.py pharmacy    # 국립중앙의료원 약국 FullData
    python health_env.py emergency   # 국립중앙의료원 응급의료기관 목록
    python health_env.py air         # 에어코리아 시군구별 1시간 값 (최근 24시간) → 쌓기 (매일 실행)
    python health_env.py crime       # 경찰청 범죄 발생 지역별 통계 CSV (data.go.kr 파일) → 그 연도를 갈아 끼움
    python health_env.py all         # 위 전부

- 시설은 poi.py와 같이 raw.poi의 source_id 행을 통째로 갈아 끼운다 (좌표 → 지역 배정은 sql/mart/85_amenities.sql).
- 하루 호출 수: 병·의원 80번, 약국 26번, 응급 1번, 미세먼지 17번 남짓 (pipeline/quota.py).
- [출처 표시] meta.data_source: nmc_hospital, nmc_pharmacy, nmc_emergency, airkorea_stats, police_crime
  (sql/init/13_health_env.sql)
"""
import argparse
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import psycopg2.extras

import datago_periodic
import molit_rent as common
from pipeline.quota import Quota
from poi import num, replace_source, session

NMC = "https://apis.data.go.kr/B552657/"
HOSP_FULL = NMC + "HsptlAsembySearchService/getHsptlMdcncFullDown"
PHARM_FULL = NMC + "ErmctInsttInfoInqireService/getParmacyFullDown"
EMERG_LIST = NMC + "ErmctInfoInqireService/getEgytListInfoInqire"
AIR_SIGUNGU = "https://apis.data.go.kr/B552584/ArpltnStatsSvc/getCtprvnMesureSidoLIst"
# 에어코리아 시도 이름 (2026 통합 뒤 이름이 바뀌었을 수 있어 둘 다 불러 본다)
AIR_SIDO = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남",
            "전북", "전남", "경북", "경남", "제주"]
CRIME_PK = "3074462"
CRIME_DIR = Path("data/crime")
ROWS = 1000

# 병·의원 종별 (dutyDiv): 병원급은 종합병원·병원·요양병원 등, 의원급은 의원. 치과·한방은 따로 둔다
HOSP_CAT = {"A": "hospital", "B": "hospital", "C": "clinic", "R": "hospital", "G": "oriental", "D": "hospital",
            "E": "hospital", "M": "dental", "N": "dental", "W": "other"}
PEDIATRIC = re.compile(r"소아|어린이병원|아동병원|아이들병원")


def xml_items(text):
    root = ET.fromstring(text)
    code = root.findtext(".//resultCode")
    if code not in (None, "00"):
        raise RuntimeError(f"API 오류 {code}: {root.findtext('.//resultMsg')}")
    if root.find(".//returnReasonCode") is not None:
        raise RuntimeError(f"API 오류 {root.findtext('.//returnReasonCode')}: {root.findtext('.//errMsg')}")
    total = int(root.findtext(".//totalCount") or 0)
    return [{c.tag: (c.text or "").strip() for c in it} for it in root.iter("item")], total


def nmc_all(s, key, url, quota, api, **params):
    """국립중앙의료원 목록을 끝까지 넘겨 받는다"""
    out, page = [], 1
    while True:
        quota.use(api)
        r = s.get(url, params={"serviceKey": key, "pageNo": page, "numOfRows": ROWS, **params}, timeout=120)
        r.raise_for_status()
        items, total = xml_items(r.content)
        out += items
        if page * ROWS >= total or not items:
            break
        page += 1
        time.sleep(0.3)
    print(f"  {url.rsplit('/', 1)[1]}: {len(out):,}곳 (전체 {total:,})")
    return out


def fetch_hospital(s, key, quota):
    rows = []
    for it in nmc_all(s, key, HOSP_FULL, quota, "nmc_hospital"):
        lon, lat = num(it.get("wgs84Lon")), num(it.get("wgs84Lat"))
        cat = HOSP_CAT.get(it.get("dutyDiv"), "other")
        keep = {k: it.get(k) for k in ("hpid", "dutyName", "dutyDiv", "dutyDivNam", "dutyEryn", "dutyAddr")}
        rows.append((it["hpid"], cat, it.get("dutyName"), it.get("dutyAddr"), None, lon, lat, None, keep))
        if PEDIATRIC.search(it.get("dutyName") or ""):   # 소아과는 따로 한 줄 더 (이름 기준)
            rows.append(("ped:" + it["hpid"], "pediatric", it.get("dutyName"), it.get("dutyAddr"), None, lon, lat,
                         None, keep))
    return rows


def fetch_pharmacy(s, key, quota):
    return [(it["hpid"], "pharmacy", it.get("dutyName"), it.get("dutyAddr"), None,
             num(it.get("wgs84Lon")), num(it.get("wgs84Lat")), None,
             {k: it.get(k) for k in ("hpid", "dutyName", "dutyAddr")})
            for it in nmc_all(s, key, PHARM_FULL, quota, "nmc_pharmacy")]


def fetch_emergency(s, key, quota):
    return [(it["hpid"], "emergency", it.get("dutyName"), it.get("dutyAddr"), None,
             num(it.get("wgs84Lon")), num(it.get("wgs84Lat")), None,
             {k: it.get(k) for k in ("hpid", "dutyName", "dutyEmcls", "dutyEmclsName", "dutyAddr")})
            for it in nmc_all(s, key, EMERG_LIST, quota, "nmc_emergency")]


def fetch_air(s, key, quota, conn):
    rows, empty = [], []
    for sido in AIR_SIDO:
        page = 1
        while True:
            quota.use("airkorea_stats")
            r = s.get(AIR_SIGUNGU, params={"serviceKey": key, "sidoName": sido, "searchCondition": "DAILY",
                                           "returnType": "json", "numOfRows": ROWS, "pageNo": page}, timeout=120)
            body = r.json()["response"]
            if body.get("header", {}).get("resultCode") != "00":
                raise RuntimeError(f"에어코리아 오류 {sido}: {body.get('header')}")
            items = body["body"].get("items") or []
            for it in items:
                day = (it.get("dataTime") or "").replace(" 24:00", " 23:59")   # '24:00' 표기
                if not day or not it.get("cityName"):
                    continue
                it = {k: v for k, v in it.items() if k != "serviceKey"}
                rows.append((sido, it["cityName"], day, num(it.get("pm25Value")), num(it.get("pm10Value")),
                             json.dumps(it, ensure_ascii=False)))
            if not items and page == 1:
                empty.append(sido)
            if page * ROWS >= int(body["body"].get("totalCount") or 0) or not items:
                break
            page += 1
        time.sleep(0.3)
    if not rows:
        raise RuntimeError("미세먼지 자료를 하나도 받지 못했습니다.")
    rows = list({(r[0], r[1], r[2]): r for r in rows}.values())
    with conn, conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, """
            INSERT INTO raw.air_sigungu_hourly (sido_nm, city_nm, msr_time, pm25, pm10, payload) VALUES %s
            ON CONFLICT (sido_nm, city_nm, msr_time) DO UPDATE SET pm25 = EXCLUDED.pm25, pm10 = EXCLUDED.pm10,
                payload = EXCLUDED.payload, fetched_at = now()""", rows, page_size=2000)
        cur.execute("""SELECT count(DISTINCT (sido_nm, city_nm)), count(DISTINCT msr_time), min(msr_time), max(msr_time)
                       FROM raw.air_sigungu_hourly""")
        n_city, n_hr, d0, d1 = cur.fetchone()
    print(f"[airkorea_stats] 이번에 {len(rows):,}행 · 쌓인 자료: 시군구 {n_city}곳, {n_hr}시간 ({d0} ~ {d1})"
          + (f" · 응답 없는 시도 {empty}" if empty else ""))


def fetch_crime(conn):
    """data.go.kr 파일(CP949 CSV): 행 = 범죄대분류·중분류, 열 = '서울 종로구' … '외국 …'"""
    s = datago_periodic.make_session()
    key, title = datago_periodic.get_current_key(s, CRIME_PK)
    (CRIME_DIR / "raw").mkdir(parents=True, exist_ok=True)
    path = datago_periodic.download(s, CRIME_PK, key, "1", CRIME_DIR / "raw" / key.replace(":", "_"))
    m = re.search(r"(20\d\d)\d{4}", title)
    year = int(m.group(1)) if m else None
    raw = path.read_bytes()
    text = next(raw.decode(e) for e in ("utf-8-sig", "cp949") if _decodes(raw, e))
    lines = [l.split(",") for l in text.splitlines() if l.strip()]
    head = lines[0]
    rows = []
    for c in lines[1:]:
        major, minor = c[0].strip(), c[1].strip()
        for label, v in zip(head[2:], c[2:]):
            label = label.strip()
            if label.startswith("외국") or not v.strip():
                continue
            sido, _, sg = label.partition(" ")
            rows.append((year, label, sido, sg, major, minor, int(float(v))))
    if not year:
        raise RuntimeError(f"파일 제목에서 연도를 찾지 못했습니다: {title}")
    with conn, conn.cursor() as cur:
        cur.execute("DELETE FROM raw.crime_region WHERE data_year = %s", (year,))
        psycopg2.extras.execute_values(cur, """
            INSERT INTO raw.crime_region (data_year, region_label, sido_nm, sigungu_nm, crime_major, crime_minor, cnt)
            VALUES %s ON CONFLICT DO NOTHING""", rows, page_size=5000)
    print(f"[police_crime] {year}년: 지역 {len({r[1] for r in rows})}곳 × 범죄 {len({(r[4], r[5]) for r in rows})}종")


def _decodes(b, enc):
    try:
        b.decode(enc)
        return True
    except UnicodeDecodeError:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["hospital", "pharmacy", "emergency", "air", "crime", "all"])
    a = ap.parse_args()
    common.load_env()
    key = common.service_key()
    conn = common.connect()
    quota = Quota(conn)
    s = session()
    jobs = ["hospital", "pharmacy", "emergency", "air", "crime"] if a.what == "all" else [a.what]
    failed = []
    for job in jobs:
        try:
            if job == "hospital":
                replace_source(conn, "nmc_hospital", fetch_hospital(s, key, quota))
            elif job == "pharmacy":
                replace_source(conn, "nmc_pharmacy", fetch_pharmacy(s, key, quota))
            elif job == "emergency":
                replace_source(conn, "nmc_emergency", fetch_emergency(s, key, quota))
            elif job == "air":
                fetch_air(s, key, quota, conn)
            elif job == "crime":
                fetch_crime(conn)
        except Exception as e:   # 한 원천이 실패해도 나머지는 받는다
            failed.append(job)
            print(f"[{job}] 실패: {e}")
    conn.close()
    if failed:
        sys.exit(f"실패한 원천: {', '.join(failed)}")


if __name__ == "__main__":
    main()
