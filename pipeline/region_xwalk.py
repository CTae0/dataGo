"""
원천별 지역 키를 dim.region leaf(수집·지도 단위)에 매핑한다 → dim.region_xwalk

사용법: python -m pipeline.region_xwalk      (dim.region과 각 raw 테이블이 채워진 뒤)

원천별 키
  kca_store       raw.kca_code(AR) 시군구 코드         예: '수원시  장안', '천안', '(구)광주광역시 > 동구'
  std_trash       raw.std_trash_bag_price 시도명|시군구명  예: '경기도|수원시' → 수원 일반구 4곳 (si)
  std_water       raw.std_water_sewage_fee 기관명        예: '대구광역시' → 대구 전체 (sido)
  mois_public_fee raw.mois_public_fee 시도 짧은 이름      예: '광주' → 통합 전 광주 자치구 5곳 (sido_part)
  mois_public_fee_sigungu  2013·2016 시군구 값         예: '강원|춘천시'
  mois_dining     raw.mois_dining_price 시도 짧은 이름    예: '충남' → 충남 + 세종 (세종은 충남 값에 포함)
  good_price      raw.good_price_store 시도|시군 (모든 스냅샷)  예: '서울특별시|강남구', '서울|강남구'
국토부 전월세는 LAWD_CD = region_code라서 매핑이 필요 없다.
"""
import re
from collections import defaultdict

import psycopg2.extras

import molit_rent as common

# 시도 이름(현재·옛·짧은) → 현재 시도코드
SIDO_CODE = {
    "서울": "11", "서울특별시": "11", "부산": "26", "부산광역시": "26", "대구": "27", "대구광역시": "27",
    "인천": "28", "인천광역시": "28", "대전": "30", "대전광역시": "30", "울산": "31", "울산광역시": "31",
    "세종": "36", "세종특별자치시": "36", "경기": "41", "경기도": "41", "충북": "43", "충청북도": "43",
    "충남": "44", "충청남도": "44", "경북": "47", "경상북도": "47", "경남": "48", "경상남도": "48",
    "제주": "50", "제주특별자치도": "50", "제주도": "50", "강원": "51", "강원도": "51", "강원특별자치도": "51",
    "전북": "52", "전라북도": "52", "전북특별자치도": "52",
    "광주": "12", "광주광역시": "12", "(구)광주광역시": "12", "전남": "12", "전라남도": "12", "(구)전라남도": "12",
    "전남광주": "12", "전남광주통합특별시": "12",
    # 원천 표기 오타 (착한가격업소)
    "광주광역시광역시": "12", "서울특별시시": "11", "세종시": "36",
}
# 통합 전 시도 이름 → dim.region_code_history.old_sido (sido_part 매핑용)
LEGACY_PART = {"광주": "광주", "광주광역시": "광주", "(구)광주광역시": "광주",
               "전남": "전남", "전라남도": "전남", "(구)전라남도": "전남"}
# 없어지거나 쪼개진 옛 이름 → 지금 leaf들 [(시도코드, 법정동 시군구명)]. 모두 granularity 'legacy'
SIGUNGU_ALIAS = {
    ("12", "여천시"): [("12", "여수시")], ("12", "여천군"): [("12", "여수시")],
    ("41", "양주군"): [("41", "양주시")], ("41", "여주군"): [("41", "여주시")],
    ("41", "고양시일산"): [("41", "고양시일산동구"), ("41", "고양시일산서구")],
    ("48", "양산군"): [("48", "양산시")], ("48", "진해시"): [("48", "창원시진해구")],
    ("48", "마산시"): [("48", "창원시마산합포구"), ("48", "창원시마산회원구")],
    ("48", "마산시회원구"): [("48", "창원시마산회원구")], ("48", "마산시합포구"): [("48", "창원시마산합포구")],
    ("47", "봉화군봉화"): [("47", "봉화군")], ("47", "경주시북구"): [("47", "경주시")],
    ("47", "군위군"): [("27", "군위군")], ("44", "연기"): [("36", "세종시")], ("44", "연기군"): [("36", "세종시")],
    ("43", "청원군"): [("43", "청주시상당구"), ("43", "청주시서원구"), ("43", "청주시흥덕구"), ("43", "청주시청원구")],
    ("50", "북제주군"): [("50", "제주시")], ("50", "남제주군"): [("50", "서귀포시")],
    ("36", "세종특별자치시"): [("36", "세종시")],
    ("28", "남구"): [("28", "미추홀구")],
    ("44", "게룡시"): [("44", "계룡시")],   # 착한가격업소 오타
    ("28", "중구"): [("28", "제물포구"), ("28", "영종구")], ("28", "동구"): [("28", "제물포구")],
    ("28", "서구"): [("28", "서해구"), ("28", "검단구")],
}
SIDO_LEVEL_WORDS = {"없음", "전체", ""}   # 시군구 자리에 이게 있으면 시도 단위 값
SKIP_WORDS = {"평균", "합계", "계"}


