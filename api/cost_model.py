"""
질문지 → 시군구별 월 생활비 추정 (순수 함수, DB 없음)

- QUESTIONS: 질문·선택지 문구와 모델 계수. /api/questions가 그대로 내려준다 → 문구만 바꿀 땐 여기만 고친다.
  말투: 재미있게, 하지만 비하하지 않는다(소득·외모·가족 형태 농담 금지). 선택지마다 hint(작은 글씨 기준)를 꼭 단다.
- estimate(region, answers): 지역 1곳의 항목별 원/월
- recommend(regions, answers): 조건에 맞는 지역을 월 합계 오름차순으로

계수의 근거는 상수 옆 주석에. 아직 확인 못 한 값은 'TODO 출처'.
"""
from statistics import median

# ── 계수 ─────────────────────────────────────────────────────
RATE = 0.055  # 전세 보증금 기회비용(연). mart.rent_*의 환산 월세와 같은 값 (sql/mart/10_rent.sql)
MIN_DEALS = 10  # 최근 12개월 거래가 이보다 적은 면적대의 중위값은 믿지 않고 '자료 없음'(→ 시도 중위값으로 채움)

HOUSEHOLD = {   # 문항 1
    "solo":   {"persons": 1, "band": "s", "water": 0.5, "gas_units": 2.5, "trash": 1.0, "riders": 1, "eaters": 1, "grocery_base": 220_000},
    "duo":    {"persons": 2, "band": "m", "water": 0.8, "gas_units": 3.5, "trash": 1.5, "riders": 2, "eaters": 2, "grocery_base": 380_000},
    "family": {"persons": 4, "band": "l", "water": 1.2, "gas_units": 5.0, "trash": 2.5, "riders": 2, "eaters": 3, "grocery_base": 620_000},
}
# water: 상하수도 요금(20㎥ 기준값)에 곱하는 가구원 배율. 20㎥ ≈ 2~3인 가구 월 사용량. TODO 출처: 환경부 상수도통계 1인당 급수량
# gas_units: 월 사용량을 '516MJ(취사 기준 1단위)' 몇 개로 볼지. gas_total은 행안부 지방공공요금의 취사 516MJ 월 요금이라
#            그대로 쓰면 난방이 빠진다 → 연평균 월 사용량으로 환산. TODO 출처: 도시가스 가정용 가구당 월평균 사용량
# trash: 쓰레기봉투 장수(문항 7, 1인 기준)에 곱하는 가구원 보정
# riders: 시내버스를 타는 사람 수 / eaters: 외식 인원 (아이 둘 ≈ 어른 한 명분)
# grocery_base: 가구원 수별 월 식료품·비주류음료 지출(원). TODO 출처: 통계청 가계동향조사 가구원수별 소비지출

