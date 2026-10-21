"""
행정안전부 지방물가정보 — 개인서비스(외식비) 가격 수집기  → raw.mois_dining_price

  화면: https://www.mois.go.kr/frt/sub/a02/lpid020101/screen.do
        (iframe https://hamoni.mois.go.kr/portal/lcpr/indvSrcvEatoutCstList.do)
  원자료: 국가데이터처 소비자물가조사 조사 가격. 참가격 '외식비'도 같은 자료다.
  [출처 표시] meta.data_source 'mois_dining' (이용허락 조건 미확인 → 표시하는 것으로 둔다)

  - 시도 16곳(세종은 충남에 포함) × 9품목, 월간. 2011-09부터 있다. 인증키 필요 없음.
  - 화면과 같은 내부 경로(POST getIndvSrcvEatoutCstList.do)를 쓴다. 한 번에 최대 12개월.
    포털이 개편되면 깨질 수 있다.

사용법:
    python mois_dining.py                       # 최근 12개월 (늦게 고쳐지는 값까지 다시 받음, 참가격 대조 포함 약 1분)
    python mois_dining.py --from 201109         # 처음부터 전부 (하모니 약 140회 + 참가격 약 150회 요청)
    python mois_dining.py --from 202501 --to 202512

같은 (연월, 시도, 품목)은 덮어쓴다 → 여러 번 실행해도 결과가 같다.

원천에서 바로잡는 것 (아래 REMAP, fetch 참고)
  - 2014-07까지 짜장면·삼계탕·칼국수 값이 서로 다른 코드에 들어 있음 → 실제 품목으로 바꿔 저장
  - 2012-12은 전 품목 0 → 저장하지 않음 (결측)
  - 2018-03~2020-01에 같은 시도·품목 행이 두 번 오고 값이 다를 때가 있음 (첫 행이 틀리기도 함),
    2023-10 대구·대전·부산 '삼겹살 환산 전' 칸에 '환산 후' 값이 들어 있음 등
    → 참가격 외식비 표(같은 행안부 자료, 2014-07~)와 달마다 대조한다.
      · 엇갈리는 중복 행: 참가격 값과 같은 후보를 쓴다
      · 값이 하나인데 참가격과 다름: 대부분 가격 변동 달이 한 달 어긋난 작은 차이라 하모니 값 유지.
        하모니 값만 앞뒤 달 모두와 15% 넘게 튀고 참가격 값은 이어지면 참가격 값으로 바꾼다
      바꾼 칸은 price_src = 'tprice'. 2014-06 이전은 대조할 원천이 없어 하모니 값 그대로.
    참가격은 빠르게 연달아 부르면 연결을 끊는다 → 달마다 3초 간격 (전체 백필은 10분 남짓)
  - 김밥은 2016-12까지 1인분, 2017-01부터 1줄 (값이 약 40% 떨어짐) — 그대로 두고 집계할 때 주의
"""
import argparse
import html
import json
import re
import sys
import time
from collections import defaultdict
from datetime import date

import psycopg2.extras
import requests

import molit_rent as common  # .env 읽기, DB 연결

URL = "https://hamoni.mois.go.kr/portal/lcpr/getIndvSrcvEatoutCstList.do"
# 같은 자료의 참가격 화면 (2014-07부터). 하모니 중복 행이 엇갈릴 때만 쓴다.
TPRICE_URL = "https://www.price.go.kr/tprice/portal/servicepriceinfo/dineoutprice/dineOutPriceList.do"
TPRICE_COLS = ["BA", "BB", "BC", "BD", "BE", "BF", "BG", "BH", "BI"]   # 참가격 표의 열 순서
TPRICE_FIRST_YM = "201407"    # 참가격 외식비 표에 값이 있는 첫 달
OUTLIER = 0.15                # 하모니 값이 앞뒤 달 모두와 이만큼 넘게 다르면 참가격 값으로 바꾼다
FIRST_YM = "201109"
# 하모니 품목 코드 (화면 체크박스 순서). 응답에는 코드가 없어서 품목별로 따로 요청한다.
ITEMS = {
    "BA": "냉면", "BB": "비빔밥", "BC": "김치찌개 백반", "BD": "삼겹살 환산 전", "BE": "삼겹살 환산 후",
    "BF": "짜장면", "BG": "삼계탕", "BH": "칼국수", "BI": "김밥",
}
# 원천 오류: 2014-07까지는 BF·BG·BH 코드에 칼국수·짜장면·삼계탕 값이 들어 있다 (이름표는 코드대로 나옴).
# 2014-07 → 2014-08 시도 평균이 BF 5,843 → BH 5,849, BG 4,277 → BF 4,284, BH 11,873 → BG 11,887로 이어진다.
# 그 이전 달은 '요청 코드 → 실제 품목 코드'로 바꿔 저장한다.
REMAP_BEFORE = "201408"
REMAP = {"BF": "BH", "BG": "BF", "BH": "BG"}
# 하모니 시도 코드 → 짧은 시도 이름 (dim.region_xwalk의 source_key).
# 광주·전남은 2026-07부터 '전남광주(광주)'·'전남광주(전남)'로 표기되지만 코드는 그대로다.
CTPV = {
    "6110000": "서울", "6260000": "부산", "6270000": "대구", "6280000": "인천", "6290000": "광주",
    "6300000": "대전", "6310000": "울산", "6320000": "세종", "6410000": "경기", "6420000": "강원",
    "6430000": "충북", "6440000": "충남", "6450000": "전북", "6460000": "전남", "6470000": "경북",
    "6480000": "경남", "6490000": "제주",
}