def norm(s):
    s = re.sub(r"\s+|\(구\)", "", s or "")
    return re.sub(r"(구|시|군)청$", r"\1", s)    # '북구청' → '북구'


class Matcher:
    def __init__(self, cur):
        cur.execute("""SELECT region_code, sido_code, sigungu_raw, level, parent_code, is_leaf FROM dim.region""")
        self.rows = [dict(zip(("code", "sido", "raw", "level", "parent", "leaf"), r)) for r in cur.fetchall()]
        self.leaves_of = defaultdict(list)          # si 코드 → 일반구 leaf
        for r in self.rows:
            if r["parent"]:
                self.leaves_of[r["parent"]].append(r["code"])
        cur.execute("SELECT old_sido, region_code FROM dim.region_code_history WHERE old_sido IN ('광주', '전남')")
        self.legacy = defaultdict(list)
        for old_sido, code in cur.fetchall():
            self.legacy[old_sido].append(code)

    def sido_leaves(self, sido_name):
        """시도 이름 → (leaf 목록, granularity)"""
        if sido_name in LEGACY_PART:
            return self.legacy[LEGACY_PART[sido_name]], "sido_part"
        sc = SIDO_CODE.get(sido_name)
        return ([r["code"] for r in self.rows if r["sido"] == sc and r["leaf"]], "sido") if sc else ([], None)

    def sigungu(self, sido_name, name):
        """시도 + 시군구 이름 → (leaf 목록, granularity, method)"""
        sc = SIDO_CODE.get(sido_name)
        if not sc:
            return [], None, "unknown sido"
        n = norm(name)
        if n in SIDO_LEVEL_WORDS or n == norm(sido_name):
            leaves, gran = self.sido_leaves(sido_name)
            return leaves, gran, "rule"
        if (sc, n) in SIGUNGU_ALIAS:
            leaves = []
            for tsc, tname in SIGUNGU_ALIAS[(sc, n)]:
                got, _, _ = self._exact(tsc, tname)
                leaves += got
            return (leaves, "legacy", "alias") if leaves else ([], None, "alias target missing")
        leaves, gran, method = self._exact(sc, n)
        if leaves or not method.startswith("no match"):
            return leaves, gran, method
        # 잘린 이름 ('해운' → 해운대구): 앞부분이 한 곳만 맞으면 채택
        hit = [r for r in self.rows if r["sido"] == sc and norm(r["raw"]).startswith(n) and r["level"] != "gu"]
        if len(hit) == 1:
            return self._expand(hit[0], "prefix")
        return [], None, "no match"

    def _expand(self, r, method):
        if r["level"] == "si":
            return self.leaves_of[r["code"]], "si", method
        return [r["code"]], "exact", method

    def _exact(self, sc, n):
        cands = [r for r in self.rows if r["sido"] == sc]
        for suffix in ("", "구", "시", "군"):
            hit = [r for r in cands if norm(r["raw"]) == n + suffix]
            if len(hit) == 1:
                return self._expand(hit[0], "name")
            if len(hit) > 1:
                return [], None, f"ambiguous: {[h['code'] for h in hit]}"
        return [], None, "no match"


