"""질문지 → 월 생활비 추정 모델 테스트 (DB 없이 표본 행으로). 실행: python -m pytest tests -q"""
import pytest

from api import cost_model as cm
from api import describe

# /api/regions 행에서 모델이 쓰는 칸만 (값은 실제 마트 값과 비슷하게) + mart.region_features 칸
CHUNCHEON = {"region_code": "51110", "sido": "강원", "sigungu": "춘천시", "sigungu_type": "시",
             "deals_s": 500, "deals_m": 300, "deals_l": 200, "jeonse_deals_s": 100, "jeonse_deals_m": 100, "jeonse_deals_l": 100,
             "cost_s": 40.6, "cost_m": 57.3, "cost_l": 103.2, "jeonse_s": 7000.0, "jeonse_m": 12700.0, "jeonse_l": 22500.0,
             "water_sewer": 24000.0, "water_sewer_gran": "exact", "gas_total": 12618.0, "trash_20l": 470.0, "trash_gran": "exact",
             "bus_card": 1291.0, "meal_avg": 9300.0, "dining_gran": "sido", "grocery_index": 102.7, "grocery_gran": "exact",
             "grocery_stores": 2, "is_coastal": False, "coast_km": 0, "is_capital": False, "is_metro_area": False,
             "airport_name": "원주공항", "airport_km": 51.4, "archetype": "small_city"}
GANGNAM = {"region_code": "11680", "sido": "서울", "sigungu": "강남구", "sigungu_type": "구",
           "deals_s": 500, "deals_m": 300, "deals_l": 200, "jeonse_deals_s": 100, "jeonse_deals_m": 100, "jeonse_deals_l": 100,
           "cost_s": 96.6, "cost_m": 150.0, "cost_l": 389.6, "jeonse_s": 27000.0, "jeonse_m": 50000.0, "jeonse_l": 85000.0,
           "water_sewer": 22280.0, "water_sewer_gran": "sido", "gas_total": 11624.0, "trash_20l": 490.0, "trash_gran": "exact",
           "bus_card": 1500.0, "meal_avg": 10277.0, "dining_gran": "sido", "grocery_index": 102.6, "grocery_gran": "exact",
           "grocery_stores": 14, "is_coastal": False, "coast_km": 0, "is_capital": True, "is_metro_area": True,
           "airport_name": "김포공항", "airport_km": 25.0, "archetype": "metropolis"}
YANGYANG = {"region_code": "51830", "sido": "강원", "sigungu": "양양군", "sigungu_type": "군",
            "deals_s": 40, "deals_m": 0, "deals_l": 0, "jeonse_deals_s": 3,
            "cost_s": 35.0, "cost_m": None, "cost_l": None, "jeonse_s": None, "jeonse_m": None, "jeonse_l": None,
            "water_sewer": 30000.0, "water_sewer_gran": "exact", "gas_total": 12618.0, "trash_20l": 420.0, "trash_gran": "exact",
            "bus_card": 1291.0, "meal_avg": 9300.0, "dining_gran": "sido", "grocery_index": None, "grocery_gran": None,
            "grocery_stores": 0, "is_coastal": True, "coast_km": 21.0, "is_capital": False, "is_metro_area": False,
            "airport_name": "양양공항", "airport_km": 8.0, "archetype": "seaside_village"}
REGIONS = [CHUNCHEON, GANGNAM, YANGYANG]
SOLO = {"living": "a"}
DUO = {"living": "b", "family_size": "a"}
FAMILY = {"living": "b", "family_size": "b"}


def ans(**kw):
    return cm.normalize(kw)


def test_chuncheon_solo_wolse_by_hand():
    # 기본 답: 월세(b), 3분 샤워(b, 0.8), 전기장판(b, 0.7), 생수 냉장고(b, 0.6), 집밥(b, 4끼), 미니멀(b, 2장), 버스(a, 44회)
    e = cm.estimate(CHUNCHEON, ans(**SOLO))
    assert e["housing"] == 406_000                                 # 40.6만 원
    assert e["water"] == round(24000 * 0.299 * 0.8)                # 1인 196.6ℓ/일 → 20㎥의 0.299배 × 3분 샤워
    assert e["gas"] == round(12618 * 2.63 * 0.7)                   # 평균 가구 3.86단위 × √1/√2.16 × 전기장판
    assert e["trash"] == round(470 * 2 * 1.0)
    assert e["transit"] == round(1291 * 44 * 1)
    assert e["dining"] == round(9300 * 4 * 1)
    assert e["grocery"] == round(241_000 * 0.6 * 1.027)


