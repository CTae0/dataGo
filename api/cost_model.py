"""
질문지 → 시군구별 월 생활비 추정 (순수 함수, DB 없음)

- QUESTIONS: 질문·선택지 문구와 모델 계수. /api/questions가 그대로 내려준다 → 문구만 바꿀 땐 여기만 고친다.
  말투: 재미있게, 하지만 비하하지 않는다(소득·외모·가족 형태 농담 금지). 선택지마다 hint(작은 글씨)를 꼭 단다. hint는 '어떤 생활인지'만 적고(예: 보일러 늘 켜 둠) 계산 방식(배수·우대·반영 여부)은 적지 않는다 → 결과 화면 '이렇게 계산했어요'에만 둔다.
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
# [기름값] 한국교통안전공단 「2025년 자동차주행거리 통계」(2026-06 발표): 비사업용 자동차 1대당 일평균 30.8km
#          → 월 937km를 '자가용 출퇴근' 기준 거리로, 거리 문항이 배수(장거리 1.5 / 단거리 0.6)를 정한다.
#          연비는 최신 공식 평균을 찾지 못해 휘발유 승용차 12km/ℓ로 둔다 — 가정.
#          유가는 오피넷 시군구 보통휘발유 평균가 (mart.fuel_region gasoline_30d, 원/ℓ, 최근 30일 스냅샷 평균)
# [생활편의 점수] mart.region_scores (sql/mart/85_amenities.sql): 시설 종류별 지표 점수 0~100 (전국 백분위 기반)
#   세부 질문에서 A를 고른 시설만 가중치를 받는다.
#   종합 점수 = (1 − Σw) × 생활비 점수 + Σ (w_i × 지표 점수_i)
#   생활비 점수 = 전국 시군구 중 싼 순서를 0~100으로 (가장 싼 곳 100). 하나도 안 고르면 Σw = 0 → 생활비 순서 그대로.
#   가중치는 '생활비가 여전히 가장 큰 기준'이 되게 정한 설계 값(근거 통계 아님). 다 고르면 합이 0.99라
#   MAX_AMENITY_WEIGHT(0.5)에 맞춰 같은 비율로 줄인다.
INDICATORS = {   # 키: (요약 표 칸, 가중치, 화면 이름, 분야)
    "kinder": ("kinder_score", 0.10, "유치원", "교육"),
    "elem": ("elem_score", 0.10, "초등학교", "교육"),
    "secondary": ("secondary_score", 0.08, "중·고등학교", "교육"),
    "academy": ("academy_score", 0.10, "학원", "교육"),
    "library": ("library_score", 0.07, "도서관", "문화"),
    "museum": ("museum_score", 0.06, "박물관·미술관", "문화"),
    "arts": ("arts_score", 0.06, "문예회관·문화센터", "문화"),
    "park": ("park_score", 0.09, "공원", "생활"),
    # 안전·의료·환경 (sql/mart/86_health_env.sql mart.region_health_scores)
    "pediatric": ("pediatric_score", 0.08, "소아과", "의료"),
    "safety": ("safety_score", 0.07, "치안", "안전"),
    "hospital": ("hospital_score", 0.06, "병원·약국", "의료"),
    "emergency": ("emergency_score", 0.06, "응급실 거리", "의료"),
    "air": ("air_score", 0.06, "공기", "환경"),
}
MAX_AMENITY_WEIGHT = 0.5   # 다 고르면 합이 0.99 → 0.5로 줄인다 (생활비가 여전히 절반)
GROUP_SCORES = ("edu", "culture", "medical", "safety", "env")   # 분야 점수·별점 (요약 표 <분야>_score, <분야>_stars)
CAR_KM_PER_DAY = 30.8
CAR_KM_PER_MONTH = round(CAR_KM_PER_DAY * 365 / 12)   # 937km
FUEL_KM_PER_L = 12.0


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
        {"id": "a", "label": "나 혼자 산다, 자유가 최고", "hint": "혼자 사는 1인 가구", "set": {"household": "solo"}},
        {"id": "b", "label": "같이 사는 사람이 있다", "hint": "가족·연인·친구와 함께 살아요", "set": {"household": "duo"}},
    ]},
    {"id": "family_size", "group": "생활", "title": "식탁에 둘러앉는 인원은?", "show_if": {"living": "b"}, "options": [
        {"id": "a", "label": "둘이 딱 좋아, 오붓하게", "hint": "둘이 사는 2인 가구", "set": {"household": "duo"}},
        {"id": "b", "label": "우리 집은 작은 부족", "hint": "넷 안팎이 북적북적", "set": {"household": "family"}},
    ]},
    {"id": "tenure", "group": "생활", "title": "보증금은?", "options": [
        {"id": "a", "label": "목돈 묻어 두는 전세파", "hint": "큰 보증금을 맡기고 월세는 없어요", "set": {"tenure": "jeonse"}},
        {"id": "b", "label": "통장은 가볍게, 월세파", "hint": "보증금은 적게, 매달 월세를 내요", "set": {"tenure": "wolse"}},
    ]},
    {"id": "house", "group": "생활", "title": "우리 집 스타일은?", "options": [
        {"id": "a", "label": "관리사무소 아저씨와 인사하는 아파트파", "hint": "아파트 단지에 살아요", "set": {"house": "apt"}},
        {"id": "b", "label": "관리비 없는 빌라·원룸 자유인", "hint": "빌라·다세대·오피스텔·단독주택", "set": {"house": "other"}},
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
        {"id": "a", "label": "열대야엔 24시간 풀가동, 북극곰 모드", "hint": "여름밤 내내 에어컨 켜고 자요", "set": {"aircon": 1.5}},
        {"id": "b", "label": "선풍기와 의리, 에어컨은 손님 올 때만", "hint": "선풍기 위주, 에어컨은 가끔", "set": {"aircon": 0.9}},
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
        {"id": "a", "label": "버스 기사님과 인사하는 사이", "hint": "거의 매일 버스로 출퇴근", "set": {"trips": 44, "car": False}},
        {"id": "b", "label": "내 차와 한 몸, 운전대가 곧 출근 도장", "hint": "매일 자가용으로 출퇴근", "set": {"trips": 2, "car": True}},
    ]},
    {"id": "drive", "group": "생활", "title": "운전해서 가는 길은?", "show_if": {"transit": "b"}, "options": [
        {"id": "a", "label": "고속도로 타는 장거리 출퇴근러", "hint": "출퇴근길이 왕복 1시간을 넘어요",
         "set": {"km_factor": 1.5}},
        {"id": "b", "label": "회사가 코앞, 동네 한 바퀴 수준", "hint": "출퇴근길이 10~20분이면 끝",
         "set": {"km_factor": 0.6}},
    ]},
    # ── 생활편의 세부 질문: A를 고른 시설 지표만 순위에 반영 (INDICATORS) ──
    {"id": "has_kids", "group": "편의", "title": "우리 집에 아이가 있나요?", "show_if": {"living": "b"}, "options": [
        {"id": "a", "label": "있어요, 우리 집 꼬마 대장", "hint": "집에 아이가 있어요", "set": {"kids": True}},
        {"id": "b", "label": "없어요, 어른들만 오붓하게", "hint": "아이 없이 어른만 살아요", "set": {"kids": False}},
    ]},
    {"id": "kid_age", "group": "편의", "title": "우리 집 아이는?", "show_if": {"living": "b", "has_kids": "a"}, "options": [
        {"id": "a", "label": "아직 유치원 갈 나이, 뽀로로가 최고", "hint": "미취학 (만 3~5세 안팎)", "set": {"kid": "preschool"}},
        {"id": "b", "label": "학교 다니는 나이, 숙제 전쟁 중", "hint": "초·중·고 학생", "set": {"kid": "school"}},
    ]},
    {"id": "kinder", "group": "편의", "title": "유치원은?", "show_if": {**{"living": "b", "has_kids": "a"}, "kid_age": "a"}, "options": [
        {"id": "a", "label": "집 앞에 골라 보낼 만큼 넉넉해야", "hint": "걸어서 보낼 유치원을 골라 보내고 싶어요", "set": {"amenity": {"kinder": True}}},
        {"id": "b", "label": "한 곳만 있어도 OK, 차로 데려다줌", "hint": "차로 데려다줘도 괜찮아요", "set": {"amenity": {"kinder": False}}},
    ]},
    {"id": "elem", "group": "편의", "title": "초등학교는?", "show_if": {"living": "b", "has_kids": "a"}, "options": [
        {"id": "a", "label": "초품아 필수, 걸어서 등교", "hint": "아이가 걸어서 학교에 가요", "set": {"amenity": {"elem": True}}},
        {"id": "b", "label": "스쿨버스 타고 가도 괜찮아", "hint": "등교는 버스나 차로 해도 돼요", "set": {"amenity": {"elem": False}}},
    ]},
    {"id": "secondary", "group": "편의", "title": "중·고등학교는?", "show_if": {**{"living": "b", "has_kids": "a"}, "kid_age": "b"}, "options": [
        {"id": "a", "label": "학교 선택지가 많아야 마음이 편해", "hint": "학교를 골라 보내고 싶어요", "set": {"amenity": {"secondary": True}}},
        {"id": "b", "label": "가까운 한 곳이면 충분", "hint": "집 근처 학교면 충분해요", "set": {"amenity": {"secondary": False}}},
    ]},
    {"id": "academy", "group": "편의", "title": "학원은?", "show_if": {**{"living": "b", "has_kids": "a"}, "kid_age": "b"}, "options": [
        {"id": "a", "label": "학원가가 곧 경쟁력, 대치동 부럽지 않게", "hint": "학원 여러 곳을 다녀요", "set": {"amenity": {"academy": True}}},
        {"id": "b", "label": "인강과 문제집이면 충분", "hint": "학원은 거의 안 다녀요", "set": {"amenity": {"academy": False}}},
    ]},
    {"id": "library", "group": "편의", "title": "책은?", "options": [
        {"id": "a", "label": "도서관이 제2의 거실", "hint": "한 달에 몇 번은 도서관에 가요", "set": {"amenity": {"library": True}}},
        {"id": "b", "label": "책보다 유튜브가 편해", "hint": "책은 거의 안 읽어요", "set": {"amenity": {"library": False}}},
    ]},
    {"id": "museum", "group": "편의", "title": "전시회는?", "options": [
        {"id": "a", "label": "박물관·미술관 도장깨기가 취미", "hint": "주말마다 전시회를 찾아다녀요", "set": {"amenity": {"museum": True}}},
        {"id": "b", "label": "전시는 1년에 한 번이면 충분", "hint": "전시는 1년에 한두 번", "set": {"amenity": {"museum": False}}},
    ]},
    {"id": "arts", "group": "편의", "title": "취미·공연은?", "options": [
        {"id": "a", "label": "문화센터 강좌에 공연 관람까지", "hint": "공연 관람이나 취미 강좌를 즐겨요", "set": {"amenity": {"arts": True}}},
        {"id": "b", "label": "취미는 집에서 혼자 조용히", "hint": "집에서 쉬는 게 최고의 취미", "set": {"amenity": {"arts": False}}},
    ]},
    {"id": "park", "group": "편의", "title": "산책은?", "options": [
        {"id": "a", "label": "저녁마다 공원 한 바퀴, 없으면 못 살아", "hint": "매일 산책이나 운동을 해요", "set": {"amenity": {"park": True}}},
        {"id": "b", "label": "걷는 건 출퇴근으로 충분", "hint": "산책은 가끔", "set": {"amenity": {"park": False}}},
    ]},
    {"id": "pediatric", "group": "편의", "title": "소아과는?", "show_if": {"living": "b", "has_kids": "a"}, "options": [
        {"id": "a", "label": "열나면 바로 달려갈 소아과가 코앞에", "hint": "아이 병원에 자주 다녀요", "set": {"amenity": {"pediatric": True}}},
        {"id": "b", "label": "조금 멀어도 괜찮아, 튼튼이라서", "hint": "아이 병원은 가끔 가요", "set": {"amenity": {"pediatric": False}}},
    ]},
    {"id": "safety", "group": "편의", "title": "밤길은?", "options": [
        {"id": "a", "label": "야근 후 밤 11시에도 마음 편히 걸어야", "hint": "늦게까지 혼자 걸어 다녀요", "set": {"amenity": {"safety": True}}},
        {"id": "b", "label": "해 지면 집순이·집돌이", "hint": "해 지면 집에 있어요", "set": {"amenity": {"safety": False}}},
    ]},
    {"id": "hospital", "group": "편의", "title": "병원은?", "options": [
        {"id": "a", "label": "콧물만 나도 바로 병원·약국", "hint": "병원·약국이 가까워야 마음 편해요", "set": {"amenity": {"hospital": True}}},
        {"id": "b", "label": "웬만한 건 꿀물 한 잔으로 버팀", "hint": "아플 때만 찾아가요", "set": {"amenity": {"hospital": False}}},
    ]},
    {"id": "emergency", "group": "편의", "title": "응급실은?", "options": [
        {"id": "a", "label": "만약을 대비해 응급실이 가까워야", "hint": "지병이 있거나 어르신과 살아요", "set": {"amenity": {"emergency": True}}},
        {"id": "b", "label": "아직 팔팔해서 괜찮아", "hint": "아직 튼튼해요", "set": {"amenity": {"emergency": False}}},
    ]},
    {"id": "air", "group": "편의", "title": "공기는?", "options": [
        {"id": "a", "label": "미세먼지 앱 확인이 아침 루틴", "hint": "미세먼지 앱을 매일 봐요", "set": {"amenity": {"air": True}}},
        {"id": "b", "label": "공기 맛은 잘 모르겠어", "hint": "공기는 신경 안 써요", "set": {"amenity": {"air": False}}},
    ]},
    {"id": "capital", "group": "어디서", "title": "서울과의 거리는?", "options": [
        {"id": "a", "label": "수도권 아니면 안 돼, 한강 뷰는 못 참지", "hint": "서울·경기·인천에 살고 싶어요", "set": {"where": {"capital": True}}},
        {"id": "b", "label": "서울은 가끔 놀러 가면 충분", "hint": "어디든 괜찮아요", "set": {}},
    ]},
    {"id": "metro", "group": "어디서", "title": "도시의 크기는?", "options": [
        {"id": "a", "label": "광역시급 생활권, 지하철 소리가 자장가", "hint": "큰 도시의 편리함이 좋아요", "set": {"where": {"metro_area": True}}},
        {"id": "b", "label": "작은 도시도 시골도 다 좋아", "hint": "어디든 괜찮아요", "set": {}},
    ]},
    {"id": "sea", "group": "어디서", "title": "바다는?", "options": [
        {"id": "a", "label": "창문 열면 바다 냄새가 나야 해", "hint": "바닷가 동네에 살고 싶어요", "set": {"where": {"coastal": True}}},
        {"id": "b", "label": "바다는 여행 갈 때만 보면 충분", "hint": "어디든 괜찮아요", "set": {}},
    ]},
    {"id": "airport", "group": "어디서", "title": "비행기는?", "options": [
        {"id": "a", "label": "공항까지 1시간 안, 훌쩍 떠나는 게 낙", "hint": "해외여행·출장이 잦아요", "set": {"where": {"airport": True}}},
        {"id": "b", "label": "비행기는 1년에 한 번 탈까 말까", "hint": "비행기는 거의 안 타요", "set": {}},
    ]},
    {"id": "vibe", "group": "어디서", "title": "동네 분위기는?", "options": [
        {"id": "a", "label": "논밭과 산이 보이는 조용한 시골", "hint": "한적한 시골 마을이 좋아요", "set": {"where": {"rural": True}}},
        {"id": "b", "label": "사람 사는 곳이면 어디든 OK", "hint": "어디든 괜찮아요", "set": {}},
    ]},
    {"id": "mart", "group": "어디서", "title": "장 볼 때는?", "options": [
        {"id": "a", "label": "대형마트 카트를 끌어야 장 본 기분", "hint": "장은 대형마트에서 한 번에", "set": {"where": {"need_mart": True}}},
        {"id": "b", "label": "동네 슈퍼·시장이면 충분", "hint": "동네 슈퍼·시장에서 그때그때", "set": {}},
    ]},
    # 순위 기준 — 이 질문만 답이 3개 (결과 화면 맨 위 정렬 스위치와 같은 값)
    {"id": "sort", "group": "어디서", "title": "어떤 동네가 1등이면 좋겠어요?", "options": [
        {"id": "a", "label": "💰 한 푼이라도 아끼는 알뜰파", "hint": "생활비가 적게 드는 동네", "set": {"sort": "cheap"}},
        {"id": "b", "label": "⚖️ 너무 싸지도 비싸지도 않게", "hint": "전국 평균쯤의 무난한 동네", "set": {"sort": "middle"}},
        {"id": "c", "label": "💎 돈보다 여유, 프리미엄", "hint": "생활비가 높아도 누리는 게 많은 동네", "set": {"sort": "premium"}},
    ]},
]
SORT_LABEL = {"cheap": "알뜰한 순", "middle": "딱 중간", "premium": "프리미엄 순"}
DEFAULTS = {"living": "a", "family_size": "a", "tenure": "b", "house": "b", "shower": "b", "boiler": "b",
            "aircon": "b", "grocery": "b",
            "dining": "b", "trash": "b", "transit": "a", "capital": "b", "metro": "b", "sea": "b", "airport": "b",
            "vibe": "b", "mart": "b", "drive": "b",
            "has_kids": "b", "kid_age": "b", "kinder": "b", "elem": "b", "secondary": "b", "academy": "b",
            "library": "b", "museum": "b", "arts": "b", "park": "b",
            "pediatric": "b", "safety": "b", "hospital": "b", "emergency": "b", "air": "b", "sort": "a"}
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

ITEMS = ["housing", "mgmt", "electricity", "gas", "water", "dining", "grocery", "transit", "fuel", "trash"]
ITEM_LABEL = {"housing": "주거", "mgmt": "관리비", "electricity": "전기", "gas": "도시가스", "water": "상하수도",
              "dining": "외식", "grocery": "장보기", "transit": "버스", "fuel": "기름값", "trash": "쓰레기봉투"}
ITEM_SOURCE = {"housing": "molit_rent", "mgmt": "kapt_fee", "electricity": "kepco_house_power",
               "gas": "mois_public_fee", "water": "std_water_sewage_fee", "dining": "mois_dining",
               "grocery": "kca_price", "transit": "mois_public_fee", "fuel": "opinet_price",
               "trash": "std_trash_bag_price"}
# 화면 묶음 (카드 막대·범례는 묶음 4색, 펼치면 항목별)
GROUPS = [{"id": "home", "label": "주거"}, {"id": "energy", "label": "에너지·관리비"},
          {"id": "food", "label": "먹거리"}, {"id": "etc", "label": "교통·기타"}]
ITEM_GROUP = {"housing": "home", "mgmt": "energy", "electricity": "energy", "gas": "energy", "water": "energy",
              "dining": "food", "grocery": "food", "transit": "etc", "fuel": "etc", "trash": "etc"}
# 답에 따라 '해당 없음'인 항목 (0원, 시도 중위값으로 채우지 않음)
NOT_APPLICABLE = {"mgmt": lambda a: a["house"] != "apt", "fuel": lambda a: not a["car"]}


def amenity_weights(a):
    """세부 질문에서 A를 고른 시설 → 가중치. 합이 MAX_AMENITY_WEIGHT를 넘으면 같은 비율로 줄인다"""
    w = {k: INDICATORS[k][1] for k, on in a["amenity"].items() if on and k in INDICATORS}
    total = sum(w.values())
    if total > MAX_AMENITY_WEIGHT:
        w = {k: v * MAX_AMENITY_WEIGHT / total for k, v in w.items()}
    return w


def visible(q, ans):
    """앞 질문 답에 따라 이 질문을 보여 줄지 (show_if)"""
    return all(ans.get(k) == v for k, v in q.get("show_if", {}).items())


def normalize(answers):
    """답(질문 id → 'a'/'b') → 계산용 값. 잘못된 답은 ValueError"""
    raw = {**DEFAULTS, **{k: v for k, v in (answers or {}).items() if v is not None}}
    p = {"household": "solo", "tenure": "wolse", "house": "other", "shower": 1.0, "boiler": 1.0, "aircon": 1.0,
         "grocery": 1.0, "car": False, "km_factor": 1.0, "kids": False, "kid": None, "amenity": {}, "sort": "cheap",
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
            elif k == "amenity":
                p["amenity"].update(v)
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
        "fuel": ((r["gasoline_30d"] * CAR_KM_PER_MONTH * a["km_factor"] / FUEL_KM_PER_L
                  if r.get("gasoline_30d") else None) if a["car"] else 0),
        "water": r["water_sewer"] * hh["water"] * a["shower"] if r.get("water_sewer") else None,
        "gas": r["gas_total"] * hh["gas_units"] * a["boiler"] if r.get("gas_total") else None,
        "trash": r["trash_20l"] * a["bags"] * hh["trash"] if r.get("trash_20l") else None,
        "transit": r["bus_card"] * a["trips"] * hh["riders"] if r.get("bus_card") else None,
        "dining": r["meal_avg"] * a["meals"] * hh["eaters"] if r.get("meal_avg") else None,
        "grocery": (hh["grocery_base"] * a["grocery"] * r["grocery_index"] / 100
                    if r.get("grocery_index") else None),
    }
    return {k: (round(v) if v is not None else None) for k, v in out.items()}


GRAN_FIELD = {"housing": None, "mgmt": "mgmt_gran", "electricity": "power_gran", "fuel": "fuel_gran",
              "water": "water_sewer_gran",
              "gas": None, "trash": "trash_gran", "transit": None, "dining": "dining_gran", "grocery": "grocery_gran"}
SIDO_LEVEL = {"gas", "transit"}   # 원천 자체가 시도 평균


def _items(r, e, by_sido, nat, a):
    items = {}
    for k in ITEMS:
        v, filled = e[k], False
        if k in NOT_APPLICABLE and NOT_APPLICABLE[k](a):   # 빌라파의 관리비, 버스파의 기름값
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
            if v is not None and not (k in NOT_APPLICABLE and NOT_APPLICABLE[k](a)):
                by_sido.setdefault((r["sido"], k), []).append(v)
                nat.setdefault(k, []).append(v)
    everyone = []
    for r in regions:
        items = _items(r, est[r["region_code"]], by_sido, nat, a)
        everyone.append({"region_code": r["region_code"], "sido": r["sido"], "sigungu": r["sigungu"],
                         "total": sum(i["value"] for i in items.values()), "items": items, "_row": r})
    everyone.sort(key=lambda x: (x["total"], x["region_code"]))
    n = len(everyone)
    for i, x in enumerate(everyone, 1):
        x["national_rank"], x["national_pct"] = i, max(1, -(-i * 100 // n))   # 싼 순 상위 몇 %인지 (올림, 최소 1)
        x["national_count"] = n
        pct = 0.0 if n == 1 else 100.0 * (i - 1) / (n - 1)        # 0 = 가장 쌈, 100 = 가장 비쌈
        x["_cost_score"] = {"cheap": 100.0 - pct, "premium": pct,  # 순위 기준(sort)별 생활비 점수
                            "middle": 100.0 - 2 * abs(pct - 50)}[a["sort"]]

    # 생활편의 지표 점수: 결측은 같은 시도 중위값(없으면 전국 중위값)으로 채운다
    weights = amenity_weights(a)
    fields = ([(f"{g}_score", g) for g in GROUP_SCORES]
              + [(INDICATORS[k][0], k) for k in INDICATORS])
    for field, _ in fields:
        pool_sido, pool_nat = {}, []
        for x in everyone:
            v = x["_row"].get(field)
            if v is not None:
                pool_sido.setdefault(x["sido"], []).append(v)
                pool_nat.append(v)
        for x in everyone:
            v = x["_row"].get(field)
            filled = v is None
            if filled:
                pool = pool_sido.get(x["sido"]) or pool_nat
                v = median(pool) if pool else 50.0
            x.setdefault("_scores", {})[field] = (float(v), filled)
    wsum = sum(weights.values())
    for x in everyone:
        sc = x["_scores"]
        picked = [{"key": k, "label": INDICATORS[k][2], "weight": round(w, 3),
                   "score": round(sc[INDICATORS[k][0]][0], 1), "filled": sc[INDICATORS[k][0]][1]}
                  for k, w in weights.items()]
        x["scores"] = {
            "cost": round(x["_cost_score"], 1),
            **{g: round(sc[f"{g}_score"][0], 1) for g in GROUP_SCORES},
            **{f"{g}_filled": sc[f"{g}_score"][1] for g in GROUP_SCORES},
            "picked": picked,
            "total": round((1 - wsum) * x["_cost_score"]
                           + sum(w * sc[INDICATORS[k][0]][0] for k, w in weights.items()), 2),
            **{f"{g}_stars": x["_row"].get(f"{g}_stars") for g in GROUP_SCORES},
        }
    if weights or a["sort"] != "cheap":   # 종합 점수 순 (같으면 싼 곳 먼저). 알뜰·편의 없음이면 위의 생활비 순서 그대로
        everyone.sort(key=lambda x: (-x["scores"]["total"], x["total"], x["region_code"]))

    wanted = [w for w in WHERE if a["where"].get(w[0])]
    relaxed = []
    while True:
        results = [x for x in everyone if all(ok(x["_row"]) for _, _, ok in wanted)]
        if len(results) >= MIN_RESULTS or not wanted:
            break
        relaxed.append(wanted.pop(0)[1])
    out = []
    for i, x in enumerate(results, 1):
        out.append({**{k: v for k, v in x.items() if not k.startswith("_")}, "rank": i})
    hh = HOUSEHOLD[a["household"]]
    assumptions = {
        "rate": RATE, "household": hh,
        "params": {k: a[k] for k in ("tenure", "house", "shower", "boiler", "aircon", "grocery", "meals", "bags",
                                     "trips", "car", "km_factor")},
        "weights": {"cost": round(1 - wsum, 3), **{k: round(w, 3) for k, w in weights.items()}},
        "sort": a["sort"],
        "where": [label for key, label, _ in WHERE if a["where"].get(key) and label not in relaxed],
        "relaxed": relaxed,
        "notes": [
            "주거비는 최근 12개월 실거래 중위값이고, 전세는 보증금 이자(연 5.5%)로 환산했습니다. 아파트파는 아파트 거래만 보고, 아파트 거래가 적은 곳은 전체 유형 값을 씁니다.",
            "관리비(아파트파만)는 K-apt 관리비 공개 의무단지의 ㎡당 공용관리비+장기수선충당금 시군구 중위값에 공급면적(면적대 대표 전용면적 × 1.3, 가정)을 곱했습니다. 전기·수도·가스 같은 개별사용료는 다른 항목에 따로 있어 뺐습니다.",
            f"기름값(자가용 출퇴근파만)은 자가용 하루 평균 {CAR_KM_PER_DAY}km(한국교통안전공단 2025년 자동차주행거리 통계, 월 약 {CAR_KM_PER_MONTH:,}km)에 거리 답 배수를 곱하고, 연비 {FUEL_KM_PER_L:g}km/ℓ(가정)와 오피넷 시군구 보통휘발유 평균가로 계산했습니다. 주차비·보험·통행료는 빠져 있습니다.",
            "전기는 한전 시군구 가구 평균 월별 사용량(최근 12개월)에 가구원 수 배율(가정)과 여름 에어컨 답을 반영해, 달마다 주택용 누진 요금표(2024-07-01)로 계산하고, 지역의 한전 실제 평균 청구액에 맞춰 보정한 값입니다 (아파트 단일계약·복지할인 반영).",
            "상하수도는 기본요금이 빠져 있어 실제보다 조금 낮습니다.",
            "도시가스·버스는 시도 평균 요금, 외식비는 시도 평균 가격입니다. 가구원 수에 따른 외식비 배수는 가계동향조사 음식·숙박 지출 비율(1인 대비 2인 1.28배, 4인 2.43배)을 썼습니다.",
            "장보기는 가구원 수별 식료품비(국가데이터처 가계동향조사 2026년 1~2분기)에 지역 장바구니 지수를 곱한 값입니다 (대형마트·SSM 기준).",
            "물 사용량은 1인 하루 196.6ℓ(2024년 상수도 통계 가정용), 도시가스는 가구당 연 559.6㎥(한국가스공사 2022년)를 기준으로 했습니다. 가스의 가구원 수별 차이는 추정입니다.",
            "바다는 해안선이 3km 이상인 시군구, 공항은 가장 가까운 공항까지 직선 40km 이내(도로 약 1.3배, 차로 1시간 안팎), 광역시 생활권은 특별·광역시와 그와 맞닿은 시군구입니다.",
            (f"순위 기준은 「{SORT_LABEL[a['sort']]}」입니다 (알뜰: 쌀수록, 프리미엄: 비쌀수록, 딱 중간: 전국 가운데에 가까울수록 생활비 점수가 높음). "
             + "순위는 생활비 점수 " + f"{round((1 - wsum) * 100)}%"
             + "".join(f" + {INDICATORS[k][2]} {round(w * 100)}%" for k, w in weights.items())
             + "로 매겼습니다. 시설 점수는 학교·학원(나이스), 유치원(유치원알리미), 도서관·박물관·미술관·문예회관(문화기반시설총람), 공원(도시공원 표준데이터), 병원·의원·약국(국립중앙의료원)을 인구 대비 비율과 면적(㎢) 대비 밀도를 전국과 비교해 반반 섞은 0~100점입니다. 소아과는 이름에 소아·어린이·아동이 든 병·의원입니다."),
            "응급실 거리는 시군구 안쪽 대표점에서 가장 가까운 응급의료기관까지 직선거리라, 넓은 군에서는 실제 거리와 다를 수 있습니다. 치안은 경찰청 시군구별 강력·절도·폭력범죄 발생 건수를 주민 수로 나눈 값이라, 사람이 많이 오가는 도심·관광지는 실제보다 불리하게 나옵니다. 공기는 에어코리아 시군구별 초미세먼지(PM2.5) 1시간 값을 날마다 쌓은 평균입니다(확정 전 자료). 쌓인 기간이 30일이 안 되는 동안은 공기 점수를 모든 지역에 같게(중위값) 둡니다.",
            "모든 값은 추정치이며 실제와 다를 수 있습니다.",
        ],
    }
    return out, a, assumptions
