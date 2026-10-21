"""
질문지 → 시군구별 월 생활비 추정 (순수 함수, DB 없음)

- QUESTIONS: 질문·선택지 문구와 모델 계수. /api/questions가 그대로 내려준다 → 문구만 바꿀 땐 여기만 고친다.
  말투: 재미있게, 하지만 비하하지 않는다(소득·외모·가족 형태 농담 금지). 선택지마다 hint(작은 글씨 기준)를 꼭 단다.
- estimate(region, answers): 지역 1곳의 항목별 원/월
- recommend(regions, answers): 조건에 맞는 지역을 월 합계 오름차순으로

계수의 근거는 아래 '근거 통계'와 상수 옆 주석에. 근거 수치를 바꾸면 계수는 다시 계산된다.
"""
from math import sqrt
from statistics import median

from api.power_tariff import bill as power_bill

# ── 근거 통계 (2026-10-21 확인) ─────────────────────────────────
# [식료품] 국가데이터처 가계동향조사, KOSIS DT_1L9U105 「가구원수별 가구당 월평균 가계수지 (전국,1인이상)」
#          01.식료품·비주류음료, 전체가구, 2026.1/4와 2026.2/4의 평균 (원/월). 가족은 '4인' 행.
#          https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1L9U105
GROCERY_SPEND = {1: (246_648 + 235_269) / 2, 2: (478_532 + 450_852) / 2, 4: (689_743 + 672_983) / 2}
AVG_HOUSEHOLD_SIZE = 2.16   # 같은 표의 '전체 평균' 가구원수 (2026.1/4·2/4)
# [외식] 같은 표의 11.음식·숙박, 2026.1/4·2/4 평균 (원/월). 숙박이 섞여 있어 금액이 아니라 '1인 가구 대비 배수'만 쓴다
#        → 외식 인원 배수 eaters = 가구원 수별 지출 / 1인 지출 (1 / 1.28 / 2.43)
DINING_SPEND = {1: (307_285 + 322_484) / 2, 2: (388_066 + 421_121) / 2, 4: (775_525 + 755_829) / 2}
# [물] 기후에너지환경부 「2024년 상수도 통계」: 국민 1인 1일 물 사용량 305.9ℓ 중 가정용 196.6ℓ
#      (한국수자원공사 안내 페이지 https://www.kwater.or.kr/cust/sub04/rateconsumerPage.do?s_mid=1548)
WATER_L_PER_PERSON_DAY = 196.6
WATER_BASE_M3 = 20          # mart의 상하수도 요금 기준 사용량 (sql/mart/20_utility.sql)
# [가스] 한국가스공사 「연별 가구당 가정용 도시가스 소비량」 (data.go.kr 15130018): 2022년 가구당 559.6㎥/년
#        도시가스 총발열량 42.7MJ/N㎥ (에너지법 시행규칙 별표) → 월 46.6㎥ ≈ 1,991MJ
#        gas_total(행안부 지방공공요금)은 '가정용 취사 516MJ' 월 요금이라 그 몇 배인지(단위 수)로 쓴다.
GAS_M3_PER_HOUSEHOLD_YEAR = 559.6
GAS_MJ_PER_M3 = 42.7
GAS_UNIT_MJ = 516
# 가구원 수별 가스 사용량 통계는 찾지 못해, 평균 가구(2.16명) 값을 OECD 제곱근 등가척도(√가구원 수)로 나눈다 — 가정.
#   1인 2.63 / 2인 3.71 / 4인 5.25 단위
# [전기] 한전 전력데이터개방포털 「가구평균 전력사용량」 시군구 × 월 (mart.power_region kwh_m01~m12, 최근 12개월)
#        → 가구원 수 보정(가스와 같은 √ 척도, 평균 2.16명 = 1.0) × 에어컨 문항(7~8월만) → 달마다 주택용 요금표
#        (api/power_tariff.py, 2024-07-01 시행)로 계산해 12개월 평균. 누진제라 평균 kWh에 단가를 곱하지 않는다.
SUMMER = (7, 8)
# [관리비] K-apt 관리비공개의무단지 (mart.mgmt_region): (공용관리비 + 장기수선충당금) ÷ 관리비부과면적 의 시군구 중위값(원/㎡·월)
#          관리비부과면적은 대개 공급면적 → 면적대 대표 전용면적 × 1.3(전용→공급 환산, 가정)
BAND_AREA = {"s": 33, "m": 50, "l": 75}   # 면적대(≤40, 40~60, 60~85㎡)의 대표 전용면적
SUPPLY_RATIO = 1.3