def collect(cur):
    """(source_id, source_key, label, kind, sido, sigungu) 목록. kind = 'sido' | 'sigungu'"""
    keys = []
    cur.execute("""SELECT c.code, p.code_name, c.code_name FROM raw.kca_code c
                   JOIN raw.kca_code p ON p.class_code = 'AR' AND p.code = c.high_code
                   WHERE c.class_code = 'AR' AND p.high_code = '020000000'""")
    keys += [("kca_store", code, f"{sd} {sg}", "sigungu", sd, sg) for code, sd, sg in cur.fetchall()]
    cur.execute("SELECT DISTINCT sido_nm, sigungu_nm FROM raw.std_trash_bag_price")
    keys += [("std_trash", f"{sd}|{sg}", f"{sd} {sg}", "sigungu", sd, sg) for sd, sg in cur.fetchall()]
    cur.execute("SELECT DISTINCT instt_nm FROM raw.std_water_sewage_fee")
    for (nm,) in cur.fetchall():
        parts = nm.split()
        if len(parts) == 1 or parts[1].endswith(("사업본부", "사업소")):
            keys.append(("std_water", nm, nm, "sido", parts[0], None))
        else:
            keys.append(("std_water", nm, nm, "sigungu", parts[0], " ".join(parts[1:])))
    cur.execute("SELECT DISTINCT sido FROM raw.mois_public_fee WHERE level = 'sido'")
    keys += [("mois_public_fee", sd, sd, "sido", sd, None) for (sd,) in cur.fetchall()]
    cur.execute("SELECT DISTINCT sido, sigungu FROM raw.mois_public_fee WHERE level = 'sigungu'")
    keys += [("mois_public_fee_sigungu", f"{sd}|{sg}", f"{sd} {sg}", "sigungu", sd, sg) for sd, sg in cur.fetchall()]
    cur.execute("SELECT DISTINCT sido FROM raw.mois_dining_price")
    for (sd,) in cur.fetchall():
        keys.append(("mois_dining", sd, sd, "sido", sd, None))
        if sd == "충남":   # 기관 주석: 세종의 가격정보는 충남에 포함 → 같은 키를 세종에도 연결
            keys.append(("mois_dining", sd, "충남(세종 포함)", "sido", "세종", None))
    cur.execute("SELECT DISTINCT sido_nm, sigungu_nm FROM raw.good_price_store WHERE sido_nm IS NOT NULL")
    keys += [("good_price", f"{sd}|{sg or ''}", f"{sd} {sg or ''}".strip(), "sigungu", sd, sg or "")
             for sd, sg in cur.fetchall()]
    return keys


def main():
    common.load_env()
    conn = common.connect()
    with conn, conn.cursor() as cur:
        m = Matcher(cur)
        out, unmatched = [], []
        for source_id, key, label, kind, sido, sg in collect(cur):
            if sg and norm(sg) in SKIP_WORDS:
                continue  # 원천의 통계 행 ('울산 평균' 등)
            if kind == "sido":
                leaves, gran = m.sido_leaves(sido)
                method, reason = "rule", "unknown sido"
            else:
                leaves, gran, method = m.sigungu(sido, sg)
                reason = method
            if leaves:
                out += [(source_id, key, label, code, gran, method) for code in leaves]
            else:
                unmatched.append((source_id, key, label, reason))
        cur.execute("TRUNCATE dim.region_xwalk, dim.region_xwalk_unmatched")
        psycopg2.extras.execute_values(cur, """INSERT INTO dim.region_xwalk
            (source_id, source_key, source_label, region_code, granularity, match_method) VALUES %s
            ON CONFLICT DO NOTHING""", out)
        if unmatched:
            psycopg2.extras.execute_values(cur, """INSERT INTO dim.region_xwalk_unmatched
                (source_id, source_key, source_label, reason) VALUES %s ON CONFLICT DO NOTHING""", unmatched)
        cur.execute("""SELECT source_id, count(DISTINCT source_key), count(*), count(DISTINCT region_code)
                       FROM dim.region_xwalk GROUP BY 1 ORDER BY 1""")
        summary = cur.fetchall()
    conn.close()
    for sid, keys, rows, leaves in summary:
        print(f"  {sid:24} 키 {keys:4}개 → leaf {leaves:3}곳 ({rows}행)")
    print(f"매핑 못 한 키 {len(unmatched)}개" + (" → dim.region_xwalk_unmatched" if unmatched else ""))
    for u in unmatched[:30]:
        print("   ", u)


if __name__ == "__main__":
    main()
