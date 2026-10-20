"""
한국소비자원_생필품 가격 정보_GW 수집기 (참가격, data.go.kr 15158701)

[저작자표시 필요 — 공공누리 1유형] 화면에 쓸 때는 meta.data_source 'kca_price' 문구를 함께 표시한다.

사용법:
    python kca_price.py meta                         # 판매점·상품·기준코드 전체 갱신 (호출 약 7회)
    python kca_price.py days --from 2026-01-01       # 금요일마다 자료가 있는지 확인 (금요일 1개당 1회)
    python kca_price.py prices --latest 2            # 자료 있는 최근 조사일 2개의 가격 받기
    python kca_price.py prices --days 2026-10-09,2026-09-25

API 메모 (2026-10-21 확인):
  - 기준코드 classCode: AR 지역(시도·시군구 311개), AL 상품분류(188개, 3단계), BU 업태, UT 단위
  - 가격 조회는 goodInspectDay(조사일) + goodId 또는 entpId가 필요하다.
    조사는 격주 금요일. 상품 1개 조회 = 전국 판매점 약 130~140곳.
  - 개발계정 하루 2,000회 → 조사일 1개 ≈ 상품 수(약 600)만큼 호출. --max-calls로 멈추고 다음 날 이어받는다.
  - 가격은 '현재 상품 목록'의 goodId로 돈다. 단종된 옛 상품은 과거 조사일에서 빠질 수 있다.
"""
import argparse
import json
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

import psycopg2.extras
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import molit_rent as common  # .env, 인증키, DB 연결

BASE = "https://apis.data.go.kr/B551919/ProductPriceInfoService"
CODE_CLASSES = {"AR": "지역", "AL": "상품분류", "BU": "업태", "UT": "단위"}
# 조사일 탐색용: 오래 팔린 기본 상품 몇 개 (하나라도 결과가 있으면 그날은 조사일)
PROBE_GOODS = ["35"]


class CallLimit(RuntimeError):
    pass


class Client:
    def __init__(self, key, max_calls, sleep):
        self.key, self.max_calls, self.sleep, self.calls = key, max_calls, sleep, 0
        self.s = requests.Session()
        self.s.mount("https://", HTTPAdapter(max_retries=Retry(
            total=4, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])))

    def get(self, op, **params):
        if self.calls >= self.max_calls:
            raise CallLimit(f"이번 실행 호출 한도 {self.max_calls}회에 도달했습니다. 다시 실행하면 이어서 받습니다.")
        self.calls += 1
        r = self.s.get(f"{BASE}/{op}", params={"serviceKey": self.key, **params}, timeout=120)
        time.sleep(self.sleep)
        root = ET.fromstring(r.content)
        if root.tag == "OpenAPI_ServiceResponse":
            code = root.findtext(".//returnReasonCode", "")
            sys.exit(f"API 오류 [{code}] {root.findtext('.//errMsg', '')} — 활용신청·일일 한도(22)를 확인하세요.")
        res = root.find("result")
        if res is None:
            code, msg = root.findtext("resultCode", ""), root.findtext("resultMsg", "")
            if code not in ("", "00"):
                raise RuntimeError(f"{op} {params}: [{code}] {msg}")
            return []
        return [{c.tag: (c.text or "").strip() for c in it} for it in res]