def _water_factor(persons):
    """20㎥ 기준 요금에 곱할 배율 = 가구 월 사용량 / 20㎥ (1인 0.30, 2인 0.60, 4인 1.20)"""
    return round(persons * WATER_L_PER_PERSON_DAY * 365 / 12 / 1000 / WATER_BASE_M3, 3)


def _elec_factor(persons):
    """평균 가구(2.16명) 대비 전기 사용량 배율 (1인 0.68, 2인 0.96, 4인 1.36) — 가정"""
    return round(sqrt(persons) / sqrt(AVG_HOUSEHOLD_SIZE), 2)


def _gas_units(persons):
    avg_units = GAS_M3_PER_HOUSEHOLD_YEAR / 12 * GAS_MJ_PER_M3 / GAS_UNIT_MJ     # 평균 가구 ≈ 3.86단위
    return round(avg_units * sqrt(persons) / sqrt(AVG_HOUSEHOLD_SIZE), 2)


# ── 계수 ─────────────────────────────────────────────────────
RATE = 0.055  # 전세 보증금 기회비용(연). mart.rent_*의 환산 월세와 같은 값 (sql/mart/10_rent.sql)
MIN_DEALS = 10  # 최근 12개월 거래가 이보다 적은 면적대의 중위값은 믿지 않고 '자료 없음'(→ 시도 중위값으로 채움)

HOUSEHOLD = {   # 문항 1
    key: {"persons": n, "band": band, "water": _water_factor(n), "gas_units": _gas_units(n), "trash": trash,
          "elec": _elec_factor(n), "mgmt_m2": round(BAND_AREA[band] * SUPPLY_RATIO, 1),
          "riders": riders, "eaters": round(DINING_SPEND[n] / DINING_SPEND[1], 2), "grocery_base": round(GROCERY_SPEND[n], -2)}
    for key, n, band, trash, riders in [
        ("solo", 1, "s", 1.0, 1),
        ("duo", 2, "m", 1.5, 2),
        ("family", 4, "l", 2.5, 2),
    ]
}
# water: 상하수도 요금(20㎥ 기준값)에 곱하는 가구원 배율 — [물] 근거
# gas_units: 월 사용량을 '516MJ(취사 기준 1단위)' 몇 개로 볼지 — [가스] 근거 (난방 포함 연평균)
# grocery_base: 가구원 수별 월 식료품·비주류음료 지출(원) — [식료품] 근거. 냉장고 문항 배율(0.5/1.0/1.4)을 곱한다
# trash: 쓰레기봉투 장수(문항 7, 1인 기준)에 곱하는 가구원 보정 (가정)
# riders: 시내버스를 타는 사람 수 (가정)
# elec: 지역 가구 평균 전기 사용량에 곱하는 가구원 배율 — [전기] 근거
# mgmt_m2: 관리비를 매길 공급면적(㎡) — [관리비] 근거
# eaters: 외식비 배수 — [외식] 근거. 1인 가구 외식비의 몇 배를 쓰는지 (2인 1.28, 4인 2.43)