QUESTIONS = [
    {"id": "household", "title": "우리 집 인구는?", "kind": "single", "options": [
        {"id": "solo", "label": "혼자가 최고", "hint": "1인 가구 · 40㎡ 이하 집 기준"},
        {"id": "duo", "label": "둘이 딱 좋아", "hint": "2인 가구 · 40~60㎡ 집 기준"},
        {"id": "family", "label": "우리 집은 작은 부족", "hint": "자녀 있는 가구(4인) · 60~85㎡ 집 기준"},
    ]},
    {"id": "tenure", "title": "집은 어떻게 구할 계획?", "kind": "single", "options": [
        {"id": "wolse", "label": "월세로 가볍게", "hint": "보증금+월세를 월 비용으로 환산"},
        {"id": "jeonse", "label": "목돈 묻어 두는 전세파", "hint": "전세 보증금의 이자(연 5.5%)를 월 비용으로"},
        {"id": "any", "label": "싼 쪽으로 알아서", "hint": "지역마다 월세·전세 중 더 싼 쪽"},
    ]},
    {"id": "shower", "title": "샤워할 때 나는?", "kind": "single", "options": [
        {"id": "quick", "label": "군대식 3분 샤워", "hint": "5분 이하", "factor": 0.7},
        {"id": "normal", "label": "평범한 시민", "hint": "10분 안팎", "factor": 1.0},
        {"id": "waterpark", "label": "워터파크 개장", "hint": "15분 이상 · 하루 2번", "factor": 1.5},
    ]},
    {"id": "boiler", "title": "겨울 보일러는?", "kind": "single", "options": [
        {"id": "low", "label": "전기장판과 의리", "hint": "보일러는 거의 안 켬", "factor": 0.6},
        {"id": "mid", "label": "적당히 따뜻하게", "hint": "외출할 땐 끄고, 잘 땐 약하게", "factor": 1.0},
        {"id": "sauna", "label": "집이 곧 찜질방", "hint": "한겨울에도 반팔로 지냄", "factor": 1.6},
    ]},
    {"id": "grocery", "title": "냉장고 사정은?", "kind": "single", "options": [
        {"id": "empty", "label": "냉장고는 생수 보관함", "hint": "장보기 거의 안 함", "factor": 0.5},
        {"id": "weekly", "label": "주말마다 장보기", "hint": "주 1회 장보기", "factor": 1.0},
        {"id": "vip", "label": "마트 시식 코너 VIP", "hint": "주 2~3회 장보기", "factor": 1.4},
    ]},
    {"id": "dining", "title": "밖에서 사 먹는 끼니는?", "kind": "single", "options": [
        {"id": "home", "label": "집밥 수호자", "hint": "주 0~1회", "meals": 3},
        {"id": "half", "label": "반반 치킨처럼 반반", "hint": "주 2~4회", "meals": 12},
        {"id": "outside", "label": "배달앱·식당 VIP", "hint": "주 5회 이상", "meals": 25},
    ]},
    {"id": "trash", "title": "쓰레기봉투(20ℓ) 한 장으로?", "kind": "single", "options": [
        {"id": "minimal", "label": "한 달 버티는 미니멀리스트", "hint": "월 1~2장", "bags": 2},
        {"id": "weekly", "label": "일주일이면 꽉 참", "hint": "주 1장", "bags": 4},
        {"id": "regular", "label": "분리수거장 단골 손님", "hint": "주 2장 이상", "bags": 9},
    ]},
    {"id": "transit", "title": "나의 이동 수단은?", "kind": "single", "options": [
        {"id": "walk", "label": "두 발이 곧 대중교통", "hint": "버스는 거의 안 탐", "trips": 2},
        {"id": "commute", "label": "출퇴근 버스 정기 승객", "hint": "월 40회 안팎", "trips": 44},
        {"id": "bus_friend", "label": "버스 기사님과 인사하는 사이", "hint": "월 60회 이상", "trips": 66},
    ]},
    {"id": "where", "title": "어디서, 얼마까지?", "kind": "filters",
     "fields": [
         {"id": "sidos", "label": "살고 싶은 시도", "hint": "비워 두면 전국 어디든", "type": "multi_sido"},
         {"id": "housing_cap", "label": "월 주거비 상한 (만 원)", "hint": "비워 두면 상관없음", "type": "number"},
         {"id": "need_mart", "label": "근처에 대형마트는 있어야지", "hint": "대형마트·SSM 조사 점포가 있는 시군구만", "type": "bool"},
     ]},
]
DEFAULTS = {"household": "solo", "tenure": "any", "shower": "normal", "boiler": "mid", "grocery": "weekly",
            "dining": "half", "trash": "weekly", "transit": "commute", "sidos": [], "housing_cap": None, "need_mart": False}

ITEMS = ["housing", "water", "gas", "trash", "transit", "dining", "grocery"]
ITEM_LABEL = {"housing": "주거", "water": "상하수도", "gas": "도시가스", "trash": "쓰레기봉투",
              "transit": "버스", "dining": "외식", "grocery": "장보기"}
ITEM_SOURCE = {"housing": "molit_rent", "water": "std_water_sewage_fee", "gas": "mois_public_fee",
               "trash": "std_trash_bag_price", "transit": "mois_public_fee", "dining": "mois_dining", "grocery": "kca_price"}


def _opt(qid, oid):
    q = next(q for q in QUESTIONS if q["id"] == qid)
    return next(o for o in q["options"] if o["id"] == oid)


def normalize(answers):
    """기본값 채우고 잘못된 선택지는 막는다 (ValueError)"""
    a = {**DEFAULTS, **{k: v for k, v in (answers or {}).items() if v is not None}}
    for q in QUESTIONS:
        if q["kind"] == "single" and a[q["id"]] not in {o["id"] for o in q["options"]}:
            raise ValueError(f"{q['id']}: 알 수 없는 선택지 {a[q['id']]!r}")
    a["sidos"] = list(a.get("sidos") or [])
    cap = a.get("housing_cap")
    a["housing_cap"] = float(cap) if cap not in (None, "") else None
    a["need_mart"] = bool(a.get("need_mart"))
    return a


