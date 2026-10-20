"""
행정안전부_지방공공요금 현황(3045228) 원본 파일들을 하나로 합친다.

사용법:
    python merge_public_fee.py --src ./data/public_fee

입력: datago_periodic.py가 만든 <src>/manifest.csv + <src>/raw/*.csv|*.zip
출력: <src>/merged/
  - public_fee_long.csv     모든 값 (연월 × 지역 × 항목 1행), UTF-8
  - public_fee_sido_wide.csv 시도 단위 공공요금 표준 항목을 연월 × 시도 1행으로 펼친 표
  - merge_report.txt        양식별 파일 수, 무시한 컬럼, 중복 처리 내역

원본 양식이 시기별로 7가지라 '헤더'를 보고 양식을 판별한다(파일 이름은 틀린 경우가 있음).
"""
import argparse
import collections
import csv
import io
import re
import zipfile
from pathlib import Path

# ── 항목 표준화 ─────────────────────────────────────────────
def _gas(c):
    return c.startswith("도시가스료") and "조사가격" not in c


def _per20(c, prefix):
    if not c.startswith(prefix) or "조사가격" in c:
        return False
    return "20" in c or c == f"{prefix}(가정용)"



# 원본 컬럼명 → 표준 항목 코드. 공백·괄호 차이를 줄이려고 정규화한 이름으로 비교한다.
ITEM_RULES = [
    # (category, item, 조건 함수)
    ("utility", "subway_card", lambda c: c.startswith("전철료") and "카드" in c),
    ("utility", "subway_cash", lambda c: c.startswith("전철료") and "현금" in c),
    ("utility", "bus_card", lambda c: c.startswith("시내버스료") and "카드" in c),
    ("utility", "bus_cash", lambda c: c.startswith("시내버스료") and "현금" in c),
    ("utility", "taxi", lambda c: c.startswith("택시료")),
    # 도시가스: 월 사용량 환산 요금(516MJ ≒ 12㎥)만 쓴다. '조사가격'(1MJ·1㎥ 단가)은 버린다.
    # 최근 양식은 '도매요금', '소매요금'이 도시가스 바로 뒤에 붙은 별도 컬럼이다.
    ("utility", "gas_wholesale", lambda c: c == "도매요금" or (_gas(c) and "도매" in c)),
    ("utility", "gas_retail", lambda c: c == "소매요금" or (_gas(c) and "소매" in c)),
    ("utility", "gas_total", lambda c: _gas(c)),
    # 상·하수도: 20㎥ 사용 기준 월 요금 ('조사가격'은 구간별 단가라 버린다)
    ("utility", "water_20m3", lambda c: _per20(c, "상수도료")),
    ("utility", "sewer_20m3", lambda c: _per20(c, "하수도료")),
    ("utility", "trash_20l", lambda c: c.replace(" ", "").startswith("쓰레기봉투료")),
    # 2016-12 ~ 2017-03 ZIP에만 있는 부록 표
    ("personal_service", "laundry", lambda c: c == "세탁료"),
    ("personal_service", "lodging_inn", lambda c: c.startswith("숙박료")),
    ("personal_service", "barber", lambda c: c == "이용료"),
    ("personal_service", "hair_cut", lambda c: c.startswith("미용료")),
    ("personal_service", "bath", lambda c: c.startswith("목욕료")),
    ("dining", "naengmyeon", lambda c: c == "냉면"),
    ("dining", "bibimbap", lambda c: c == "비빔밥"),
    ("dining", "kimchi_stew_set", lambda c: c.replace(" ", "") == "김치찌개백반"),
    ("dining", "samgyeopsal", lambda c: c == "삼겹살(외식)"),
    ("dining", "samgyeopsal_200g", lambda c: c == "삼겹살(외식)환산"),
    ("dining", "jajangmyeon", lambda c: c == "자장면"),
    ("dining", "samgyetang", lambda c: c == "삼계탕"),
    ("dining", "kalguksu", lambda c: c == "칼국수"),
    ("dining", "gimbap", lambda c: c == "김밥"),
]
KEY_COLS = {"연번", "시도", "시도코드", "년월", "구분", "지자체명", "공란", ""}
UTILITY_ITEMS = [i for cat, i, _ in ITEM_RULES if cat == "utility"]