# 질문지: 질문마다 유머 섞인 A/B 두 답. 답 하나가 모델 값 하나(set)를 정한다.
#   show_if: 앞 질문의 답에 따라 보이는 질문 / set.where: 지역 조건 (mart.region_features)
QUESTIONS = [
    {"id": "living", "group": "생활", "title": "우리 집 식구는?", "options": [
        {"id": "a", "label": "나 혼자 산다, 자유가 최고", "hint": "1인 가구 · 40㎡ 이하 집", "set": {"household": "solo"}},
        {"id": "b", "label": "같이 사는 사람이 있다", "hint": "2인 이상", "set": {"household": "duo"}},
    ]},
    {"id": "family_size", "group": "생활", "title": "식탁에 둘러앉는 인원은?", "show_if": {"living": "b"}, "options": [
        {"id": "a", "label": "둘이 딱 좋아, 오붓하게", "hint": "2인 가구 · 40~60㎡ 집", "set": {"household": "duo"}},
        {"id": "b", "label": "우리 집은 작은 부족", "hint": "자녀 있는 4인 가구 · 60~85㎡ 집", "set": {"household": "family"}},
    ]},
    {"id": "tenure", "group": "생활", "title": "보증금은?", "options": [
        {"id": "a", "label": "목돈 묻어 두는 전세파", "hint": "전세 보증금 이자(연 5.5%)를 월 비용으로", "set": {"tenure": "jeonse"}},
        {"id": "b", "label": "통장은 가볍게, 월세파", "hint": "보증금+월세를 월 비용으로 환산", "set": {"tenure": "wolse"}},
    ]},
    {"id": "house", "group": "생활", "title": "우리 집 스타일은?", "options": [
        {"id": "a", "label": "관리사무소 아저씨와 인사하는 아파트파", "hint": "아파트 · 관리비 포함", "set": {"house": "apt"}},
        {"id": "b", "label": "관리비 없는 빌라·원룸 자유인", "hint": "빌라·다세대·오피스텔·단독", "set": {"house": "other"}},
    ]},
    {"id": "shower", "group": "생활", "title": "샤워할 때 물은?", "options": [
        {"id": "a", "label": "부르주아처럼 신경 안 쓰고 콸콸", "hint": "15분 이상 · 하루 두 번도 OK", "set": {"shower": 1.4}},
        {"id": "b", "label": "3분 컷, 군대식 샤워", "hint": "5분 이내", "set": {"shower": 0.8}},
    ]},
    {"id": "boiler", "group": "생활", "title": "한겨울 우리 집 온도는?", "options": [
        {"id": "a", "label": "집이 곧 찜질방, 한겨울에도 반팔", "hint": "보일러 늘 켜 둠", "set": {"boiler": 1.5}},
        {"id": "b", "label": "전기장판과 의리, 보일러는 거의 안 켬", "hint": "외출·취침 땐 끔", "set": {"boiler": 0.7}},
    ]},
    {"id": "aircon", "group": "생활", "title": "한여름 에어컨은?", "options": [
        {"id": "a", "label": "열대야엔 24시간 풀가동, 북극곰 모드", "hint": "7~8월 전기 사용량 1.5배", "set": {"aircon": 1.5}},
        {"id": "b", "label": "선풍기와 의리, 에어컨은 손님 올 때만", "hint": "7~8월 사용량 0.9배", "set": {"aircon": 0.9}},
    ]},
    {"id": "grocery", "group": "생활", "title": "우리 집 냉장고는?", "options": [
        {"id": "a", "label": "마트 시식 코너 VIP, 늘 꽉 차 있음", "hint": "주 2~3회 장보기", "set": {"grocery": 1.3}},
        {"id": "b", "label": "생수 보관함, 열면 메아리가 들림", "hint": "장보기 거의 안 함", "set": {"grocery": 0.6}},
    ]},
    {"id": "dining", "group": "생활", "title": "밥은 주로?", "options": [
        {"id": "a", "label": "배달앱 VVIP, 사장님이 내 이름을 앎", "hint": "주 5회 이상 사 먹음", "set": {"meals": 25}},
        {"id": "b", "label": "집밥 수호자, 냉장고 털이 장인", "hint": "주 1회 이하", "set": {"meals": 4}},
    ]},
    {"id": "trash", "group": "생활", "title": "쓰레기봉투(20ℓ)는?", "options": [
        {"id": "a", "label": "분리수거장 단골 손님", "hint": "주 2장 이상", "set": {"bags": 9}},
        {"id": "b", "label": "한 장으로 한 달 버티는 미니멀리스트", "hint": "월 1~2장", "set": {"bags": 2}},
    ]},
    {"id": "transit", "group": "생활", "title": "출퇴근은?", "options": [
        {"id": "a", "label": "버스 기사님과 인사하는 사이", "hint": "버스 월 40회 이상", "set": {"trips": 44}},
        {"id": "b", "label": "두 발 또는 내 차가 최고", "hint": "버스는 거의 안 탐", "set": {"trips": 2}},
    ]},
    {"id": "capital", "group": "어디서", "title": "서울과의 거리는?", "options": [
        {"id": "a", "label": "수도권 아니면 안 돼, 한강 뷰는 못 참지", "hint": "서울·경기·인천만", "set": {"where": {"capital": True}}},
        {"id": "b", "label": "서울은 가끔 놀러 가면 충분", "hint": "상관없음", "set": {}},
    ]},
    {"id": "metro", "group": "어디서", "title": "도시의 크기는?", "options": [
        {"id": "a", "label": "광역시급 생활권, 지하철 소리가 자장가", "hint": "특별·광역시 또는 그와 맞닿은 시군구", "set": {"where": {"metro_area": True}}},
        {"id": "b", "label": "작은 도시도 시골도 다 좋아", "hint": "상관없음", "set": {}},
    ]},
    {"id": "sea", "group": "어디서", "title": "바다는?", "options": [
        {"id": "a", "label": "창문 열면 바다 냄새가 나야 해", "hint": "바다와 맞닿은 시군구", "set": {"where": {"coastal": True}}},
        {"id": "b", "label": "바다는 여행 갈 때만 보면 충분", "hint": "상관없음", "set": {}},
    ]},
    {"id": "airport", "group": "어디서", "title": "비행기는?", "options": [
        {"id": "a", "label": "공항까지 1시간 안, 훌쩍 떠나는 게 낙", "hint": "가장 가까운 공항까지 직선 40km 이내 (차로 1시간 안팎)", "set": {"where": {"airport": True}}},
        {"id": "b", "label": "비행기는 1년에 한 번 탈까 말까", "hint": "상관없음", "set": {}},
    ]},
    {"id": "vibe", "group": "어디서", "title": "동네 분위기는?", "options": [
        {"id": "a", "label": "논밭과 산이 보이는 조용한 시골", "hint": "군 지역", "set": {"where": {"rural": True}}},
        {"id": "b", "label": "사람 사는 곳이면 어디든 OK", "hint": "상관없음", "set": {}},
    ]},
    {"id": "mart", "group": "어디서", "title": "장 볼 때는?", "options": [
        {"id": "a", "label": "대형마트 카트를 끌어야 장 본 기분", "hint": "대형마트·SSM 조사 점포가 있는 시군구", "set": {"where": {"need_mart": True}}},
        {"id": "b", "label": "동네 슈퍼·시장이면 충분", "hint": "상관없음", "set": {}},
    ]},
]
DEFAULTS = {"living": "a", "family_size": "a", "tenure": "b", "house": "b", "shower": "b", "boiler": "b",
            "aircon": "b", "grocery": "b",
            "dining": "b", "trash": "b", "transit": "a", "capital": "b", "metro": "b", "sea": "b", "airport": "b",
            "vibe": "b", "mart": "b"}
