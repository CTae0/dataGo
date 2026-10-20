"""
전국 시군구 기준(dim.region)을 법정동 코드로 채운다.

원천: 국토교통부_전국 법정동 (data.go.kr 15063424, 연 1회 갱신, 이용허락 제한 없음)
     현재 존재하는 코드만 있고 폐지 이력은 없다 → 옛 코드는 아래 KNOWN_CHANGES로 dim.region_code_history에 넣는다.

사용법 (프로젝트 루트에서):
    python -m pipeline.dim_region                 # 최신 파일을 받아서 적재, 전국 leaf를 수집 대상으로
    python -m pipeline.dim_region --file data/legal_dong/raw/xxx.csv
    python -m pipeline.dim_region --scope gangwon # 수집 대상을 강원만 (시험용)
"""
import argparse
import csv
from pathlib import Path

import psycopg2.extras

import datago_periodic
import molit_rent as common

DATASET_PK = "15063424"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "legal_dong" / "raw"

SIDO_SHORT = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주",
    "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기",
    "강원특별자치도": "강원", "강원도": "강원", "충청북도": "충북", "충청남도": "충남",
    "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남", "경상북도": "경북", "경상남도": "경남",
    "제주특별자치도": "제주", "전남광주통합특별시": "전남광주",
}

# 시도 개편으로 코드가 통째로 바뀐 경우: (새 시도코드, 옛 시도코드, 날짜, 옛 시도 짧은 이름) — 뒷 3자리는 그대로
PREFIX_CHANGES = [("51", "42", "2023-06-11", "강원"), ("52", "45", "2024-01-18", "전북")]
# 개별 변경: 새 코드 → [(옛 코드, 날짜, 옛 시도, 메모)]
OLD_GWANGJU = {"동구": "29110", "서구": "29140", "남구": "29155", "북구": "29170", "광산구": "29200"}
OLD_JEONNAM = {
    "목포시": "46110", "여수시": "46130", "순천시": "46150", "나주시": "46170", "광양시": "46230",
    "담양군": "46710", "곡성군": "46720", "구례군": "46730", "고흥군": "46770", "보성군": "46780",
    "화순군": "46790", "장흥군": "46800", "강진군": "46810", "해남군": "46820", "영암군": "46830",
    "무안군": "46840", "함평군": "46860", "영광군": "46870", "장성군": "46880", "완도군": "46890",
    "진도군": "46900", "신안군": "46910",
}
SINGLE_CHANGES = {
    "27720": [("47720", "2023-07-01", "경북", "군위군 경북→대구 편입")],
    # 인천 2026-06-30 개편: 중구·동구 → 제물포구·영종구, 서구 → 서해구·검단구
    "28125": [("28110", "2026-06-30", "인천", "중구(내륙)→제물포구"), ("28140", "2026-06-30", "인천", "동구→제물포구")],
    "28155": [("28110", "2026-06-30", "인천", "중구(영종)→영종구")],
    "28275": [("28260", "2026-06-30", "인천", "서구→서해구")],
    "28290": [("28260", "2026-06-30", "인천", "서구(검단)→검단구")],
}


