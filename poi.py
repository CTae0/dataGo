"""
생활편의 시설(교육·문화)과 연령별 인구 수집기  → raw.poi, raw.population_age

사용법:
    python poi.py culture        # 한국문화정보원 전국문화기반시설총람 (도서관·박물관·미술관·문예회관·생활문화센터·문학관)
    python poi.py park           # 전국도시공원정보표준데이터 (위경도·면적)
    python poi.py cinema         # 행정안전부 영화상영관 (영업 중만)
    python poi.py school         # 나이스 학교기본정보 (EDU_API_KEY)
    python poi.py academy        # 나이스 학원교습소정보 (EDU_API_KEY)
    python poi.py kinder         # 유치원알리미 일반현황 (EDUCHILD_API_KEY)
    python poi.py population     # 행정안전부 법정동별 성·연령별 주민등록 인구 (시군구, 최근 달)
    python poi.py all            # 위 전부 (키가 없는 원천은 건너뜀)

- 원천 하나를 받으면 raw.poi의 그 source_id 행을 통째로 갈아 끼운다 (snapshot = 받은 날, KST).
- 좌표가 없는 원천은 주소 앞부분에서 시도·시군구를 뽑아 sido_nm·sigungu_nm에 둔다
  (예: '경기도 용인시 수지구 …' → '경기도', '용인시 수지구'). 지역 배정은 sql/mart/85_amenities.sql.
- [출처 표시] meta.data_source: culture_facility, city_park, mois_cinema, neis_school, neis_academy,
  kinder_info, mois_population (sql/init/12_poi.sql)
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime

import psycopg2.extras
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import molit_rent as common
from pipeline.quota import KST

CULTURE = "https://apis.data.go.kr/B553457/rgnCltrFcltExmnv1/"
# 엔드포인트 → (분류, 이름 칸, 주소 칸)
CULTURE_EPS = {
    "clifLbrryv1": ("library", "lbrryNm", "instAddr"),
    "clifNtnLbrryv1": ("library", "lbrryNm", "instAddr"),
    "clifMsmv1": ("museum", "msmNm", "instAddr"),
    "clifArglv1": ("gallery", "arglNm", "instAddr"),
    "clifClcnv1": ("arts_center", "clcnNm", "instAddr"),
    "clifLvclCntrv1": ("culture_center", "lvclCntrNm", "instAddr"),
    "clifLtrm1": ("literature", "ltrmNm", "addr"),
}
PARK = "https://api.data.go.kr/openapi/tn_pubr_public_cty_park_info_api"
CINEMA = "https://apis.data.go.kr/1741000/movie_theaters/info"
POP = "https://apis.data.go.kr/1741000/stdgSexdAgePpltn/selectStdgSexdAgePpltn"
NEIS = "https://open.neis.go.kr/hub/"
KINDER = "https://e-childschoolinfo.moe.go.kr/api/notice/basicInfo2.do"
# 나이스 시도교육청 코드 (학원교습소정보는 교육청마다 불러야 한다)
NEIS_OFFICES = ["B10", "C10", "D10", "E10", "F10", "G10", "H10", "I10", "J10", "K10", "M10", "N10", "P10", "Q10",
                "R10", "S10", "T10"]
# 인구 API 시도 코드(법정동 10자리). 2026 통합 뒤 전남광주는 12
POP_SIDO = ["11", "26", "27", "28", "30", "31", "36", "41", "43", "44", "47", "48", "50", "51", "52", "12"]
SIDO_WORDS = ("특별시", "광역시", "특별자치시", "특별자치도", "도", "통합특별시")


def session():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (eodi-salkka data pipeline)"
    s.mount("https://", HTTPAdapter(max_retries=Retry(total=5, backoff_factor=2,
                                                      status_forcelist=[429, 500, 502, 503, 504])))
    return s


def parse_addr(addr):
    """주소 → (시도, 시군구). '경기도 용인시 수지구 …' → ('경기도', '용인시 수지구'), '세종특별자치시 …' → ('세종특별자치시', '')"""
    if not addr:
        return None, None
    t = re.sub(r"[()]", " ", addr).split()
    if not t:
        return None, None
    sido = t[0]
    if len(t) < 2 or not re.search(r"(시|군|구)$", t[1]) or sido.startswith("세종"):
        return sido, ""
    sg = t[1]
    if sg.endswith("시") and len(t) > 2 and t[2].endswith("구") and not t[2].endswith("지구"):
        sg = f"{sg} {t[2]}"
    return sido, sg


def num(v):
    try:
        return float(v) if v not in (None, "", "None") else None
    except (TypeError, ValueError):
        return None


def replace_source(conn, source_id, rows):
    """rows: (poi_id, category, name, addr, sgg_cd, lon, lat, size_value, payload)"""
    snapshot = datetime.now(KST).date()
    out = []
    for poi_id, cat, name, addr, sgg, lon, lat, size, payload in rows:
        sido, sg = parse_addr(addr)
        out.append((source_id, str(poi_id), cat, name, addr, sido, sg, sgg, lon, lat, size,
                    json.dumps(payload, ensure_ascii=False), snapshot))
    with conn, conn.cursor() as cur:
        cur.execute("DELETE FROM raw.poi WHERE source_id = %s", (source_id,))
        psycopg2.extras.execute_values(cur, """
            INSERT INTO raw.poi (source_id, poi_id, category, name, addr, sido_nm, sigungu_nm, sgg_cd, lon, lat,
                                 size_value, payload, snapshot)
            VALUES %s ON CONFLICT (source_id, poi_id) DO NOTHING""", out, page_size=2000)
        # 한국 범위 안의 좌표만 점으로 만든다
        cur.execute("""UPDATE raw.poi SET geom = ST_SetSRID(ST_MakePoint(lon, lat), 4326)
                       WHERE source_id = %s AND lon BETWEEN 124 AND 132 AND lat BETWEEN 33 AND 39""", (source_id,))
        cur.execute("SELECT category, count(*), count(geom) FROM raw.poi WHERE source_id = %s GROUP BY 1 ORDER BY 1",
                    (source_id,))
        summary = cur.fetchall()
    print(f"[{source_id}] " + ", ".join(f"{c} {n}곳(좌표 {g})" for c, n, g in summary))


# ── 원천별 ─────────────────────────────────────────────
def fetch_culture(s, key):
    rows = []
    for ep, (cat, name_f, addr_f) in CULTURE_EPS.items():
        year = None
        for y in range(datetime.now(KST).year, datetime.now(KST).year - 4, -1):   # 가장 최근 발간 연도
            b = s.get(CULTURE + ep, params={"serviceKey": key, "pageNo": 1, "numOfRows": 1, "pblshYr": y},
                      timeout=60).json()["response"].get("body", {})
            if int(b.get("totalCount") or 0) > 0:
                year = y
                break
        if not year:
            print(f"  {ep}: 최근 4년 자료 없음")
            continue
        page = 1
        while True:
            b = s.get(CULTURE + ep, params={"serviceKey": key, "pageNo": page, "numOfRows": 500, "pblshYr": year},
                      timeout=60).json()["response"]["body"]
            data = b.get("data") or []
            for d in data:
                rows.append((f"{ep}:{d.get('instId')}", cat, d.get(name_f), d.get(addr_f), d.get("sggCd"),
                             None, None, None, {**d, "_endpoint": ep}))
            if page * 500 >= int(b.get("totalCount") or 0) or not data:
                break
            page += 1
        print(f"  {ep} ({cat}) {year}년판")
    return rows


def fetch_park(s, key):
    rows, page = [], 1
    while True:
        r = s.get(PARK, params={"serviceKey": key, "pageNo": page, "numOfRows": 1000, "type": "json"}, timeout=120)
        d = r.json()
        body = d.get("response", d).get("body", {})
        items = body.get("items") or []
        items = items.get("item", []) if isinstance(items, dict) else items
        for it in items:
            rows.append((it.get("manageNo") or f"{it.get('insttCode')}-{it.get('parkNm')}", "park", it.get("parkNm"),
                         it.get("rdnmadr") or it.get("lnmadr"), None, num(it.get("longitude")), num(it.get("latitude")),
                         num(it.get("parkAr")), it))
        total = int(body.get("totalCount") or 0)
        if page * 1000 >= total or not items:
            break
        page += 1
        time.sleep(0.3)
    return rows


def fetch_cinema(s, key):
    rows, page = [], 1
    while True:
        r = s.get(CINEMA, params={"serviceKey": key, "pageNo": page, "numOfRows": 100, "returnType": "json",
                                  "cond[SALS_STTS_CD::EQ]": "01"},   # 영업상태 01 = 영업/정상
                  timeout=60)
        d = r.json()
        if "OpenAPI_ServiceResponse" in d:
            raise RuntimeError(f"영화상영관 API 오류: {d['OpenAPI_ServiceResponse']['cmmMsgHeader']}")
        body = d["response"]["body"]
        items = (body.get("items") or {}).get("item") or []
        for it in items:
            if "영업" not in (it.get("SALS_STTS_NM") or it.get("DTL_SALS_STTS_NM") or ""):
                continue
            rows.append((it.get("MNG_NO"), "cinema", it.get("BPLC_NM"), it.get("ROAD_NM_ADDR") or it.get("LOTNO_ADDR"),
                         None, None, None, None, it))
        if page * 100 >= int(body.get("totalCount") or 0) or not items:
            break
        page += 1
    return rows


def neis(s, key, svc, **params):
    rows, page = [], 1
    while True:
        d = s.get(NEIS + svc, params={"KEY": key, "Type": "json", "pIndex": page, "pSize": 1000, **params},
                  timeout=60).json()
        if svc not in d:
            code = d.get("RESULT", {}).get("CODE")
            if code == "INFO-200":   # 자료 없음
                break
            raise RuntimeError(f"나이스 {svc} 오류: {d.get('RESULT')}")
        part = d[svc][1]["row"]
        rows += part
        if len(part) < 1000:
            break
        page += 1
    return rows


SCHOOL_CAT = {"초등학교": "school_elem", "중학교": "school_mid", "고등학교": "school_high"}


def fetch_school(s, key):
    out = []
    for r in neis(s, key, "schoolInfo"):
        cat = SCHOOL_CAT.get(r.get("SCHUL_KND_SC_NM"))
        if cat:
            out.append((f"{r['ATPT_OFCDC_SC_CODE']}:{r['SD_SCHUL_CODE'].strip() or r['SCHUL_NM']}", cat, r["SCHUL_NM"],
                        r.get("ORG_RDNMA"), None, None, None, None, r))
    return out


def fetch_academy(s, key):
    out = []
    for office in NEIS_OFFICES:
        for r in neis(s, key, "acaInsTiInfo", ATPT_OFCDC_SC_CODE=office):
            out.append((f"{office}:{r.get('ACA_ASNUM')}", "academy", r.get("ACA_NM"), r.get("FA_RDNMA"),
                        None, None, None, None, r))
        time.sleep(0.3)
    return out


def fetch_kinder(s, key, conn):
    """유치원알리미는 시도·시군구 코드로 부른다 → 우리 leaf 코드(법정동 5자리)를 그대로 넣어 본다"""
    with conn.cursor() as cur:
        # 일반구가 있는 시(고양·용인·청주…)는 시 코드로 부르면 0곳 → 구 코드(leaf)로 부른다
        cur.execute("SELECT region_code FROM dim.region WHERE is_leaf ORDER BY 1")
        codes = [c.strip() for (c,) in cur.fetchall()]
    out, empty = [], []
    for code in codes:
        d = s.get(KINDER, params={"key": key, "sidoCode": code[:2], "sggCode": code}, timeout=60).json()
        if d.get("status") not in (None, "SUCCESS"):
            raise RuntimeError(f"유치원알리미 오류 {code}: {d.get('status')} {d.get('message')}")
        info = d.get("kinderInfo") or []
        if not info:
            empty.append(code)
        for k in info:
            out.append((k.get("kindercode") or k.get("kinderCode"), "kindergarten", k.get("kindername"), k.get("addr"),
                        code, num(k.get("lngtcdnt")), num(k.get("lttdcdnt")), num(k.get("prmstfcnt")), k))
        time.sleep(0.2)
    if empty:
        print(f"  유치원 0곳으로 응답한 코드 {len(empty)}개 (코드 체계가 다를 수 있음): {empty[:10]}")
    return out


def fetch_population(s, key, conn):
    now = datetime.now(KST)
    rows = []
    for back in range(1, 4):   # 최근 달부터 (보통 한 달 늦게 올라온다)
        y, m = now.year, now.month - back
        while m < 1:
            y, m = y - 1, m + 12
        ym = f"{y}{m:02d}"
        for sido in POP_SIDO:
            page = 1
            while True:
                d = s.get(POP, params={"serviceKey": key, "stdgCd": f"{sido}00000000", "srchFrYm": ym, "srchToYm": ym,
                                       "lv": "2", "type": "JSON", "numOfRows": 100, "pageNo": page},
                          timeout=60).json()["Response"]
                items = (d.get("items") or {}).get("item") or []
                items = [items] if isinstance(items, dict) else items
                for it in items:
                    age = {f"age{a}": int(it.get(f"male{a}AgeNmprCnt") or 0) + int(it.get(f"feml{a}AgeNmprCnt") or 0)
                           for a in range(0, 101, 10)}
                    rows.append((ym, it["stdgCd"], it.get("ctpvNm"), it.get("sggNm"), int(it.get("totNmprCnt") or 0),
                                 *[age[f"age{a}"] for a in range(0, 101, 10)], json.dumps(it, ensure_ascii=False)))
                if page * 100 >= int(d["head"].get("totalCount") or 0) or not items:
                    break
                page += 1
        if rows:
            break
    if not rows:
        raise RuntimeError("최근 3개월 인구 자료가 없습니다.")
    with conn, conn.cursor() as cur:
        cur.execute("DELETE FROM raw.population_age WHERE stats_ym = %s", (rows[0][0],))
        psycopg2.extras.execute_values(cur, """
            INSERT INTO raw.population_age (stats_ym, stdg_cd, sido_nm, sigungu_nm, total,
                age0, age10, age20, age30, age40, age50, age60, age70, age80, age90, age100, payload) VALUES %s
            ON CONFLICT (stats_ym, stdg_cd) DO NOTHING""", rows)
    print(f"[mois_population] {rows[0][0]}: 시군구 {len(rows)}곳, 인구 {sum(r[4] for r in rows):,}명")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["culture", "park", "cinema", "school", "academy", "kinder", "population", "all"])
    a = ap.parse_args()
    common.load_env()
    dkey = common.service_key()
    edu = os.environ.get("EDU_API_KEY", "").strip()
    edu_child = (os.environ.get("EDUCHILD_API_KEY") or os.environ.get("EDU_CHILD_API_KEY") or "").strip()
    conn = common.connect()
    s = session()
    jobs = ["culture", "park", "cinema", "school", "academy", "kinder", "population"] if a.what == "all" else [a.what]
    failed = []
    for job in jobs:
        try:
            if job == "culture":
                replace_source(conn, "culture_facility", fetch_culture(s, dkey))
            elif job == "park":
                replace_source(conn, "city_park", fetch_park(s, dkey))
            elif job == "cinema":
                replace_source(conn, "mois_cinema", fetch_cinema(s, dkey))
            elif job in ("school", "academy"):
                if not edu:
                    print(f"[{job}] EDU_API_KEY가 .env에 없어 건너뜀")
                    continue
                replace_source(conn, "neis_school" if job == "school" else "neis_academy",
                               fetch_school(s, edu) if job == "school" else fetch_academy(s, edu))
            elif job == "kinder":
                if not edu_child:
                    print("[kinder] EDUCHILD_API_KEY가 .env에 없어 건너뜀")
                    continue
                replace_source(conn, "kinder_info", fetch_kinder(s, edu_child, conn))
            elif job == "population":
                fetch_population(s, dkey, conn)
        except Exception as e:   # 한 원천이 실패해도 나머지는 받는다
            failed.append(job)
            print(f"[{job}] 실패: {e}")
    conn.close()
    if failed:
        sys.exit(f"실패한 원천: {', '.join(failed)}")


if __name__ == "__main__":
    main()