# ── 지역명 표준화 ──────────────────────────────────────────
SIDO_SHORT = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원도": "강원", "강원특별자치도": "강원", "충청북도": "충북",
    "충청남도": "충남", "전라북도": "전북", "전북특별자치도": "전북", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주", "제주도": "제주",
}
SIDO_ALIASES = {"전남광주(광주)": "광주", "전남광주(전남)": "전남"}  # 2026-07부터 통합 표기
SHORT_NAMES = set(SIDO_SHORT.values())
STAT_ROWS = {"평균", "전국", "전국평균", "표준편차", "최대값", "최소값", "최대", "최소", "합계", "계"}


def norm_col(c):
    return re.sub(r"\s+", " ", c.replace("﻿", "")).strip()


def classify(col):
    c = norm_col(col)
    for cat, item, rule in ITEM_RULES:
        if rule(c):
            return cat, item
    return None


def norm_sido(name):
    n = name.strip()
    if n in SIDO_ALIASES:
        return SIDO_ALIASES[n]
    if n in SHORT_NAMES:
        return n
    return SIDO_SHORT.get(n)


def parse_num(v):
    v = (v or "").replace(",", "").strip()
    if v in ("", "-", "–", "."):
        return None
    try:
        x = float(v)
    except ValueError:
        return None
    return int(x) if x == int(x) else round(x, 4)


def decode(b):
    for enc in ("utf-8-sig", "cp949"):
        try:
            return b.decode(enc), enc
        except UnicodeDecodeError:
            pass
    return b.decode("cp949", "replace"), "cp949(손상)"


def ym_from_text(*texts):
    """'2020년6월', '2013년 10월', '(2022-05)', '20260930' 같은 문자열에서 YYYY-MM을 뽑는다"""
    for t in texts:
        if not t:
            continue
        m = re.search(r"(20\d{2})\s*년\s*(\d{1,2})\s*월", t) or re.search(r"(20\d{2})-(\d{2})", t) \
            or re.search(r"(20\d{2})(\d{2})\d{2}(?!\d)", t)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}"
    return None


def zip_name(info):
    """ZIP 안 한글 파일명. UTF-8 표시가 없으면 zipfile이 cp437로 읽어 깨지므로 cp949로 되돌린다.
    (파이썬 버전에 따라 이미 제대로 읽힌 경우도 있어서, 되돌릴 수 없으면 그대로 쓴다)"""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp949", "replace")
    except UnicodeEncodeError:
        return info.filename


