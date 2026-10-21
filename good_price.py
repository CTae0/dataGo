"""
행정안전부_착한가격업소 현황 적재기  → raw.good_price_store, raw.good_price_menu

  데이터: https://www.data.go.kr/data/3045247/fileData.do  (분기 파일, 이용허락범위 제한 없음)
  [출처] meta.data_source 'good_price'

  착한가격업소는 지역 평균보다 싼 가게를 지자체가 지정한 표본이다 → 외식비 '수준'으로 쓰지 않는다.
  시군구별 가성비 식당 수(인구 대비 등) 지표용. 조사 결과: docs/research/dining_sources.md

사용법:
    python good_price.py                 # 포털에서 최신 파일을 받고(과거 파일은 이미 받은 것 재사용) 전부 적재
    python good_price.py --no-download   # data/good_price에 있는 파일만 적재
    python good_price.py --latest-only   # 최신 스냅샷만 적재

동작:
  1. datago_periodic.py로 data/good_price/raw에 현재 + 과거 파일을 받는다 (이미 받은 과거 파일은 건너뜀)
  2. 파일마다 스냅샷 기준일을 정한다: 파일 이름의 _YYYYMMDD와 포털 등록일 중 이른 날
     (이름의 날짜가 등록일보다 늦은 파일이 있다. 예: '_20221231' 등록일 2022-08-30)
  3. 같은 스냅샷 행을 지우고 다시 넣는다 → 여러 번 실행해도 결과가 같다

파일 형식 (헤더로 판별)
  2019~2020  : 순번, 업종, 업소명, 대표자, 시/도(시도), 시/군/구(시군), 주소, 연락처, 대표품목, 가격 …
  2022~      : 시도, 시군, 업종, 업소명, (연락처), 주소, 메뉴1, 가격1 … 메뉴4, 가격4
  2020-09-18 등록본 하나는 업소 목록이 아니라 시도별 집계표 → 건너뜀
  대표자 이름·연락처는 개인정보라 저장하지 않는다 (payload에서도 뺀다).
"""
import argparse
import csv
import io
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import psycopg2.extras

import molit_rent as common  # .env 읽기, DB 연결

PK = "3045247"
OUT = Path(__file__).with_name("data") / "good_price"
ALIASES = {
    "sido": ["시도", "시/도"],
    "sigungu": ["시군", "시/군/구"],
    "biz": ["업종"],
    "store": ["업소명"],
    "addr": ["주소", "주소(도로명 새주소 명기)"],
}
PRIVATE = {"대표자", "연락처"}
# 업종 표기가 파일마다 제각각이라('한식_일반', '한식 육류', '기타요식업(커피디저트등)' …) 키워드로 외식업을 판정한다
DINING_WORDS = ("한식", "한실", "중식", "일식", "양식", "요식", "외식", "분식", "음식", "베이커리", "제과",
                "카페", "커피", "다방", "뷔페", "뷔폐", "찌개", "면류", "해산물", "횟집", "돈까스", "한정식")


def read_csv(path):
    b = path.read_bytes()
    for enc in ("utf-8-sig", "cp949"):
        try:
            text = b.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise RuntimeError(f"{path.name}: 인코딩을 알 수 없음")
    rows = list(csv.reader(io.StringIO(text)))
    header = [h.strip() for h in rows[0]]
    return header, [r for r in rows[1:] if any(c.strip() for c in r)]


def snapshot_date(name, reg_date):
    m = re.search(r"(\d{8})\s*$", name)
    d = date(int(m.group(1)[:4]), int(m.group(1)[4:6]), int(m.group(1)[6:])) if m else None
    reg = date.fromisoformat(reg_date) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", reg_date or "") else None
    cands = [x for x in (d, reg) if x]
    if not cands:
        raise RuntimeError(f"기준일을 정할 수 없음: {name} / {reg_date}")
    return min(cands)


def to_price(v):
    m = re.search(r"\d[\d,]*", v or "")
    if not m:
        return None
    n = int(m.group(0).replace(",", ""))
    return n if 0 < n < 10_000_000 else None