def num(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def to_day(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


# ── meta ─────────────────────────────────────────────────
def cmd_meta(a, cli, conn):
    codes = []
    for cc in CODE_CLASSES:
        items = cli.get("getStandardInfoSvc.do", classCode=cc)
        codes += [(cc, i.get("code"), i.get("codeName"), i.get("highCode") or None) for i in items]
        print(f"  기준코드 {cc}({CODE_CLASSES[cc]}): {len(items)}개")
    stores = cli.get("getStoreInfoSvc.do")
    products = cli.get("getProductInfoSvc.do")
    with conn, conn.cursor() as cur:
        cur.execute("TRUNCATE raw.kca_code")
        psycopg2.extras.execute_values(cur, "INSERT INTO raw.kca_code (class_code, code, code_name, high_code) VALUES %s", codes)
        cur.execute("TRUNCATE raw.kca_store")
        psycopg2.extras.execute_values(cur, """
            INSERT INTO raw.kca_store (entp_id, entp_name, type_code, area_code, area_detail_code, tel, post_no,
                                       addr_jibun, addr_road, lat, lon, payload) VALUES %s""",
            [(s.get("entpId"), s.get("entpName"), s.get("entpTypeCode"), s.get("entpAreaCode"), s.get("areaDetailCode"),
              s.get("entpTelno"), s.get("postNo"),
              " ".join(x for x in (s.get("plmkAddrBasic"), s.get("plmkAddrDetail")) if x) or None,
              " ".join(x for x in (s.get("roadAddrBasic"), s.get("roadAddrDetail")) if x) or None,
              num(s.get("xMapCoord")), num(s.get("yMapCoord")), json.dumps(s, ensure_ascii=False)) for s in stores],
            template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)")
        cur.execute("TRUNCATE raw.kca_product")
        psycopg2.extras.execute_values(cur, """
            INSERT INTO raw.kca_product (good_id, good_name, maker_code, small_class_code, base_cnt, unit_code,
                                         total_cnt, total_unit_code, detail, payload) VALUES %s""",
            [(p.get("goodId"), p.get("goodName"), p.get("productEntpCode"), p.get("goodSmlclsCode"),
              num(p.get("goodBaseCnt")), p.get("goodUnitDivCode"), num(p.get("goodTotalCnt")),
              p.get("goodTotalDivCode"), p.get("datailMean"), json.dumps(p, ensure_ascii=False)) for p in products],
            template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)")
    print(f"판매점 {len(stores)}곳, 상품 {len(products)}개, 기준코드 {len(codes)}개 저장")


# ── days ─────────────────────────────────────────────────
def fridays(d0, d1):
    d = d0 + timedelta(days=(4 - d0.weekday()) % 7)
    while d <= d1:
        yield d
        d += timedelta(days=7)


def cmd_days(a, cli, conn):
    d0, d1 = to_day(a.from_day), to_day(a.to_day) if a.to_day else date.today()
    with conn.cursor() as cur:
        cur.execute("SELECT inspect_day FROM raw.kca_survey_day WHERE has_data")
        known = {r[0] for r in cur.fetchall()}
        cur.execute("SELECT inspect_day FROM raw.kca_survey_day WHERE NOT has_data AND probed_at > now() - interval '7 days'")
        recent_empty = {r[0] for r in cur.fetchall()}
    found = 0
    try:
        for d in fridays(d0, d1):
            if d in known or d in recent_empty:
                continue
            has = any(cli.get("getProductPriceInfoSvc", goodInspectDay=d.strftime("%Y%m%d"), goodId=g) for g in PROBE_GOODS)
            with conn, conn.cursor() as cur:
                cur.execute("""INSERT INTO raw.kca_survey_day (inspect_day, has_data) VALUES (%s, %s)
                               ON CONFLICT (inspect_day) DO UPDATE SET has_data = EXCLUDED.has_data, probed_at = now()""",
                            (d, has))
            found += has
            print(f"  {d} {'조사일' if has else '-'}")
    except CallLimit as e:
        print(f"[멈춤] {e}", file=sys.stderr)
    print(f"새로 찾은 조사일 {found}개, API 호출 {cli.calls}회")


# ── prices ───────────────────────────────────────────────
def cmd_prices(a, cli, conn):
    with conn.cursor() as cur:
        if a.days:
            days = [to_day(x) for x in a.days.split(",")]
        else:
            cur.execute("SELECT inspect_day FROM raw.kca_survey_day WHERE has_data ORDER BY inspect_day DESC LIMIT %s",
                        (a.latest,))
            days = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT good_id FROM raw.kca_product ORDER BY good_id::int")
        goods = [r[0] for r in cur.fetchall()]
    if not days:
        sys.exit("조사일이 없습니다. 먼저 `python kca_price.py days --from YYYY-MM-DD`를 실행하세요.")
    if not goods:
        sys.exit("상품 목록이 없습니다. 먼저 `python kca_price.py meta`를 실행하세요.")
    print(f"조사일 {', '.join(map(str, days))} × 상품 {len(goods)}개")
    stored = 0
    try:
        for d in days:
            with conn.cursor() as cur:
                cur.execute("SELECT good_id FROM raw.kca_price_fetch_log WHERE inspect_day = %s", (d,))
                done = {r[0] for r in cur.fetchall()} if not a.refresh else set()
            todo = [g for g in goods if g not in done]
            n_day = 0
            for i, g in enumerate(todo, 1):
                items = cli.get("getProductPriceInfoSvc", goodInspectDay=d.strftime("%Y%m%d"), goodId=g)
                rows = [(d, it.get("entpId"), it.get("goodId") or g, int(num(it.get("goodPrice")) or 0) or None,
                         it.get("goodDcYn") or None, it.get("goodDcStartDay") or None, it.get("goodDcEndDay") or None,
                         it.get("plusoneYn") or None, it.get("inputDttm") or None) for it in items]
                with conn, conn.cursor() as cur:
                    cur.execute("DELETE FROM raw.kca_price WHERE inspect_day = %s AND good_id = %s", (d, g))
                    if rows:
                        psycopg2.extras.execute_values(cur, """
                            INSERT INTO raw.kca_price (inspect_day, entp_id, good_id, price, dc_yn, dc_start_day,
                                                       dc_end_day, plusone_yn, input_dttm) VALUES %s
                            ON CONFLICT DO NOTHING""", rows)
                    cur.execute("""INSERT INTO raw.kca_price_fetch_log (inspect_day, good_id, n_items) VALUES (%s, %s, %s)
                                   ON CONFLICT (inspect_day, good_id) DO UPDATE SET n_items = EXCLUDED.n_items, fetched_at = now()""",
                                (d, g, len(rows)))
                n_day += len(rows)
                if i % 100 == 0:
                    print(f"  {d}: 상품 {i}/{len(todo)}, 누적 {n_day}건")
            stored += n_day
            print(f"[받음] {d}: {n_day}건 (이번 실행 상품 {len(todo)}개)")
    except CallLimit as e:
        print(f"[멈춤] {e}", file=sys.stderr)
    print(f"완료: 저장 {stored}건, API 호출 {cli.calls}회")


def main():
    common.load_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-calls", type=int, default=1900, help="이번 실행 최대 호출 수 (개발계정 하루 2,000회)")
    ap.add_argument("--sleep", type=float, default=0.1)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("meta").set_defaults(func=cmd_meta)
    d = sub.add_parser("days")
    d.add_argument("--from", dest="from_day", required=True, help="YYYY-MM-DD")
    d.add_argument("--to", dest="to_day", help="YYYY-MM-DD (기본 오늘)")
    d.set_defaults(func=cmd_days)
    p = sub.add_parser("prices")
    p.add_argument("--latest", type=int, default=1, help="자료 있는 최근 조사일 개수")
    p.add_argument("--days", help="쉼표로 구분한 YYYY-MM-DD (지정하면 --latest 무시)")
    p.add_argument("--refresh", action="store_true")
    p.set_defaults(func=cmd_prices)
    a = ap.parse_args()
    cli = Client(common.service_key(), a.max_calls, a.sleep)
    conn = common.connect()
    try:
        a.func(a, cli, conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
