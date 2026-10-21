"""
한국석유공사 오피넷 「시군구별 주유소 평균가격(현재)」 수집기  → raw.opinet_sigun_price

  가이드: 「오피넷 일반 API 이용 가이드」(2026.10). 인증키는 .env의 OPINET_API_KEY, 파라미터 이름은 'code'.
  (웹 안내 페이지 예시의 certkey로 보내면 오류 없이 빈 결과만 온다)
  [출처 표시] meta.data_source 'opinet_price' — 오피넷 저작권정책상 출처 명시 필수

  - areaCode.do 1번(시도 목록) + 시도마다 avgSigunPrice.do 1번 = 하루 17번 남짓. 일 한도 300회.
  - '현재' 가격만 준다 (하루 6번 갱신: 1·2·9·12·16·19시) → 하루 한 번 받아 snapshot(KST 날짜)으로 쌓는다.
    같은 날 다시 받으면 그날 값을 덮어쓴다.
  - 시군구 이름은 '강원 춘천시'처럼 시도 짧은 이름이 앞에 붙어 온다 (세종만 '세종시') → 떼어서 저장.
    일반구가 있는 시(수원·성남 …)는 시 단위 값 하나만 온다.

사용법:
    python opinet_price.py
"""
import argparse
import os
import sys
import time
from datetime import datetime

import psycopg2.extras
import requests

import molit_rent as common
from pipeline.quota import KST, Quota, QuotaExceeded

BASE = "https://www.opinet.co.kr/api/"
API = "opinet"


def call(s, key, ep, **params):
    r = s.get(BASE + ep, params={"code": key, "out": "json", **params}, timeout=60)
    r.raise_for_status()
    return r.json().get("RESULT", {}).get("OIL", []) or []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=1.0)
    a = ap.parse_args()

    common.load_env()
    key = os.environ.get("OPINET_API_KEY", "").strip()
    if not key:
        sys.exit("OPINET_API_KEY가 .env에 없습니다.")
    snapshot = datetime.now(KST).date()
    conn = common.connect()
    quota = Quota(conn)
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (eodi-salkka data pipeline)"
    saved = 0
    try:
        quota.use(API)
        sidos = call(s, key, "areaCode.do")
        if not sidos:
            sys.exit("시도 목록이 비어 있습니다 (인증키·파라미터 확인).")
        for sd in sidos:
            quota.use(API)
            rows = []
            for d in call(s, key, "avgSigunPrice.do", sido=sd["AREA_CD"]):
                nm = d["SIGUNNM"].strip()
                prefix = sd["AREA_NM"] + " "
                sigun = nm[len(prefix):] if nm.startswith(prefix) else nm
                rows.append((snapshot, d["SIGUNCD"], sd["AREA_NM"], sigun, d["PRODCD"], d["PRICE"], d.get("DIFF")))
            with conn, conn.cursor() as cur:
                psycopg2.extras.execute_values(cur, """
                    INSERT INTO raw.opinet_sigun_price (snapshot, sigun_cd, sido_nm, sigun_nm, prodcd, price, diff)
                    VALUES %s ON CONFLICT (snapshot, sigun_cd, prodcd) DO UPDATE SET
                        sido_nm = EXCLUDED.sido_nm, sigun_nm = EXCLUDED.sigun_nm, price = EXCLUDED.price,
                        diff = EXCLUDED.diff, fetched_at = now()""", rows)
            saved += len(rows)
            time.sleep(a.sleep)
    except QuotaExceeded as e:
        print(e)
    finally:
        conn.close()
    print(f"{snapshot}: {len(sidos)}개 시도, {saved}행 저장")


if __name__ == "__main__":
    main()