def test_gangnam_family_jeonse_by_hand():
    e = cm.estimate(GANGNAM, ans(**FAMILY, tenure="a", dining="a"))
    assert e["housing"] == round(85000 * 10_000 * 0.055 / 12)
    assert e["dining"] == round(10277 * 25 * 2.43)                 # 배달앱 VVIP × 가계동향 4인 외식 배수
    assert e["transit"] == round(1500 * 44 * 2)


def test_family_question_only_when_living_together():
    assert "family_size" not in ans(**SOLO)["answers"]             # 혼자 살면 묻지 않음
    assert ans(living="a", family_size="b")["household"] == "solo"  # 숨은 질문의 답은 무시
    assert ans(**DUO)["household"] == "duo" and ans(**FAMILY)["household"] == "family"


@pytest.mark.parametrize("qid,item", [("shower", "water"), ("boiler", "gas"), ("grocery", "grocery"), ("aircon", "electricity"),
                                      ("dining", "dining"), ("trash", "trash"), ("transit", "transit,fuel")])
def test_each_lifestyle_question_moves_only_its_item(qid, item):
    a, b = cm.estimate(CHUNCHEON_FULL, ans(**{qid: "a"})), cm.estimate(CHUNCHEON_FULL, ans(**{qid: "b"}))
    for k in cm.ITEMS:
        assert (a[k] != b[k]) == (k in item.split(",")), (qid, k)   # 출퇴근: 버스파 ↔ 자가용파 (버스·기름값)


def test_missing_items_filled_with_sido_median_and_flagged():
    res, _, _ = cm.recommend(REGIONS, DUO)
    y = next(x for x in res if x["region_code"] == "51830")
    assert y["items"]["housing"]["filled"] is True                 # 양양 2인 거래 없음 → 강원(춘천) 값
    assert y["items"]["housing"]["value"] == round(57.3 * 10_000)
    assert y["items"]["grocery"]["filled"] is True
    assert y["total"] == sum(i["value"] for i in y["items"].values())


def test_thin_samples_are_treated_as_missing():
    thin = {**CHUNCHEON, "deals_s": cm.MIN_DEALS - 1}
    assert cm.estimate(thin, ans(**SOLO))["housing"] is None
    jeon_thin = cm.estimate(YANGYANG, ans(**SOLO, tenure="a"))      # 전세 3건 → 믿지 않음
    assert jeon_thin["housing"] is None


def test_where_questions_filter_regions():
    sea = {x["region_code"] for x in cm.recommend(REGIONS, {"sea": "a"})[0]}
    capital = {x["region_code"] for x in cm.recommend(REGIONS, {"capital": "a"})[0]}
    assert sea == {"51830"} or cm.MIN_RESULTS > 1                    # 3곳 미만이면 조건이 풀린다 (아래 테스트)
    big = REGIONS + [{**YANGYANG, "region_code": f"9{i:04d}", "sigungu": f"바닷가{i}"} for i in range(3)]
    sea_big = {x["region_code"] for x in cm.recommend(big, {"sea": "a"})[0]}
    assert "11680" not in sea_big and "51110" not in sea_big
    rural = {x["region_code"] for x in cm.recommend(big, {"vibe": "a"})[0]}
    assert all(r.startswith("9") or r == "51830" for r in rural)
    air = {x["region_code"] for x in cm.recommend(big, {"airport": "a"})[0]}
    assert "51110" not in air                                      # 춘천: 원주공항까지 51km
    assert capital                                                  # 결과는 늘 비지 않는다


