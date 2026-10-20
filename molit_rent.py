"""
국토교통부 전월세 실거래가 수집기 (아파트, 오피스텔, 단독·다가구, 연립·다세대)

사용법:
    # 강원 18개 시군, 2023-01 ~ 2026-09, 4개 유형 모두
    python molit_rent.py fetch --from 202301 --to 202609

    # 일부만
    python molit_rent.py fetch --from 202409 --to 202409 --types apt --regions 51110

    # 42/51 코드가 기간별로 어떻게 응답하는지 건수만 비교 (DB에 쓰지 않음)
    python molit_rent.py probe --region 51110 --months 202305,202306,202307

설정 (.env 또는 환경변수):
    DATA_GO_KR_SERVICE_KEY  공공데이터포털 인증키 (Decoding 키 권장. Encoding 키도 자동으로 풀어 씀)
    POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_PORT (기본 eodi / eodi / eodi_local / 5433)

동작:
  - 대상 지역은 dim.region에서 in_scope = true인 시군.
  - 요청 코드: --codes auto(기본)는 dim.lawd_cd_for()로 계약년월에 맞는 코드 1개,
               --codes both는 42xxx, 51xxx 둘 다 받는다(코드 전환기 검증용).
  - (유형, 코드, 연월) 단위로 모든 페이지를 받은 뒤 한 트랜잭션으로 지우고 다시 넣는다.
  - raw.molit_rent_fetch_log에 받은 기록이 있으면 건너뛴다(이어받기).
    단, 최근 --recent-months개월은 늦게 신고된 거래가 있어 매번 다시 받는다.
  - 하루 호출 한도(개발계정 1만 건)를 넘지 않게 --max-calls에서 멈춘다.
"""
import argparse
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from urllib.parse import unquote

import psycopg2
import psycopg2.extras
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://apis.data.go.kr/1613000"
ENDPOINTS = {
    "apt": "RTMSDataSvcAptRent/getRTMSDataSvcAptRent",
    "officetel": "RTMSDataSvcOffiRent/getRTMSDataSvcOffiRent",
    "detached": "RTMSDataSvcSHRent/getRTMSDataSvcSHRent",
    "row_house": "RTMSDataSvcRHRent/getRTMSDataSvcRHRent",
}
PAGE_SIZE = 1000
OK_CODES = {"00", "000"}
# 응답 필드명이 버전마다 달라 후보를 순서대로 본다 (영문 신규 이름 → 한글 옛 이름)
DEPOSIT_KEYS = ["deposit", "보증금액", "보증금"]
RENT_KEYS = ["monthlyRent", "월세금액", "월세"]
AREA_KEYS = ["excluUseAr", "totalFloorAr", "전용면적", "계약면적", "연면적"]


class ApiError(RuntimeError):
    def __init__(self, code, msg, fatal=False):
        super().__init__(f"[{code}] {msg}")
        self.code, self.fatal = code, fatal


class CallLimit(RuntimeError):
    pass


# ── 설정 ──────────────────────────────────────────────────
def load_env(path=Path(__file__).with_name(".env")):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def service_key():
    key = os.environ.get("DATA_GO_KR_SERVICE_KEY", "").strip()
    if not key:
        sys.exit("DATA_GO_KR_SERVICE_KEY가 비어 있습니다. .env에 인증키를 넣어 주세요.")
    # Encoding 키(%2B 등)를 넣었으면 풀어서 requests가 한 번만 인코딩하게 한다
    return unquote(key) if "%" in key else key


def connect():
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", 5433)),
        dbname=os.environ.get("POSTGRES_DB", "eodi"),
        user=os.environ.get("POSTGRES_USER", "eodi"),
        password=os.environ.get("POSTGRES_PASSWORD", "eodi_local"),
    )


# ── API ───────────────────────────────────────────────────
# API(서비스)별 하루 한도를 나눠 쓰기 위한 이름 → pipeline/quota.py
QUOTA_API = {"apt": "molit_apt_rent", "officetel": "molit_offi_rent",
             "detached": "molit_sh_rent", "row_house": "molit_rh_rent"}