def months_back(ym, n):
    y, m = int(ym[:4]), int(ym[4:])
    m -= n
    while m <= 0:
        y, m = y - 1, m + 12
    return f"{y}{m:02d}"


def windows(start, end):
    """[start, end]를 12개월 이하 구간으로 나눈다 (화면 제한: 최대 1년)"""
    y, m = int(start[:4]), int(start[4:])
    while f"{y}{m:02d}" <= end:
        ey, em = y + (m + 10) // 12, (m + 10) % 12 + 1
        e = min(f"{ey}{em:02d}", end)
        yield f"{y}{m:02d}", e
        y, m = int(e[:4]) + int(e[4:]) // 12, int(e[4:]) % 12 + 1


def fetch(s, item_cd, bgn, end):
    r = s.post(URL, timeout=30, data={"menuYn": "", "searchItemNo": item_cd,
                                      "searchBgngYm": bgn, "searchEndYm": end, "searchCtpv": ""})
    r.raise_for_status()
    j = r.json()
    if j.get("result") != "success":
        raise RuntimeError(f"응답 오류: {str(j)[:200]}")
    rows, cols = json.loads(j["indvSrcvEatoutCstList"]), json.loads(j["colNmList"])
    # 원천이 2018-03~2020-01 등에서 같은 시도 행을 두 번 돌려준다. 값이 같으면 하나만 남기고,
    # 다르면 후보를 모두 남겨 main()에서 참가격 값으로 정한다 (첫 행이 맞는다는 보장이 없음).
    out = defaultdict(list)          # (ym, ctpv_no, 실제 품목) → [값 …]
    meta = {}
    for row in rows:
        if row["ctpvNo"] not in CTPV:
            raise RuntimeError(f"모르는 시도 코드 {row['ctpvNo']} {row['ctpvNm']} — CTPV에 추가하세요")
        if row["itemNm"] != ITEMS[item_cd]:
            raise RuntimeError(f"품목 코드 {item_cd}의 이름이 '{row['itemNm']}' — ITEMS 확인 필요")
        for i, col in enumerate(cols):
            v = (row.get(f"col{i}") or "").replace(",", "").strip()
            if not v or float(v) <= 0:      # 2012-12은 전 품목 0 (원천 결측)
                continue
            ym = col.replace(".", "")
            true_cd = REMAP.get(item_cd, item_cd) if ym < REMAP_BEFORE else item_cd
            key = (ym, row["ctpvNo"], true_cd)
            if int(float(v)) not in out[key]:
                out[key].append(int(float(v)))
            meta[row["ctpvNo"]] = row["ctpvNm"]
    return out, meta


