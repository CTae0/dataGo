"""질문지 → 월 생활비 추정 모델 테스트 (DB 없이 표본 행으로). 실행: python -m pytest tests -q"""
import pytest

from api import cost_model as cm

# /api/regions 행에서 모델이 쓰는 칸만 (값은 실제 마트 값과 비슷하게)
CHUNCHEON = {"region_code": "51110", "sido": "강원", "sigungu": "춘천시",
             "deals_s": 500, "deals_m": 300, "deals_l": 200, "jeonse_deals_s": 100, "jeonse_deals_m": 100, "jeonse_deals_l": 100,
             "cost_s": 40.6, "cost_m": 57.3, "cost_l": 103.2, "jeonse_s": 7000.0, "jeonse_m": 12700.0, "jeonse_l": 22500.0,
             "water_sewer": 24000.0, "water_sewer_gran": "exact", "gas_total": 12618.0, "trash_20l": 470.0, "trash_gran": "exact",
             "bus_card": 1291.0, "meal_avg": 9300.0, "dining_gran": "sido", "grocery_index": 102.7, "grocery_gran": "exact",
             "grocery_stores": 2}
GANGNAM = {"region_code": "11680", "sido": "서울", "sigungu": "강남구",
           "deals_s": 500, "deals_m": 300, "deals_l": 200, "jeonse_deals_s": 100, "jeonse_deals_m": 100, "jeonse_deals_l": 100,
           "cost_s": 96.6, "cost_m": 150.0, "cost_l": 389.6, "jeonse_s": 27000.0, "jeonse_m": 50000.0, "jeonse_l": 85000.0,
           "water_sewer": 22280.0, "water_sewer_gran": "sido", "gas_total": 11624.0, "trash_20l": 490.0, "trash_gran": "exact",
           "bus_card": 1500.0, "meal_avg": 10277.0, "dining_gran": "sido", "grocery_index": 102.6, "grocery_gran": "exact",
           "grocery_stores": 14}
YANGYANG = {"region_code": "51830", "sido": "강원", "sigungu": "양양군",
            "deals_s": 40, "deals_m": 0, "deals_l": 0, "jeonse_deals_s": 3,
            "cost_s": 35.0, "cost_m": None, "cost_l": None, "jeonse_s": None, "jeonse_m": None, "jeonse_l": None,
            "water_sewer": 30000.0, "water_sewer_gran": "exact", "gas_total": 12618.0, "trash_20l": 420.0, "trash_gran": "exact",
            "bus_card": 1291.0, "meal_avg": 9300.0, "dining_gran": "sido", "grocery_index": None, "grocery_gran": None,
            "grocery_stores": 0}
REGIONS = [CHUNCHEON, GANGNAM, YANGYANG]


def answers(**kw):
    return cm.normalize(kw)


def test_chuncheon_solo_wolse_by_hand():
    e = cm.estimate(CHUNCHEON, answers(household="solo", tenure="wolse"))
    assert e["housing"] == 406_000                         # 40.6만 원
    assert e["water"] == round(24000 * 0.5 * 1.0)          # 1인 배율 0.5, 평범한 샤워
    assert e["gas"] == round(12618 * 2.5 * 1.0)            # 516MJ 2.5단위
    assert e["trash"] == round(470 * 4 * 1.0)              # 주 1장
    assert e["transit"] == round(1291 * 44 * 1)            # 출퇴근
    assert e["dining"] == round(9300 * 12 * 1)             # 주 2~4회
    assert e["grocery"] == round(220_000 * 1.0 * 1.027)


def test_gangnam_family_jeonse_by_hand():
    e = cm.estimate(GANGNAM, answers(household="family", tenure="jeonse"))
    assert e["housing"] == round(85000 * 10_000 * 0.055 / 12)
    assert e["dining"] == round(10277 * 12 * 3)            # 아이 둘 ≈ 어른 한 명 → 3인분
    assert e["transit"] == round(1500 * 44 * 2)


def test_any_tenure_takes_cheaper():
    e = cm.estimate(CHUNCHEON, answers(tenure="any"))
    assert e["housing"] == min(406_000, round(7000 * 10_000 * 0.055 / 12))


@pytest.mark.parametrize("qid,low,high,item", [("shower", "quick", "waterpark", "water"),
                                                ("boiler", "low", "sauna", "gas")])
def test_factor_changes_only_its_item(qid, low, high, item):
    a, b = cm.estimate(CHUNCHEON, answers(**{qid: low})), cm.estimate(CHUNCHEON, answers(**{qid: high}))
    for k in cm.ITEMS:
        if k == item:
            ratio = cm._opt(qid, high)["factor"] / cm._opt(qid, low)["factor"]
            assert b[k] == pytest.approx(a[k] * ratio, rel=1e-3)
        else:
            assert a[k] == b[k]


def test_missing_items_filled_with_sido_median_and_flagged():
    res, _, _ = cm.recommend(REGIONS, {"household": "duo"})
    y = next(x for x in res if x["region_code"] == "51830")
    assert y["items"]["housing"]["filled"] is True        # 양양 cost_m 없음 → 강원(춘천) 값
    assert y["items"]["housing"]["value"] == round(57.3 * 10_000)
    assert y["items"]["grocery"]["filled"] is True
    assert y["total"] == sum(i["value"] for i in y["items"].values())


def test_sorted_and_filters():
    res, _, _ = cm.recommend(REGIONS, {})
    assert [x["total"] for x in res] == sorted(x["total"] for x in res)
    assert [x["rank"] for x in res] == [1, 2, 3]
    only_gw, _, _ = cm.recommend(REGIONS, {"sidos": ["강원"]})
    assert {x["sido"] for x in only_gw} == {"강원"}
    mart, _, _ = cm.recommend(REGIONS, {"need_mart": True})
    assert "51830" not in {x["region_code"] for x in mart}
    capped, _, _ = cm.recommend(REGIONS, {"tenure": "wolse", "housing_cap": 50})
    assert {x["region_code"] for x in capped} == {"51110", "51830"}


def test_same_answers_same_result():
    assert cm.recommend(REGIONS, {"dining": "outside"})[0] == cm.recommend(REGIONS, {"dining": "outside"})[0]


def test_every_option_has_hint_and_coefficient():
    coef = {"household": None, "tenure": None, "shower": "factor", "boiler": "factor", "grocery": "factor",
            "dining": "meals", "trash": "bags", "transit": "trips"}
    for q in cm.QUESTIONS:
        if q["kind"] != "single":
            assert all(f.get("hint") for f in q["fields"])
            continue
        for o in q["options"]:
            assert o["label"] and o["hint"], (q["id"], o["id"])
            if coef[q["id"]]:
                assert isinstance(o[coef[q["id"]]], (int, float)), (q["id"], o["id"])
        assert cm.DEFAULTS[q["id"]] in {o["id"] for o in q["options"]}
    assert set(cm.HOUSEHOLD) == {o["id"] for o in cm.QUESTIONS[0]["options"]}


def test_bad_option_rejected():
    with pytest.raises(ValueError):
        cm.normalize({"shower": "bathtub"})


def test_thin_samples_are_treated_as_missing():
    # 양양 1인: 월세 거래 40건(믿음), 전세 3건(안 믿음) → '싼 쪽' 이어도 전세 값을 쓰지 않는다
    e = cm.estimate(YANGYANG, answers(household="solo", tenure="any"))
    assert e["housing"] == 350_000
    thin = {**CHUNCHEON, "deals_s": cm.MIN_DEALS - 1}
    assert cm.estimate(thin, answers(household="solo", tenure="wolse"))["housing"] is None