def parse(header, rows):
    """→ [(item_seq, sido, sigungu, biz, store, addr, payload, [(menu_no, menu, price)])] 또는 None(업소 목록 아님)"""
    idx = {}
    for key, names in ALIASES.items():
        hit = [i for i, h in enumerate(header) if h in names]
        if not hit:
            return None
        idx[key] = hit[0]
    menu_cols = []
    for n in range(1, 5):
        if f"메뉴{n}" in header:
            menu_cols.append((n, header.index(f"메뉴{n}"), header.index(f"가격{n}") if f"가격{n}" in header else None))
    if not menu_cols and "대표품목" in header:
        menu_cols.append((1, header.index("대표품목"), header.index("가격") if "가격" in header else None))
    out = []
    for seq, r in enumerate(rows, 1):
        r = r + [""] * (len(header) - len(r))
        cell = lambda k: r[idx[k]].strip() or None
        payload = {h: r[i].strip() for i, h in enumerate(header) if h and h not in PRIVATE and r[i].strip()}
        menus = []
        for n, mi, pi in menu_cols:
            name = r[mi].strip()
            if name:
                menus.append((n, name, to_price(r[pi]) if pi is not None else None))
        out.append((seq, cell("sido"), cell("sigungu"), cell("biz"), cell("store"), cell("addr"), payload, menus))
    return out


def is_dining(biz):
    b = (biz or "").replace(" ", "")
    return "비요식" not in b and any(w in b for w in DINING_WORDS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--latest-only", action="store_true", help="최신 스냅샷만 적재")
    a = ap.parse_args()

    if not a.no_download:
        subprocess.run([sys.executable, str(Path(__file__).with_name("datago_periodic.py")), PK, "--out", str(OUT)],
                       check=True)
    manifest = OUT / "manifest.csv"
    if not manifest.exists():
        sys.exit(f"{manifest}가 없습니다. --no-download 없이 실행하세요.")
    files = []
    for m in csv.DictReader(manifest.open(encoding="utf-8")):
        reg = date.today().isoformat() if m["reg_date"] == "current" else m["reg_date"]
        files.append((snapshot_date(m["name"], reg), m["name"], OUT / "raw" / m["file"]))
    files.sort()
    if a.latest_only:
        files = files[-1:]

    common.load_env()
    conn = common.connect()
    loaded = {}
    for snap, name, path in files:
        header, rows = read_csv(path)
        parsed = parse(header, rows)
        if parsed is None:
            print(f"  [건너뜀] {snap} {name}: 업소 목록이 아님 (헤더 {header[:6]})")
            continue
        if snap in loaded:
            print(f"  [주의] 기준일 {snap}이 겹침: {loaded[snap]} / {name} → 나중 파일로 덮어씀", file=sys.stderr)
        loaded[snap] = name
        stores = [(snap, seq, sd, sg, biz, is_dining(biz), st, ad, json.dumps(p, ensure_ascii=False))
                  for seq, sd, sg, biz, st, ad, p, _ in parsed]
        menus = [(snap, seq, n, mn, pr) for seq, *_, ms in parsed for n, mn, pr in ms]
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM raw.good_price_store WHERE snapshot = %s", (snap,))   # 메뉴는 CASCADE
            psycopg2.extras.execute_values(cur, """INSERT INTO raw.good_price_store
                (snapshot, item_seq, sido_nm, sigungu_nm, biz_type, is_dining, store_nm, address, payload)
                VALUES %s""", stores, template="(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)", page_size=2000)
            psycopg2.extras.execute_values(cur, """INSERT INTO raw.good_price_menu
                (snapshot, item_seq, menu_no, menu_nm, price) VALUES %s""", menus, page_size=5000)
        n_din = sum(s[5] for s in stores)
        print(f"  {snap} {name}: 업소 {len(stores)} (외식업 {n_din}), 메뉴 {len(menus)}")

    with conn, conn.cursor() as cur:
        cur.execute("""SELECT biz_type, count(*) FROM raw.good_price_store
                       WHERE snapshot = (SELECT max(snapshot) FROM raw.good_price_store)
                       GROUP BY 1 ORDER BY 2 DESC""")
        print("최신 스냅샷 업종:", ", ".join(f"{b} {n}" for b, n in cur.fetchall()))
    conn.close()


if __name__ == "__main__":
    main()
