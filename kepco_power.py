"""
한국전력공사 전력데이터개방포털 「가구평균 전력사용량」 수집기  → raw.kepco_house_power

  API 안내: https://bigdata.kepco.co.kr/cmsmain.do?scode=S01&pcode=000493&pstate=house
  요청: /openapi/v1/powerUsage/houseAve.do?year=YYYY&month=MM&metroCd=시도코드&apiKey=…
  인증키: .env의 KEPCO_API_KEY (40자리). 값은 출력·기록하지 않는다.
  [출처 표시] meta.data_source 'kepco_house_power'

  - 시도 하나 × 달 하나 = 호출 1번, 그 시도의 시군구가 전부 온다. 2014-01부터, 보통 2달 늦게 올라온다.
  - 시도코드는 한전 공통코드(lglDngMetroCd). 통합 뒤에도 광주(29)·전남(46)으로 와야 값이 있고,
    전남광주(12)는 아직 비어 있다. 전북은 45와 52 둘 다 있다 → 전부 부르고 (연월, 시도명, 시군구명)으로 합친다.
  - 화성시·부천시처럼 구가 새로 생긴 시는 '시 전체' 행과 '구' 행이 같이 온다 → 그대로 저장하고
    집계(sql/mart/60_power.sql)에서 구 행을 먼저 쓴다.

사용법:
    python kepco_power.py                       # 안 받은 달만 (2014-01 ~ 지난달), 최근 3개월은 다시 확인
    python kepco_power.py --from 202301 --to 202608
    python kepco_power.py --refresh-months 0    # 최근 달 다시 확인 안 함

같은 (연월, 시도명, 시군구명)은 덮어쓴다 → 여러 번 실행해도 결과가 같다.
"""
import argparse
import json
import os
import sys
import time
from datetime import date

import psycopg2.extras
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import molit_rent as common
from pipeline.quota import KST, Quota, QuotaExceeded

BASE = "https://bigdata.kepco.co.kr/openapi/v1/"
API = "kepco"   # pipeline/quota.py 예산 이름
METROS = ["11", "26", "27", "28", "29", "30", "31", "36", "41", "43", "44", "45", "46", "47", "48", "50",
          "51", "52", "12"]
START = "201401"


def months(frm, to):
    y, m = int(frm[:4]), int(frm[4:])
    while f"{y}{m:02d}" <= to:
        yield f"{y}{m:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def last_month():
    t = date.today()
    return f"{t.year - 1}12" if t.month == 1 else f"{t.year}{t.month - 1:02d}"


def shift(ym, k):
    y, m = int(ym[:4]), int(ym[4:]) - k
    while m < 1:
        y, m = y - 1, m + 12
    return f"{y}{m:02d}"


def session():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (eodi-salkka data pipeline)"
    s.mount("https://", HTTPAdapter(max_retries=Retry(total=5, backoff_factor=2,
                                                      status_forcelist=[429, 500, 502, 503, 504])))
    return s


def fetch_one(s, key, ym, metro):
    r = s.get(BASE + "powerUsage/houseAve.do", timeout=60,
              params={"year": ym[:4], "month": ym[4:], "metroCd": metro, "apiKey": key, "returnType": "json"})
    try:
        body = r.json()
    except ValueError:
        raise RuntimeError(f"{ym} {metro}: JSON 아님 (HTTP {r.status_code}) {r.text[:120]!r}")
    if "errCd" in body:
        if str(body.get("errCd")) == "404":   # 그 달·시도 자료 없음 (빈 목록 대신 404로 온다)
            return []
        raise RuntimeError(f"{ym} {metro}: 오류 {body.get('errCd')} {body.get('errMsg')}")
    return body.get("data") or []


def num(v, cast=float):
    try:
        return cast(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default=START)
    ap.add_argument("--to", default=None, help="기본: 지난달")
    ap.add_argument("--refresh-months", type=int, default=3, help="최근 N개월은 받았어도 다시 확인 (늦게 올라오는 달)")
    ap.add_argument("--max-calls", type=int, default=3000)
    ap.add_argument("--sleep", type=float, default=0.3)
    a = ap.parse_args()

    common.load_env()
    key = os.environ.get("KEPCO_API_KEY", "").strip()
    if not key:
        sys.exit("KEPCO_API_KEY가 .env에 없습니다.")
    to = a.to or last_month()
    refresh_from = shift(to, a.refresh_months - 1) if a.refresh_months > 0 else "999999"

    conn = common.connect()
    quota = Quota(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT ym, metro_cd FROM raw.kepco_fetch_log")
        done = set(cur.fetchall())
    todo = [(ym, mc) for ym in months(a.frm, to) for mc in METROS
            if (ym, mc) not in done or ym >= refresh_from]
    print(f"{a.frm}~{to}: 부를 묶음 {len(todo)}개 (받은 기록 {len(done)}개, {refresh_from} 이후는 다시 확인)")

    s, calls, saved = session(), 0, 0
    try:
        for ym, mc in todo:
            if calls >= a.max_calls:
                print(f"--max-calls {a.max_calls}에 닿아 멈춥니다.")
                break
            quota.use(API)
            data = fetch_one(s, key, ym, mc)
            calls += 1
            rows = [(ym, d.get("metro") or "", d.get("city") or "", mc, num(d.get("houseCnt"), int),
                     num(d.get("powerUsage")), num(d.get("bill"), lambda v: int(round(float(v)))),
                     json.dumps(d, ensure_ascii=False))
                    for d in data if d.get("metro") and d.get("city")]
            with conn, conn.cursor() as cur:
                if rows:
                    psycopg2.extras.execute_values(cur, """
                        INSERT INTO raw.kepco_house_power
                            (ym, metro_nm, city_nm, metro_cd, house_cnt, power_kwh, bill, payload) VALUES %s
                        ON CONFLICT (ym, metro_nm, city_nm) DO UPDATE SET
                            metro_cd = EXCLUDED.metro_cd, house_cnt = EXCLUDED.house_cnt,
                            power_kwh = EXCLUDED.power_kwh, bill = EXCLUDED.bill,
                            payload = EXCLUDED.payload, fetched_at = now()""", rows)
                cur.execute("""INSERT INTO raw.kepco_fetch_log (ym, metro_cd, rows) VALUES (%s, %s, %s)
                               ON CONFLICT (ym, metro_cd) DO UPDATE SET rows = EXCLUDED.rows, fetched_at = now()""",
                            (ym, mc, len(rows)))
            saved += len(rows)
            if calls % 100 == 0:
                print(f"  {calls}회 호출, {saved}행 저장 (지금 {ym} {mc})", flush=True)
            time.sleep(a.sleep)
    except QuotaExceeded as e:
        print(e)
    finally:
        conn.close()
    print(f"완료: {calls}회 호출, {saved}행 저장")


if __name__ == "__main__":
    main()
