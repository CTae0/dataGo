from api.power_tariff import bill


def test_tariff_example3_other_season_450kwh():
    # 한전 주택용 전기요금표(2024-07-01) '요금계산 예시3': 기타계절 450kWh → 108,530원
    assert bill(450, month=3) == 108_530


def test_summer_tiers_are_wider():
    # 같은 350kWh도 여름(7~8월)은 2단계 구간이 넓어 더 싸다
    assert bill(350, month=8) < bill(350, month=3)


def test_base_fee_follows_usage_tier():
    assert bill(0, month=3) == bill(0, month=8)
    assert bill(201, month=3) - bill(200, month=3) > 600   # 기본요금 910 → 1,600 원으로 바뀜


def test_super_user_only_in_peak_months():
    assert bill(1_100, month=1) > bill(1_100, month=4)