def iter_sources(src):
    """(manifest 행, 파일 안 이름, bytes)를 차례로 돌려준다. ZIP은 풀어서 하나씩."""
    with (src / "manifest.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            p = src / "raw" / r["file"]
            if not p.is_file() or p.stat().st_size == 0:
                yield r, r["file"], None
                continue
            if p.suffix == ".zip":
                with zipfile.ZipFile(p) as z:
                    for i in z.infolist():
                        if not i.is_dir():
                            yield r, f"{r['file']}!{zip_name(i)}", z.read(i)
            else:
                yield r, r["file"], p.read_bytes()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="./data/public_fee")
    a = ap.parse_args()
    src = Path(a.src)
    out = src / "merged"
    out.mkdir(exist_ok=True)

    report = collections.defaultdict(list)
    ignored_cols = collections.Counter()
    layouts = collections.Counter()
    # (ym, level, sido, sigungu, item) → record. 같은 키가 또 나오면 등록일이 최근인 쪽을 남긴다.
    best = {}
    dupes = 0

    for m, fname, data in iter_sources(src):
        if data is None:
            report["빈 파일"].append(fname)
            continue
        text, enc = decode(data)
        rows = [r for r in csv.reader(io.StringIO(text)) if any(x.strip() for x in r)]
        if not rows:
            report["내용 없음"].append(fname)
            continue
        header = [norm_col(h) for h in rows[0]]
        level = "sigungu" if "지자체명" in header else "sido"
        name_col = next((h for h in ("시도", "구분", "지자체명") if h in header), None)
        if name_col is None:
            report["지역 컬럼 없음"].append(f"{fname} {header[:5]}")
            continue
        layouts[(level, name_col, "년월" in header, len(header))] += 1
        mapped = {}
        for idx, h in enumerate(header):
            if h in KEY_COLS:
                continue
            c = classify(h)
            if c:
                mapped[idx] = c
            else:
                ignored_cols[h] += 1
        file_ym = ym_from_text(fname.split("!")[-1], m["name"])
        reg = m["reg_date"] if m["reg_date"] != "current" else "9999-99-99"

        for r in rows[1:]:
            r = r + [""] * (len(header) - len(r))
            raw_name = r[header.index(name_col)].strip()
            if raw_name.replace(" ", "") in STAT_ROWS:
                continue
            if level == "sigungu":
                parts = raw_name.split()
                sido = norm_sido(parts[0]) if parts else None
                sigungu = " ".join(parts[1:])
                if not sigungu:  # 세종처럼 시도 = 시군구
                    sigungu = parts[0] if parts else ""
            else:
                sido, sigungu = norm_sido(raw_name), ""
            if not sido:
                report["알 수 없는 지역명"].append(f"{fname}: {raw_name}")
                continue
            ym = ym_from_text(r[header.index("년월")]) if "년월" in header else None
            ym = ym or file_ym
            if not ym:
                report["연월을 알 수 없음"].append(fname)
                break
            for idx, (cat, item) in mapped.items():
                val = parse_num(r[idx])
                if val is None or (val == 0 and item.startswith("subway")):
                    continue  # 2021년 양식은 전철 없는 시도를 0으로 적었다
                key = (ym, level, sido, sigungu, item)
                rec = {"ym": ym, "level": level, "sido": sido, "sigungu": sigungu,
                       "category": cat, "item": item, "value": val, "raw_column": header[idx],
                       "source_name": m["name"], "source_file": fname, "reg_date": m["reg_date"],
                       "_reg": reg}
                old = best.get(key)
                if old:
                    dupes += 1
                    if old["value"] != val:
                        report["중복(값 다름) — 최근 등록본 채택"].append(
                            f"{key}: {old['value']}({old['reg_date']}) vs {val}({m['reg_date']})")
                    if old["_reg"] >= reg:
                        continue
                best[key] = rec

    recs = sorted(best.values(), key=lambda x: (x["ym"], x["level"], x["sido"], x["sigungu"], x["item"]))
    fields = ["ym", "level", "sido", "sigungu", "category", "item", "value", "raw_column",
              "source_name", "source_file", "reg_date"]
    with (out / "public_fee_long.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(recs)

    wide = collections.defaultdict(dict)
    for x in recs:
        if x["level"] == "sido" and x["category"] == "utility":
            wide[(x["ym"], x["sido"])][x["item"]] = x["value"]
    with (out / "public_fee_sido_wide.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["ym", "sido"] + UTILITY_ITEMS)
        for (ym, sido), v in sorted(wide.items()):
            w.writerow([ym, sido] + [v.get(i, "") for i in UTILITY_ITEMS])

    months = sorted({x["ym"] for x in recs if x["level"] == "sido"})
    all_months = []
    if months:
        y, mo = map(int, months[0].split("-"))
        while f"{y}-{mo:02d}" <= months[-1]:
            all_months.append(f"{y}-{mo:02d}")
            y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
    missing = [x for x in all_months if x not in set(months)]

    with (out / "merge_report.txt").open("w", encoding="utf-8") as fh:
        fh.write(f"총 {len(recs)}행 (중복 키 {dupes}건 정리)\n")
        for lvl in ("sido", "sigungu"):
            ms = sorted({x["ym"] for x in recs if x["level"] == lvl})
            if ms:
                fh.write(f"{lvl}: {len(ms)}개월 ({ms[0]} ~ {ms[-1]}) {', '.join(ms) if lvl == 'sigungu' else ''}\n")
        fh.write(f"시도 단위 빠진 달 {len(missing)}개: {', '.join(missing)}\n\n")
        fh.write("양식(level, 지역컬럼, 년월컬럼 유무, 컬럼 수) → 파일 수\n")
        for k, v in layouts.most_common():
            fh.write(f"  {k}: {v}\n")
        fh.write("\n표준 항목으로 매핑하지 않은 컬럼 → 등장 파일 수\n")
        for k, v in ignored_cols.most_common():
            fh.write(f"  {k}: {v}\n")
        for k, v in report.items():
            fh.write(f"\n[{k}] {len(v)}건\n")
            for x in v[:200]:
                fh.write(f"  {x}\n")
    print(f"완료: {len(recs)}행 → {out}")
    print(f"시도 단위 {len(months)}개월, 빠진 달 {len(missing)}개 / 문제 항목: " +
          (", ".join(f"{k} {len(v)}건" for k, v in report.items()) or "없음"))


if __name__ == "__main__":
    main()