def test_too_strict_conditions_are_relaxed_and_reported():
    res, _, asm = cm.recommend(REGIONS, {"sea": "a", "capital": "a", "mart": "a"})
    assert len(res) >= cm.MIN_RESULTS
    assert asm["relaxed"] and asm["relaxed"][0] == "대형마트"         # WHERE 앞쪽부터 뺀다


def test_sorted_ranks_and_national_percentile():
    res, _, _ = cm.recommend(REGIONS, SOLO)
    assert [x["total"] for x in res] == sorted(x["total"] for x in res)
    assert [x["rank"] for x in res] == [1, 2, 3]
    assert [x["national_rank"] for x in res] == [1, 2, 3] and res[-1]["national_pct"] == 100


def test_same_answers_same_result():
    assert cm.recommend(REGIONS, {"dining": "a"})[0] == cm.recommend(REGIONS, {"dining": "a"})[0]


def test_every_question_has_two_funny_options_with_hint_and_effect():
    seen = set()
    for q in cm.QUESTIONS:
        assert q["id"] not in seen and q["title"]
        seen.add(q["id"])
        assert [o["id"] for o in q["options"]] == ["a", "b"], q["id"]
        for o in q["options"]:
            assert o["label"] and o["hint"], (q["id"], o["id"])
        assert any(o["set"] for o in q["options"]), q["id"]         # 답이 무언가를 바꾼다
        assert cm.DEFAULTS[q["id"]] in ("a", "b")
    where_keys = {k for q in cm.QUESTIONS for o in q["options"] for k in o["set"].get("where", {})}
    assert where_keys == {w[0] for w in cm.WHERE}


def test_bad_answer_rejected():
    with pytest.raises(ValueError):
        cm.normalize({"shower": "bathtub"})


def test_baselines_follow_official_sources():
    # 가계동향조사 KOSIS DT_1L9U105 (2026.1~2/4 평균), 상수도통계 2024 가정용 196.6ℓ, 가스공사 2022 559.6㎥/년
    assert [cm.HOUSEHOLD[k]["grocery_base"] for k in ("solo", "duo", "family")] == [241_000, 464_700, 681_400]
    assert [cm.HOUSEHOLD[k]["water"] for k in ("solo", "duo", "family")] == [0.299, 0.598, 1.196]
    assert [cm.HOUSEHOLD[k]["gas_units"] for k in ("solo", "duo", "family")] == [2.63, 3.71, 5.25]
    assert [cm.HOUSEHOLD[k]["eaters"] for k in ("solo", "duo", "family")] == [1.0, 1.28, 2.43]   # 11.음식·숙박 비율
    assert cm._gas_units(cm.AVG_HOUSEHOLD_SIZE) == pytest.approx(3.86, abs=0.01)


def test_card_text_and_level():
    res, _, _ = cm.recommend(REGIONS, SOLO)
    c = describe.card(res[0], next(r for r in REGIONS if r["region_code"] == res[0]["region_code"]))
    assert c["archetype"] in describe.ARCHETYPE and c["nickname"] and c["text"]
    assert res[0]["sigungu"] in c["text"] and "만 원" in c["text"]
    assert describe.level(5)["name"] == "통장 수비 만렙" and describe.level(100)["name"] == "지갑 주의보"
    sea = describe.card(res[0], YANGYANG)
    assert any("해안선" in f for f in sea["facts"]) and any("양양공항" in f for f in sea["facts"])


# ── 전기·관리비·집 유형 (2026-10-22) ──────────────────────────
KWH = {f"kwh_m{m:02d}": (320.0 if m in (7, 8) else 240.0) for m in range(1, 13)}
CHUNCHEON_FULL = {**CHUNCHEON, **KWH, "power_gran": "exact", "mgmt_per_m2": 1380.0, "mgmt_gran": "exact",
                  "gasoline_30d": 1841.0, "fuel_gran": "exact",
                  "cost_apt_s": 55.0, "deals_apt_s": 120, "jeonse_apt_s": 9000.0, "jeonse_deals_apt_s": 50}