class Client:
    def __init__(self, key, max_calls, sleep, quota=None):
        self.key, self.max_calls, self.sleep, self.calls = key, max_calls, sleep, 0
        self.quota = quota
        self.s = requests.Session()
        retry = Retry(total=4, connect=4, read=4, backoff_factor=2,
                      status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
        self.s.mount("https://", HTTPAdapter(max_retries=retry))

    def page(self, house_type, lawd_cd, deal_ym, page_no, rows=PAGE_SIZE):
        if self.calls >= self.max_calls:
            raise CallLimit(f"이번 실행 호출 한도 {self.max_calls}회에 도달했습니다.")
        if self.quota:
            from pipeline.quota import QuotaExceeded
            try:
                self.quota.use(QUOTA_API[house_type])
            except QuotaExceeded as e:
                raise CallLimit(str(e))
        self.calls += 1
        r = self.s.get(f"{BASE}/{ENDPOINTS[house_type]}", timeout=30, params={
            "serviceKey": self.key, "LAWD_CD": lawd_cd, "DEAL_YMD": deal_ym,
            "pageNo": page_no, "numOfRows": rows})
        time.sleep(self.sleep)
        return parse_response(r.content, r.status_code)

    def fetch_all(self, house_type, lawd_cd, deal_ym):
        items, page_no, total = [], 1, None
        while True:
            code, msg, total, page_items = self.page(house_type, lawd_cd, deal_ym, page_no)
            items += page_items
            if not page_items or len(items) >= total:
                return code, total, items
            page_no += 1


def parse_response(content, status):
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        raise ApiError(f"HTTP{status}", content[:200].decode("utf-8", "replace"))
    # 게이트웨이 오류 (인증키 문제, 한도 초과 등)
    if root.tag == "OpenAPI_ServiceResponse":
        code = root.findtext(".//returnReasonCode", "")
        msg = root.findtext(".//errMsg", "") + " " + root.findtext(".//returnAuthMsg", "")
        # 20 미등록/접근거부, 22 한도 초과, 30 미등록 키, 31 기한 만료 → 더 해도 소용없음
        raise ApiError(code, msg.strip(), fatal=code in {"20", "22", "30", "31", "32"})
    code = root.findtext(".//header/resultCode", "").strip()
    msg = root.findtext(".//header/resultMsg", "").strip()
    if code not in OK_CODES:
        raise ApiError(code, msg, fatal=code in {"20", "22", "30", "31", "32"})
    total = int(root.findtext(".//body/totalCount", "0") or 0)
    items = [{c.tag: (c.text or "").strip() for c in it} for it in root.iter("item")]
    return code, msg, total, items


def num(item, keys, cast=int):
    for k in keys:
        v = item.get(k, "").replace(",", "").strip()
        if v:
            try:
                return cast(float(v)) if cast is int else cast(v)
            except ValueError:
                return None
    return None


# ── DB ────────────────────────────────────────────────────
def regions(cur, only):
    cur.execute("SELECT region_code, legacy_code, sigungu FROM dim.region WHERE in_scope ORDER BY region_code")
    rows = cur.fetchall()
    if only:
        rows = [r for r in rows if r[0] in only or r[1] in only]
    return rows


def codes_for(cur, region_code, legacy, ym, mode):
    if mode == "both":
        return [c for c in (legacy, region_code) if c]
    if mode == "legacy":
        return [legacy or region_code]
    if mode == "new":
        return [region_code]
    cur.execute("SELECT dim.lawd_cd_for(%s, %s)", (region_code, ym))
    return [cur.fetchone()[0]]


def already_fetched(cur, house_type, lawd_cd, ym):
    cur.execute("SELECT 1 FROM raw.molit_rent_fetch_log WHERE house_type=%s AND lawd_cd=%s AND deal_ym=%s",
                (house_type, lawd_cd, ym))
    return cur.fetchone() is not None


def save(conn, house_type, lawd_cd, ym, code, total, items):
    rows = [(house_type, lawd_cd, ym, i, json.dumps(it, ensure_ascii=False),
             num(it, DEPOSIT_KEYS), num(it, RENT_KEYS), num(it, AREA_KEYS, float))
            for i, it in enumerate(items, 1)]
    with conn, conn.cursor() as cur:
        cur.execute("DELETE FROM raw.molit_rent WHERE house_type=%s AND lawd_cd=%s AND deal_ym=%s",
                    (house_type, lawd_cd, ym))
        psycopg2.extras.execute_values(cur, """
            INSERT INTO raw.molit_rent (house_type, lawd_cd, deal_ym, item_seq, payload, deposit, monthly_rent, area_m2)
            VALUES %s""", rows, template="(%s, %s, %s, %s, %s::jsonb, %s, %s, %s)")
        cur.execute("""
            INSERT INTO raw.molit_rent_fetch_log (house_type, lawd_cd, deal_ym, total_count, result_code, fetched_at)
            VALUES (%s, %s, %s, %s, %s, now())
            ON CONFLICT (house_type, lawd_cd, deal_ym)
            DO UPDATE SET total_count = EXCLUDED.total_count, result_code = EXCLUDED.result_code, fetched_at = now()
        """, (house_type, lawd_cd, ym, total, code))


# ── 명령 ──────────────────────────────────────────────────
def month_range(a, b):
    y, m = int(a[:4]), int(a[4:])
    while f"{y}{m:02d}" <= b:
        yield f"{y}{m:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def recent_months(n):
    t = date.today()
    y, m = t.year, t.month
    out = set()
    for _ in range(n):
        out.add(f"{y}{m:02d}")
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return out


def months_back_range(n):
    """n개월 전 ~ 지난달 (YYYYMM, YYYYMM)"""
    t = date.today()
    y, m = t.year, t.month
    y2, m2 = (y - 1, 12) if m == 1 else (y, m - 1)
    y1, m1 = y2, m2
    for _ in range(n - 1):
        y1, m1 = (y1 - 1, 12) if m1 == 1 else (y1, m1 - 1)
    return f"{y1}{m1:02d}", f"{y2}{m2:02d}"


def cmd_fetch(a):
    from pipeline.quota import Quota
    if a.months_back:
        a.from_ym, a.to_ym = months_back_range(a.months_back)
    if not (a.from_ym and a.to_ym):
        sys.exit("--from/--to 또는 --months-back을 주세요.")
    conn = connect()
    client = Client(service_key(), a.max_calls, a.sleep, quota=Quota(conn))
    types = a.types.split(",")
    unknown = set(types) - set(ENDPOINTS)
    if unknown:
        sys.exit(f"알 수 없는 유형: {unknown} (가능: {', '.join(ENDPOINTS)})")
    fresh = recent_months(a.recent_months)
    with conn.cursor() as cur:
        regs = regions(cur, set(a.regions.split(",")) if a.regions else None)
    if not regs:
        sys.exit("대상 지역이 없습니다. dim.region을 확인하세요.")
    months = list(month_range(a.from_ym, a.to_ym))
    print(f"대상: {len(regs)}개 시군 × {len(months)}개월 × {len(types)}개 유형 (코드 방식 {a.codes})")

    stored = skipped = failed = 0
    try:
        for ym in months:
            for region_code, legacy, name in regs:
                with conn.cursor() as cur:
                    codes = codes_for(cur, region_code, legacy, ym, a.codes)
                for lawd_cd in codes:
                    for t in types:
                        with conn.cursor() as cur:
                            if not a.refresh and ym not in fresh and already_fetched(cur, t, lawd_cd, ym):
                                skipped += 1
                                continue
                        try:
                            code, total, items = client.fetch_all(t, lawd_cd, ym)
                        except ApiError as e:
                            if e.fatal:
                                raise
                            print(f"[실패] {ym} {name}({lawd_cd}) {t}: {e}", file=sys.stderr)
                            failed += 1
                            continue
                        save(conn, t, lawd_cd, ym, code, total, items)
                        stored += len(items)
                        if len(items) != total:
                            print(f"[주의] {ym} {name}({lawd_cd}) {t}: totalCount {total} ≠ 받은 {len(items)}",
                                  file=sys.stderr)
                        print(f"[받음] {ym} {name}({lawd_cd}) {t}: {len(items)}건")
    except CallLimit as e:
        print(f"[멈춤] {e} 다시 실행하면 이어서 받습니다.", file=sys.stderr)
    except ApiError as e:
        print(f"[중단] API 오류 {e} — 인증키 등록 상태나 하루 한도를 확인하세요.", file=sys.stderr)
    finally:
        conn.close()
    print(f"완료: 저장 {stored}건, 건너뜀 {skipped}묶음, 실패 {failed}묶음, API 호출 {client.calls}회")


def cmd_probe(a):
    from pipeline.quota import Quota
    conn = connect()
    client = Client(service_key(), a.max_calls, a.sleep, quota=Quota(conn))
    with conn.cursor() as cur:
        regs = regions(cur, {a.region})
    if not regs:
        sys.exit(f"dim.region에 {a.region}이 없습니다.")
    region_code, legacy, name = regs[0]
    print(f"{name}: 구 코드 {legacy} / 신 코드 {region_code} — totalCount 비교")
    print(f"{'연월':8}{'유형':11}{legacy:>8}{region_code:>8}")
    for ym in a.months.split(","):
        for t in a.types.split(","):
            counts = []
            for c in (legacy, region_code):
                try:
                    counts.append(str(client.page(t, c, ym, 1, rows=1)[2]))
                except ApiError as e:
                    if e.fatal:
                        sys.exit(f"API 오류 {e}")
                    counts.append(f"오류{e.code}")
            print(f"{ym:8}{t:11}{counts[0]:>8}{counts[1]:>8}")
    conn.close()
    print(f"API 호출 {client.calls}회")


def main():
    load_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--types", default=",".join(ENDPOINTS))
    common.add_argument("--max-calls", type=int, default=9000, help="이번 실행 최대 API 호출 수")
    common.add_argument("--sleep", type=float, default=0.2, help="호출 사이 간격(초)")

    f = sub.add_parser("fetch", parents=[common])
    f.add_argument("--from", dest="from_ym", help="YYYYMM")
    f.add_argument("--to", dest="to_ym", help="YYYYMM")
    f.add_argument("--months-back", type=int, help="N개월 전 ~ 지난달 (--from/--to 대신, 정기 실행용)")
    f.add_argument("--regions", help="쉼표로 구분한 시군 코드 (신·구 코드 모두 가능)")
    f.add_argument("--codes", choices=["auto", "both", "legacy", "new"], default="auto")
    f.add_argument("--refresh", action="store_true", help="받은 기록이 있어도 다시 받기")
    f.add_argument("--recent-months", type=int, default=2, help="항상 다시 받을 최근 개월 수")
    f.set_defaults(func=cmd_fetch)

    p = sub.add_parser("probe", parents=[common])
    p.add_argument("--region", required=True)
    p.add_argument("--months", required=True, help="쉼표로 구분한 YYYYMM")
    p.set_defaults(func=cmd_probe)

    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
