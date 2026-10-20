"""
공공데이터포털 표준데이터 2종 수집기 (지자체별 공공요금)

  - water : 전국상하수도요금표준데이터  https://www.data.go.kr/data/15139217/standard.do
  - trash : 전국종량제봉투가격표준데이터 https://www.data.go.kr/data/15025538/standard.do

[저작자표시 필요] 두 데이터 모두 이용 시 출처를 표시해야 한다.
  화면에 쓸 문구는 DB meta.data_source(source_id = std_water_sewage_fee / std_trash_bag_price)
  와 ATTRIBUTION.md에 있다. 이 데이터를 보여 주는 화면에는 반드시 함께 표시할 것.

사용법:
    python std_fees.py            # 둘 다
    python std_fees.py water      # 하나만

동작:
  1. API(JSON)를 1,000행씩 끝까지 받는다. (포털 활용신청이 된 같은 인증키 사용)
  2. 원본을 data/std/<이름>/<YYYYMMDD>.jsonl로 남긴다. (스냅샷 이력은 파일로 보관)
  3. DB raw 테이블을 통째로 바꾼다. (표준데이터는 '현재 값' 목록이라 이력 대신 최신본 유지)
"""
import json
import sys
import time
from datetime import date
from pathlib import Path

import psycopg2
import psycopg2.extras
import requests

import molit_rent as common  # .env 읽기, 인증키, DB 연결을 같이 쓴다

API = "https://api.data.go.kr/openapi"
PAGE_SIZE = 1000
OUT = Path(__file__).with_name("data") / "std"
TRASH_LITERS = ["1", "1Half", "2", "2Half", "3", "5", "10", "20", "30", "50", "60", "75", "100", "120", "125"]


def to_num(v):
    v = (v or "").replace(",", "").strip()
    try:
        return float(v) if v else None
    except ValueError:
        return None


def to_date(v):
    v = (v or "").strip()
    return v if len(v) == 10 and v[4] == "-" else None


def fetch_all(service, key):
    s = requests.Session()
    items, page = [], 1
    while True:
        r = s.get(f"{API}/{service}", timeout=60,
                  params={"serviceKey": key, "pageNo": page, "numOfRows": PAGE_SIZE, "type": "json"})
        try:
            j = r.json()
        except ValueError:
            sys.exit(f"{service}: JSON이 아닌 응답 (HTTP {r.status_code}) {r.text[:200]}")
        if "OpenAPI_ServiceResponse" in j:
            h = j["OpenAPI_ServiceResponse"]["cmmMsgHeader"]
            sys.exit(f"{service}: [{h.get('returnReasonCode')}] {h.get('errMsg')} — 활용신청 승인 여부를 확인하세요.")
        head, body = j["response"]["header"] if "response" in j else j["header"], \
            j["response"]["body"] if "response" in j else j["body"]
        if head.get("resultCode") not in ("00", "000"):
            sys.exit(f"{service}: [{head.get('resultCode')}] {head.get('resultMsg')}")
        total = int(body.get("totalCount") or 0)
        got = (body.get("items") or {}).get("item") or []
        if isinstance(got, dict):
            got = [got]
        items += got
        print(f"  {service} {page}쪽: 누적 {len(items)}/{total}")
        if not got or len(items) >= total:
            if len(items) != total:
                print(f"  [주의] totalCount {total} ≠ 받은 {len(items)}", file=sys.stderr)
            return items
        page += 1
        time.sleep(0.2)


def save_snapshot(name, items):
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{date.today():%Y%m%d}.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    return p


def rows_water(items):
    for i, it in enumerate(items, 1):
        yield (i, it.get("insttCode"), it.get("insttNm"), it.get("mngInstNm"), it.get("mngNo"),
               it.get("tpbizSeNm"), it.get("wsdrSeNm"), to_num(it.get("bgngUsqty")), to_num(it.get("endUsqty")),
               to_num(it.get("untprc")), to_date(it.get("dataCrtrYmd")), json.dumps(it, ensure_ascii=False))


def rows_trash(items):
    for i, it in enumerate(items, 1):
        prices = {}
        for l in TRASH_LITERS:
            v = to_num(it.get(f"price{l}"))
            if v:  # 0 = 해당 규격 없음
                prices[l.replace("Half", ".5")] = int(v)
        yield (i, it.get("insttCode"), it.get("insttNm"), it.get("ctprvnNm"), it.get("signguNm"),
               it.get("weightedEnvlpType"), it.get("weightedEnvlpMthd"), it.get("weightedEnvlpPrpos"),
               it.get("weightedEnvlpTrget"), prices.get("20"), json.dumps(prices),
               to_date(it.get("referenceDate")), json.dumps(it, ensure_ascii=False))


JOBS = {
    "water": ("tn_pubr_public_water_sewage_fees_api", "raw.std_water_sewage_fee", rows_water,
              "item_seq, instt_code, instt_nm, mng_inst_nm, mng_no, sector, kind, usage_from, usage_to, "
              "unit_price, data_date, payload", "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)"),
    "trash": ("tn_pubr_public_weighted_envlp_api", "raw.std_trash_bag_price", rows_trash,
              "item_seq, instt_code, instt_nm, sido_nm, sigungu_nm, bag_type, method, purpose, target, "
              "price_20l, prices, data_date, payload", "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb)"),
}


def main():
    common.load_env()
    key = common.service_key()
    names = sys.argv[1:] or list(JOBS)
    conn = common.connect()
    for name in names:
        service, table, to_rows, cols, tmpl = JOBS[name]
        print(f"[{name}] 받는 중")
        items = fetch_all(service, key)
        snap = save_snapshot(name, items)
        with conn, conn.cursor() as cur:
            cur.execute(f"TRUNCATE {table}")
            psycopg2.extras.execute_values(cur, f"INSERT INTO {table} ({cols}) VALUES %s",
                                           list(to_rows(items)), template=tmpl, page_size=1000)
        print(f"[{name}] {len(items)}행 → {table}, 원본 {snap}")
    conn.close()


if __name__ == "__main__":
    main()