# 지역 조건 ↔ mart.region_features. 조건을 다 맞추는 곳이 MIN_RESULTS 미만이면 앞에서부터 하나씩 뺀다
WHERE = [  # (키, 화면 이름, 지역이 조건을 맞추는지)
    ("need_mart", "대형마트", lambda r: (r.get("grocery_stores") or 0) > 0),
    ("rural", "조용한 시골", lambda r: r.get("sigungu_type") == "군"),
    ("airport", "공항 1시간", lambda r: (r.get("airport_km") or 999) <= AIRPORT_KM),
    ("coastal", "바다", lambda r: bool(r.get("is_coastal"))),
    ("metro_area", "광역시 생활권", lambda r: bool(r.get("is_metro_area"))),
    ("capital", "수도권", lambda r: bool(r.get("is_capital"))),
]
MIN_RESULTS = 3
AIRPORT_KM = 40   # 직선거리. 도로는 보통 1.3배 → 약 50km, 차로 1시간 안팎

ITEMS = ["housing", "mgmt", "electricity", "gas", "water", "dining", "grocery", "transit", "trash"]
ITEM_LABEL = {"housing": "주거", "mgmt": "관리비", "electricity": "전기", "gas": "도시가스", "water": "상하수도",
              "dining": "외식", "grocery": "장보기", "transit": "버스", "trash": "쓰레기봉투"}