def latest_file(download):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if download:
        s = datago_periodic.make_session()
        key, title = datago_periodic.get_current_key(s, DATASET_PK)
        dest = datago_periodic.download(s, DATASET_PK, key, "1", RAW_DIR / "latest")
        print(f"받음: {title} → {dest.name}")
        return dest
    files = sorted(RAW_DIR.glob("*.csv"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise SystemExit("법정동 파일이 없습니다. --download로 받으세요.")
    return files[-1]


def build(path):
    with open(path, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    sido_names = {r["법정동코드"][:2]: r["시도명"] for r in rows if r["법정동코드"][2:] == "00000000"}
    sg = {r["법정동코드"][:5]: r for r in rows
          if r["법정동코드"][5:] == "00000" and r["시군구명"] and not r["읍면동명"]}

    regions = {}
    for code, r in sg.items():
        raw = r["시군구명"]
        parent = code[:4] + "0"
        is_gu = code[4] != "0" and parent in sg and raw.startswith(sg[parent]["시군구명"])
        has_gu = any(c != code and c[:4] == code[:4] and c[4] != "0" and sg[c]["시군구명"].startswith(raw)
                     for c in sg) if code[4] == "0" else False
        if is_gu:
            pname = sg[parent]["시군구명"]
            level, name, stype, pcode = "gu", f"{pname} {raw[len(pname):]}", "구", parent
        elif has_gu:
            level, name, stype, pcode = "si", raw, "시", None
        else:
            level, name, stype, pcode = "sigungu", raw, raw[-1], None
        sido_full = sido_names.get(code[:2], r["시도명"])
        regions[code] = {
            "region_code": code, "sido_code": code[:2], "sido": SIDO_SHORT.get(sido_full, sido_full),
            "sido_full": sido_full, "sigungu": name, "sigungu_raw": raw, "sigungu_type": stype,
            "level": level, "parent_code": pcode, "is_leaf": level != "si",
            "created_on": r["생성일자"] or None, "legacy_code": None, "code_changed_on": None,
        }

    history = []
    for code, g in regions.items():
        for new_p, old_p, day, old_sido in PREFIX_CHANGES:
            if code.startswith(new_p):
                history.append((old_p + code[2:], code, day, old_sido, f"{old_sido} 시도코드 {old_p}→{new_p}"))
        if g["sido"] == "전남광주":
            short = g["sigungu_raw"]
            # 시·군 이름은 전남, 자치구(동구·서구·남구·북구·광산구)는 광주
            if short in OLD_GWANGJU and g["sigungu_type"] == "구":
                history.append((OLD_GWANGJU[short], code, g["created_on"], "광주", "광주광역시→전남광주통합특별시"))
            elif short in OLD_JEONNAM:
                history.append((OLD_JEONNAM[short], code, g["created_on"], "전남", "전라남도→전남광주통합특별시"))
        for old, day, old_sido, note in SINGLE_CHANGES.get(code, []):
            history.append((old, code, day, old_sido, note))
    for old, code, day, _, _ in history:
        regions[code]["legacy_code"], regions[code]["code_changed_on"] = old, day
    return regions, history


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--download", action="store_true", help="포털에서 최신 파일을 받는다 (없으면 마지막 받은 파일)")
    ap.add_argument("--scope", choices=["all", "gangwon"], default="all")
    a = ap.parse_args()
    common.load_env()
    path = Path(a.file) if a.file else latest_file(a.download or not any(RAW_DIR.glob("*.csv")))
    regions, history = build(path)
    for g in regions.values():
        g["in_scope"] = g["is_leaf"] and (a.scope == "all" or g["sido"] == "강원")

    cols = ["region_code", "sido_code", "sido", "sido_full", "sigungu", "sigungu_raw", "sigungu_type", "level",
            "parent_code", "is_leaf", "legacy_code", "code_changed_on", "created_on", "in_scope"]
    conn = common.connect()
    with conn, conn.cursor() as cur:
        cur.execute("TRUNCATE dim.region")
        psycopg2.extras.execute_values(cur, f"INSERT INTO dim.region ({', '.join(cols)}) VALUES %s",
                                       [tuple(g[c] for c in cols) for g in regions.values()])
        cur.execute("TRUNCATE dim.region_code_history")
        psycopg2.extras.execute_values(cur, """INSERT INTO dim.region_code_history
            (old_code, region_code, changed_on, old_sido, note) VALUES %s""", history)
    conn.close()
    lv = {k: sum(g["level"] == k for g in regions.values()) for k in ("sigungu", "gu", "si")}
    print(f"dim.region {len(regions)}행 (자치구·시·군 {lv['sigungu']}, 일반구 {lv['gu']}, 구를 둔 시 {lv['si']}), "
          f"수집 대상 {sum(g['in_scope'] for g in regions.values())}곳, 옛 코드 이력 {len(history)}건 ← {path.name}")


if __name__ == "__main__":
    main()