def _housing(r, hh, tenure):
    band = hh["band"]
    wol = r.get(f"cost_{band}")
    wol = wol * 10_000 if wol is not None and (r.get(f"deals_{band}") or 0) >= MIN_DEALS else None
    jeon = r.get(f"jeonse_{band}")
    jeon = (jeon * 10_000 * RATE / 12
            if jeon is not None and (r.get(f"jeonse_deals_{band}") or 0) >= MIN_DEALS else None)
    if tenure == "wolse":
        return wol
    if tenure == "jeonse":
        return jeon
    vals = [v for v in (wol, jeon) if v is not None]
    return min(vals) if vals else None


def estimate(r, answers):
    """지역 행 1개 → {항목: 원/월 또는 None}. answers는 normalize() 결과"""
    a = answers
    hh = HOUSEHOLD[a["household"]]
    out = {
        "housing": _housing(r, hh, a["tenure"]),
        "water": r["water_sewer"] * hh["water"] * _opt("shower", a["shower"])["factor"] if r.get("water_sewer") else None,
        "gas": r["gas_total"] * hh["gas_units"] * _opt("boiler", a["boiler"])["factor"] if r.get("gas_total") else None,
        "trash": r["trash_20l"] * _opt("trash", a["trash"])["bags"] * hh["trash"] if r.get("trash_20l") else None,
        "transit": r["bus_card"] * _opt("transit", a["transit"])["trips"] * hh["riders"] if r.get("bus_card") else None,
        "dining": r["meal_avg"] * _opt("dining", a["dining"])["meals"] * hh["eaters"] if r.get("meal_avg") else None,
        "grocery": (hh["grocery_base"] * _opt("grocery", a["grocery"])["factor"] * r["grocery_index"] / 100
                    if r.get("grocery_index") else None),
    }
    return {k: (round(v) if v is not None else None) for k, v in out.items()}


GRAN_FIELD = {"housing": None, "water": "water_sewer_gran", "gas": None, "trash": "trash_gran",
              "transit": None, "dining": "dining_gran", "grocery": "grocery_gran"}
SIDO_LEVEL = {"gas", "transit"}   # 원천 자체가 시도 평균


def recommend(regions, answers):
    """regions: /api/regions 행 목록. → (결과 목록, 가정). 결측 항목은 같은 시도 중위값(없으면 전국 중위값)으로 채우고 filled=True"""
    a = normalize(answers)
    est = {r["region_code"]: estimate(r, a) for r in regions}
    by_sido, nat = {}, {}
    for r in regions:
        for k, v in est[r["region_code"]].items():
            if v is not None:
                by_sido.setdefault((r["sido"], k), []).append(v)
                nat.setdefault(k, []).append(v)
    results = []
    for r in regions:
        if a["sidos"] and r["sido"] not in a["sidos"]:
            continue
        if a["need_mart"] and not (r.get("grocery_stores") or 0) > 0:
            continue
        e = est[r["region_code"]]
        if a["housing_cap"] is not None and (e["housing"] is None or e["housing"] > a["housing_cap"] * 10_000):
            continue
        items = {}
        for k in ITEMS:
            v, filled = e[k], False
            if v is None:
                pool = by_sido.get((r["sido"], k)) or nat.get(k)
                v, filled = (round(median(pool)) if pool else 0), True
            gran = "sido" if k in SIDO_LEVEL else (r.get(GRAN_FIELD[k]) if GRAN_FIELD[k] else "exact")
            items[k] = {"label": ITEM_LABEL[k], "value": v, "filled": filled, "gran": gran, "source": ITEM_SOURCE[k]}
        results.append({"region_code": r["region_code"], "sido": r["sido"], "sigungu": r["sigungu"],
                        "total": sum(i["value"] for i in items.values()), "items": items})
    results.sort(key=lambda x: (x["total"], x["region_code"]))
    for i, x in enumerate(results, 1):
        x["rank"] = i
    hh = HOUSEHOLD[a["household"]]
    assumptions = {
        "rate": RATE, "household": hh,
        "factors": {q["id"]: _opt(q["id"], a[q["id"]]) for q in QUESTIONS if q["kind"] == "single"},
        "notes": [
            "주거비는 최근 12개월 실거래 중위값이고, 전세는 보증금 이자(연 5.5%)로 환산했습니다.",
            "상하수도는 기본요금이 빠져 있어 실제보다 조금 낮습니다.",
            "도시가스·버스는 시도 평균 요금, 외식비는 시도 평균 가격입니다.",
            "장보기는 가구 기준 지출에 지역 장바구니 지수를 곱한 값입니다 (대형마트·SSM 기준).",
            "모든 값은 추정치이며 실제와 다를 수 있습니다.",
        ],
    }
    return results, a, assumptions