ITEM_SOURCE = {"housing": "molit_rent", "mgmt": "kapt_fee", "electricity": "kepco_house_power",
               "gas": "mois_public_fee", "water": "std_water_sewage_fee", "dining": "mois_dining",
               "grocery": "kca_price", "transit": "mois_public_fee", "trash": "std_trash_bag_price"}
# 화면 묶음 (카드 막대·범례는 묶음 4색, 펼치면 항목별)
GROUPS = [{"id": "home", "label": "주거"}, {"id": "energy", "label": "에너지·관리비"},
          {"id": "food", "label": "먹거리"}, {"id": "etc", "label": "교통·기타"}]
ITEM_GROUP = {"housing": "home", "mgmt": "energy", "electricity": "energy", "gas": "energy", "water": "energy",
              "dining": "food", "grocery": "food", "transit": "etc", "trash": "etc"}


def visible(q, ans):
    """앞 질문 답에 따라 이 질문을 보여 줄지 (show_if)"""
    return all(ans.get(k) == v for k, v in q.get("show_if", {}).items())


def normalize(answers):
    """답(질문 id → 'a'/'b') → 계산용 값. 잘못된 답은 ValueError"""
    raw = {**DEFAULTS, **{k: v for k, v in (answers or {}).items() if v is not None}}
    p = {"household": "solo", "tenure": "wolse", "house": "other", "shower": 1.0, "boiler": 1.0, "aircon": 1.0,
         "grocery": 1.0,
         "meals": 12, "bags": 4, "trips": 44, "where": {}}
    for q in QUESTIONS:
        if not visible(q, raw):
            continue
        opt = next((o for o in q["options"] if o["id"] == raw.get(q["id"])), None)
        if opt is None:
            raise ValueError(f"{q['id']}: 알 수 없는 답 {raw.get(q['id'])!r} (a 또는 b)")
        for k, v in opt["set"].items():
            if k == "where":
                p["where"].update(v)
            else:
                p[k] = v
    return {"answers": {q["id"]: raw[q["id"]] for q in QUESTIONS if visible(q, raw)}, **p}


def _rent(r, band, kind, prefix):
    """kind 'wolse'|'jeonse', prefix ''(전체 유형) 또는 'apt_'(아파트만) → 원/월 또는 None(표본 부족)"""
    if kind == "wolse":
        v, n = r.get(f"cost_{prefix}{band}"), r.get(f"deals_{prefix}{band}")
        return v * 10_000 if v is not None and (n or 0) >= MIN_DEALS else None
    v, n = r.get(f"jeonse_{prefix}{band}"), r.get(f"jeonse_deals_{prefix}{band}")
    return v * 10_000 * RATE / 12 if v is not None and (n or 0) >= MIN_DEALS else None


def _housing(r, hh, tenure, house="other"):
    """아파트파면 아파트 전월세를 먼저 쓰고, 아파트 거래가 적으면 전체 유형 값"""
    band = hh["band"]
    prefixes = ["apt_", ""] if house == "apt" else [""]
    wol = next((v for p in prefixes if (v := _rent(r, band, "wolse", p)) is not None), None)
    jeon = next((v for p in prefixes if (v := _rent(r, band, "jeonse", p)) is not None), None)
    if tenure == "wolse":
        return wol
    if tenure == "jeonse":
        return jeon
    vals = [v for v in (wol, jeon) if v is not None]
    return min(vals) if vals else None