def tprice_month(s, ym):
    """참가격 외식비 표 한 달치 → {(ctpv_no, 품목코드): 값}. 같은 행안부 자료를 시도 × 품목 표로 보여 준다.
    빠르게 연달아 부르면 연결을 끊으므로 호출 사이에 몇 초 둔다."""
    r = s.post(TPRICE_URL, timeout=30, data={"searchOrExcel": "", "searchYear": ym[:4],
                                             "searchMonth": ym[4:], "searchArea": ""})
    r.raise_for_status()
    by_name = {v: k for k, v in CTPV.items()}
    out = {}
    for tb in re.findall(r"<tbody[^>]*>(.*?)</tbody>", r.text, re.S):
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tb, re.S):
            cells = [re.sub(r"\s+", "", html.unescape(re.sub("<[^>]+>", "", c)))
                     for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
            if len(cells) != 1 + len(TPRICE_COLS):
                continue
            name = re.sub(r"^전남광주\((.+)\)$", r"\1", cells[0])
            if name not in by_name:
                continue
            for cd, v in zip(TPRICE_COLS, cells[1:]):
                v = v.replace(",", "")
                if v.isdigit() and int(v) > 0:
                    out[(by_name[name], cd)] = int(v)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", help="YYYYMM (기본: 최근 12개월)")
    ap.add_argument("--to", dest="end", default=f"{date.today():%Y%m}")
    ap.add_argument("--sleep", type=float, default=0.5)
    ap.add_argument("--no-verify", dest="verify", action="store_false",
                    help="참가격 대조를 값이 엇갈리는 달로만 줄인다 (기본: 2014-07 이후 모든 달 대조, 달마다 3초)")
    a = ap.parse_args()
    start = max(a.start or months_back(a.end, 11), FIRST_YM)

    common.load_env()
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (eodi-salkka data pipeline)"
    cells, names = {}, {}
    for bgn, end in windows(start, a.end):
        for cd in ITEMS:
            got, meta = fetch(s, cd, bgn, end)
            for k, vals in got.items():
                cells.setdefault(k, [])
                cells[k] += [v for v in vals if v not in cells[k]]
            names.update(meta)
            time.sleep(a.sleep)
        print(f"  {bgn}~{end}: 누적 {len(cells)}칸")
    if not cells:
        sys.exit("받은 값이 없습니다.")

    # 참가격 대조: 참가격에 자료가 있는 달(2014-07~)은 모두, 없으면 값이 엇갈리는 달만
    conflict_months = {k[0] for k, v in cells.items() if len(v) > 1}
    months = {k[0] for k in cells}
    check = sorted(conflict_months | ({ym for ym in months if ym >= TPRICE_FIRST_YM} if a.verify else set()))
    tp = {}
    if check:
        print(f"  참가격 대조 {len(check)}개월 ({check[0]}~{check[-1]}, 값이 엇갈리는 달 {len(conflict_months)}개 포함)")
    for ym in check:
        for attempt in range(3):
            try:
                tp[ym] = tprice_month(s, ym)
                break
            except requests.RequestException as e:
                print(f"  [재시도] 참가격 {ym}: {type(e).__name__}", file=sys.stderr)
                time.sleep(10 * (attempt + 1))
        time.sleep(3)

    def neighbors(ym, ct, cd):
        y, mo = int(ym[:4]), int(ym[4:])
        prev = f"{y - (mo == 1)}{(mo - 2) % 12 + 1:02d}"
        nxt = f"{y + (mo == 12)}{mo % 12 + 1:02d}"
        return [cells[k][0] for k in ((prev, ct, cd), (nxt, ct, cd)) if k in cells and len(cells[k]) == 1]

    def jumps(v, around):   # 이웃 달 모두와 OUTLIER 넘게 차이
        return bool(around) and all(abs(v / n - 1) > OUTLIER for n in around)

    rows, unresolved, fixed, small = [], 0, [], 0
    for (ym, ct, cd), vals in sorted(cells.items()):
        price, src = vals[0], "hamoni"
        ref = tp.get(ym, {}).get((ct, cd))
        if len(vals) > 1:                     # 엇갈리는 중복 행 → 참가격 값으로 고른다
            if ref is not None:
                if ref not in vals:
                    fixed.append(f"{ym} {CTPV[ct]} {ITEMS[cd]}: 후보 {vals}에 없는 참가격 {ref} 사용")
                price, src = ref, "tprice"
            else:
                src, unresolved = "hamoni_first", unresolved + 1
        elif ref is not None and ref != price:
            # 대부분은 두 화면이 가격 변동 달을 한 달씩 다르게 둔 작은 차이 → 하모니 유지.
            # 하모니 값만 앞뒤 달과 동떨어지고 참가격 값은 이어질 때만 바꾼다 (예: 2023-10 삼겹살 환산 전)
            around = neighbors(ym, ct, cd)
            if jumps(price, around) and not jumps(ref, around):
                fixed.append(f"{ym} {CTPV[ct]} {ITEMS[cd]}: 하모니 {price} (이웃 {around}) → 참가격 {ref}")
                price, src = ref, "tprice"
            else:
                small += 1
        rows.append((ym, ct, CTPV[ct], names.get(ct), cd, ITEMS[cd], price, src))
    if fixed:
        print(f"  [수정] 참가격 값으로 바꾼 칸 {len(fixed)}개 (중복 행 선택 제외)", file=sys.stderr)
        for f in fixed[:30]:
            print("    " + f, file=sys.stderr)
    if small:
        print(f"  [참고] 참가격과 조금 다른 칸 {small}개는 하모니 값 유지 (변동 시점 한 달 차이 등)")
    if unresolved:
        print(f"  [주의] 참가격으로 못 정한 칸 {unresolved}개 → 첫 값 저장 (price_src = 'hamoni_first')", file=sys.stderr)

    conn = common.connect()
    with conn, conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, """
            INSERT INTO raw.mois_dining_price (ym, ctpv_no, sido, ctpv_nm, item_cd, item_nm, price, price_src)
            VALUES %s
            ON CONFLICT (ym, ctpv_no, item_cd) DO UPDATE SET
                sido = EXCLUDED.sido, ctpv_nm = EXCLUDED.ctpv_nm, item_nm = EXCLUDED.item_nm,
                price = EXCLUDED.price, price_src = EXCLUDED.price_src, fetched_at = now()""",
                                       rows, page_size=2000)
        cur.execute("""SELECT min(ym), max(ym), count(DISTINCT ym), count(DISTINCT ctpv_no), count(*)
                       FROM raw.mois_dining_price""")
        lo, hi, n_ym, n_sido, n = cur.fetchone()
    conn.close()
    print(f"{len(rows)}행 저장 → raw.mois_dining_price 전체 {n}행 ({lo}~{hi}, {n_ym}개월, 시도 {n_sido}곳)")


if __name__ == "__main__":
    main()