def test_electricity_by_hand_with_tariff():
    from api.power_tariff import bill
    e = cm.estimate(CHUNCHEON_FULL, ans(**SOLO))                    # 1인 0.68배, 에어컨 b 0.9배(여름만)
    hand = sum(bill(v * 0.68 * (0.9 if m in (7, 8) else 1.0), m)
               for m, v in ((int(k[-2:]), x) for k, x in KWH.items())) / 12
    assert e["electricity"] == round(hand)                          # power_bill 없음 → 보정 1.0


def test_aircon_changes_only_summer_electricity():
    a = cm.estimate(CHUNCHEON_FULL, ans(aircon="a"))
    b = cm.estimate(CHUNCHEON_FULL, ans(aircon="b"))
    assert a["electricity"] > b["electricity"]
    assert all(a[k] == b[k] for k in cm.ITEMS if k != "electricity")
    winter_only = {**CHUNCHEON_FULL, "kwh_m07": None}                # 달 하나라도 없으면 계산하지 않음 → 채움 대상
    assert cm.estimate(winter_only, ans())["electricity"] is None


def test_house_question_adds_mgmt_and_switches_to_apartment_rent():
    villa = cm.estimate(CHUNCHEON_FULL, ans(**SOLO, house="b"))
    apt = cm.estimate(CHUNCHEON_FULL, ans(**SOLO, house="a"))
    assert villa["mgmt"] == 0 and villa["housing"] == 406_000
    assert apt["mgmt"] == round(1380 * 33 * 1.3)                       # ㎡당 × (대표 전용 33㎡ × 1.3)
    assert apt["housing"] == 550_000                                   # 아파트 월세 중위값
    thin = {**CHUNCHEON_FULL, "deals_apt_s": cm.MIN_DEALS - 1}       # 아파트 거래가 적으면 전체 유형 값
    assert cm.estimate(thin, ans(**SOLO, house="a"))["housing"] == 406_000


def test_mgmt_not_applicable_is_zero_and_not_filled():
    regions = [CHUNCHEON_FULL, {**GANGNAM, **KWH, "mgmt_per_m2": None}, YANGYANG]
    res, _, _ = cm.recommend(regions, {**SOLO, "house": "b"})
    for x in res:
        assert x["items"]["mgmt"]["value"] == 0 and x["items"]["mgmt"].get("na")
    res, _, _ = cm.recommend(regions, {**SOLO, "house": "a"})
    g = next(x for x in res if x["region_code"] == "11680")
    assert g["items"]["mgmt"]["filled"] and g["items"]["mgmt"]["value"] == round(1380 * 33 * 1.3)  # 다른 지역 값으로 채움
    assert all(x["items"][k]["group"] == cm.ITEM_GROUP[k] for x in res for k in cm.ITEMS)
    assert {g["id"] for g in cm.GROUPS} == set(cm.ITEM_GROUP.values())


def test_electricity_calibrated_to_kepco_average_bill():
    from api.power_tariff import bill
    base = sum(bill(v, int(k[-2:])) for k, v in KWH.items()) / 12
    r = {**CHUNCHEON_FULL, "power_bill": round(base * 0.85)}          # 실제 청구액이 요금표보다 15% 낮은 지역
    avg_household = cm._electricity(r, {"elec": 1.0}, 1.0)
    assert avg_household == pytest.approx(r["power_bill"], abs=1)     # 평균 가구 = 한전 평균 청구액
    assert cm._electricity(r, {"elec": 1.36}, 1.5) > avg_household * 1.36   # 누진: 많이 쓰면 비례보다 더 비싸다


def test_car_commute_adds_fuel_by_hand_and_drive_question_only_for_drivers():
    assert cm.CAR_KM_PER_MONTH == 937                                 # 교통안전공단 2025 비사업용 30.8km/일
    bus = cm.estimate(CHUNCHEON_FULL, ans(**SOLO, transit="a"))
    assert bus["fuel"] == 0
    assert "drive" not in ans(**SOLO, transit="a")["answers"]          # 버스파에겐 운전 거리를 묻지 않음
    far = cm.estimate(CHUNCHEON_FULL, ans(**SOLO, transit="b", drive="a"))
    near = cm.estimate(CHUNCHEON_FULL, ans(**SOLO, transit="b", drive="b"))
    assert far["fuel"] == round(1841 * 937 * 1.5 / 12) and near["fuel"] == round(1841 * 937 * 0.6 / 12)
    assert far["transit"] == near["transit"] == round(1291 * 2 * 1)     # 차로 다니면 버스는 월 2회