def _electricity(r, hh, aircon):
    """달별 지역 평균 kWh × 가구원 배율 × (여름만 에어컨 배수) → 달마다 요금표 → 12개월 평균 (원/월)
    × 지역 보정(한전 실제 평균 청구액 ÷ 평균 가구를 요금표로 계산한 값).
      요금표(저압)로만 계산하면 전국 중앙값이 실제보다 약 15% 높다: 아파트 단일계약(고압 요금이 더 쌈)과
      복지할인이 빠지기 때문. 보정하면 평균 가구는 한전 청구액과 같아지고, 가구원·에어컨 차이는 누진대로 남는다."""
    kwh = [r.get(f"kwh_m{m:02d}") for m in range(1, 13)]
    if any(k is None for k in kwh):
        return None
    bills = [power_bill(k * hh["elec"] * (aircon if m in SUMMER else 1.0), m) for m, k in enumerate(kwh, 1)]
    base = sum(power_bill(k, m) for m, k in enumerate(kwh, 1)) / 12
    calib = min(1.2, max(0.6, r["power_bill"] / base)) if r.get("power_bill") and base else 1.0
    return sum(bills) / 12 * calib


def estimate(r, answers):
    """지역 행 1개 → {항목: 원/월 또는 None}. answers는 normalize() 결과"""
    a = answers
    hh = HOUSEHOLD[a["household"]]
    out = {
        "housing": _housing(r, hh, a["tenure"], a["house"]),
        "mgmt": ((r["mgmt_per_m2"] * hh["mgmt_m2"] if r.get("mgmt_per_m2") else None)
                 if a["house"] == "apt" else 0),
        "electricity": _electricity(r, hh, a["aircon"]),
        "water": r["water_sewer"] * hh["water"] * a["shower"] if r.get("water_sewer") else None,
        "gas": r["gas_total"] * hh["gas_units"] * a["boiler"] if r.get("gas_total") else None,
        "trash": r["trash_20l"] * a["bags"] * hh["trash"] if r.get("trash_20l") else None,
        "transit": r["bus_card"] * a["trips"] * hh["riders"] if r.get("bus_card") else None,
        "dining": r["meal_avg"] * a["meals"] * hh["eaters"] if r.get("meal_avg") else None,
        "grocery": (hh["grocery_base"] * a["grocery"] * r["grocery_index"] / 100
                    if r.get("grocery_index") else None),
    }
    return {k: (round(v) if v is not None else None) for k, v in out.items()}


GRAN_FIELD = {"housing": None, "mgmt": "mgmt_gran", "electricity": "power_gran", "water": "water_sewer_gran",
              "gas": None, "trash": "trash_gran", "transit": None, "dining": "dining_gran", "grocery": "grocery_gran"}
SIDO_LEVEL = {"gas", "transit"}   # 원천 자체가 시도 평균


def _items(r, e, by_sido, nat, house="other"):
    items = {}
    for k in ITEMS:
        v, filled = e[k], False
        if k == "mgmt" and house != "apt":   # 빌라·원룸파: 관리비 해당 없음 (0원, 채우지 않음)
            items[k] = {"label": ITEM_LABEL[k], "value": 0, "filled": False, "gran": None,
                        "source": ITEM_SOURCE[k], "group": ITEM_GROUP[k], "na": True}
            continue
        if v is None:
            pool = by_sido.get((r["sido"], k)) or nat.get(k)
            v, filled = (round(median(pool)) if pool else 0), True
        gran = "sido" if k in SIDO_LEVEL else (r.get(GRAN_FIELD[k]) if GRAN_FIELD[k] else "exact")
        items[k] = {"label": ITEM_LABEL[k], "value": v, "filled": filled, "gran": gran, "source": ITEM_SOURCE[k],
                    "group": ITEM_GROUP[k]}
    return items


def recommend(regions, answers):
    """regions: 요약 행(+ mart.region_features 칸). → (결과, 정규화된 답, 가정)
    - 결측 항목은 같은 시도 중위값(없으면 전국 중위값)으로 채우고 filled=True
    - 지역 조건을 다 맞추는 곳이 MIN_RESULTS 미만이면 WHERE 앞쪽 조건부터 빼고 relaxed에 남긴다
    - national_rank / national_pct: 지역 조건과 상관없이 전국 시군구 중 몇 번째로 싼지"""
    a = normalize(answers)
    est = {r["region_code"]: estimate(r, a) for r in regions}
    by_sido, nat = {}, {}
    for r in regions:
        for k, v in est[r["region_code"]].items():
            if v is not None and not (k == "mgmt" and a["house"] != "apt"):
                by_sido.setdefault((r["sido"], k), []).append(v)
                nat.setdefault(k, []).append(v)
    everyone = []
    for r in regions:
        items = _items(r, est[r["region_code"]], by_sido, nat, a["house"])
        everyone.append({"region_code": r["region_code"], "sido": r["sido"], "sigungu": r["sigungu"],
                         "total": sum(i["value"] for i in items.values()), "items": items, "_row": r})
    everyone.sort(key=lambda x: (x["total"], x["region_code"]))
    n = len(everyone)
    for i, x in enumerate(everyone, 1):
        x["national_rank"], x["national_pct"] = i, max(1, -(-i * 100 // n))   # 싼 순 상위 몇 %인지 (올림, 최소 1)

    wanted = [w for w in WHERE if a["where"].get(w[0])]
    relaxed = []
    while True:
        results = [x for x in everyone if all(ok(x["_row"]) for _, _, ok in wanted)]
        if len(results) >= MIN_RESULTS or not wanted:
            break
        relaxed.append(wanted.pop(0)[1])
    out = []
    for i, x in enumerate(results, 1):
        out.append({**{k: v for k, v in x.items() if k != "_row"}, "rank": i})
    hh = HOUSEHOLD[a["household"]]
    assumptions = {
        "rate": RATE, "household": hh,
        "params": {k: a[k] for k in ("tenure", "house", "shower", "boiler", "aircon", "grocery", "meals", "bags",
                                     "trips")},
        "where": [label for key, label, _ in WHERE if a["where"].get(key) and label not in relaxed],
        "relaxed": relaxed,
        "notes": [
            "주거비는 최근 12개월 실거래 중위값이고, 전세는 보증금 이자(연 5.5%)로 환산했습니다. 아파트파는 아파트 거래만 보고, 아파트 거래가 적은 곳은 전체 유형 값을 씁니다.",
            "관리비(아파트파만)는 K-apt 관리비 공개 의무단지의 ㎡당 공용관리비+장기수선충당금 시군구 중위값에 공급면적(면적대 대표 전용면적 × 1.3, 가정)을 곱했습니다. 전기·수도·가스 같은 개별사용료는 다른 항목에 따로 있어 뺐습니다.",
            "전기는 한전 시군구 가구 평균 월별 사용량(최근 12개월)에 가구원 수 배율(가정)과 여름 에어컨 답을 반영해, 달마다 주택용 누진 요금표(2024-07-01)로 계산하고, 지역의 한전 실제 평균 청구액에 맞춰 보정한 값입니다 (아파트 단일계약·복지할인 반영).",
            "상하수도는 기본요금이 빠져 있어 실제보다 조금 낮습니다.",
            "도시가스·버스는 시도 평균 요금, 외식비는 시도 평균 가격입니다. 가구원 수에 따른 외식비 배수는 가계동향조사 음식·숙박 지출 비율(1인 대비 2인 1.28배, 4인 2.43배)을 썼습니다.",
            "장보기는 가구원 수별 식료품비(국가데이터처 가계동향조사 2026년 1~2분기)에 지역 장바구니 지수를 곱한 값입니다 (대형마트·SSM 기준).",
            "물 사용량은 1인 하루 196.6ℓ(2024년 상수도 통계 가정용), 도시가스는 가구당 연 559.6㎥(한국가스공사 2022년)를 기준으로 했습니다. 가스의 가구원 수별 차이는 추정입니다.",
            "바다는 해안선이 3km 이상인 시군구, 공항은 가장 가까운 공항까지 직선 40km 이내(도로 약 1.3배, 차로 1시간 안팎), 광역시 생활권은 특별·광역시와 그와 맞닿은 시군구입니다.",
            "모든 값은 추정치이며 실제와 다를 수 있습니다.",
        ],
    }
    return out, a, assumptions