def test_fuel_not_applicable_for_bus_riders_and_filled_for_drivers():
    regions = [CHUNCHEON_FULL, {**GANGNAM, **KWH, "gasoline_30d": None}, YANGYANG]
    res, _, _ = cm.recommend(regions, {**SOLO, "transit": "a"})
    assert all(x["items"]["fuel"]["value"] == 0 and x["items"]["fuel"].get("na") for x in res)
    res, _, _ = cm.recommend(regions, {**SOLO, "transit": "b"})
    g = next(x for x in res if x["region_code"] == "11680")
    assert g["items"]["fuel"]["filled"] and g["items"]["fuel"]["value"] > 0


# ── 생활편의 점수 섞기 (교육·문화) ────────────────────────────
def _scored(regions_scores):
    return [{**r, "edu_score": e, "culture_score": c} for r, (e, c) in regions_scores]


def test_zero_weights_keep_cost_order():
    regions = _scored([(CHUNCHEON, (90, 90)), (GANGNAM, (10, 10)), (YANGYANG, (50, 50))])
    res, a, asm = cm.recommend(regions, SOLO)                       # 주말 b(기본) · 학교 질문 없음
    assert a["w_edu"] == 0 and a["w_culture"] == 0
    assert [x["total"] for x in res] == sorted(x["total"] for x in res)
    assert asm["weights"] == {"cost": 1.0, "edu": 0.0, "culture": 0.0}


def test_culture_answer_lifts_high_culture_region():
    # 춘천이 조금 비싸지만 문화 점수가 훨씬 높게 → 주말 A면 1위가 바뀐다
    cheap = {**CHUNCHEON, "region_code": "90001", "sigungu": "싼군", "cost_s": 30.0}
    rich = {**CHUNCHEON, "region_code": "90002", "sigungu": "문화시", "cost_s": 32.0}
    filler = [({**GANGNAM, "region_code": f"91{i:03d}", "sigungu": f"비싼구{i}"}, (50, 50)) for i in range(20)]
    regions = _scored([(cheap, (50, 5)), (rich, (50, 95))] + filler)   # 실제처럼 이웃 순위끼리 생활비 점수 차이가 작게
    base, _, _ = cm.recommend(regions, SOLO)
    blend, _, asm = cm.recommend(regions, {**SOLO, "weekend": "a"})
    assert base[0]["sigungu"] == "싼군" and blend[0]["sigungu"] == "문화시"
    assert asm["weights"]["culture"] == cm.W_CULTURE
    s = blend[0]["scores"]
    assert s["total"] == pytest.approx((1 - cm.W_CULTURE) * s["cost"] + cm.W_CULTURE * s["culture"], abs=0.1)   # cost는 반올림 값
    assert blend[0]["national_rank"] == 2                              # 생활비 순위 배지는 그대로 생활비 기준


def test_school_question_only_for_families():
    assert "school" not in ans(**SOLO)["answers"] and "school" not in ans(**DUO)["answers"]
    assert ans(**FAMILY, school="a")["w_edu"] == cm.W_EDU
    assert ans(**SOLO, school="a")["w_edu"] == 0                       # 숨은 질문의 답은 무시


def test_missing_scores_filled_with_sido_median_and_flagged():
    regions = _scored([(CHUNCHEON, (80, 60)), (GANGNAM, (40, 40)), (YANGYANG, (None, None))])
    res, _, _ = cm.recommend(regions, {**FAMILY, "school": "a", "weekend": "a"})
    y = next(x for x in res if x["region_code"] == "51830")
    assert y["scores"]["edu"] == 80 and y["scores"]["edu_filled"]       # 강원(춘천) 값으로 채움
    assert y["scores"]["culture"] == 60 and y["scores"]["culture_filled"]
