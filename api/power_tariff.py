"""
주택용 전기요금(저압) 계산 — 한국전력공사 주택용 전기요금표, 2024-07-01 시행
  원천: data.go.kr 15090700 「한국전력공사_주택용 전기요금표」 (hwpx 안 그림, data/stage1/15090700)
  요금표가 바뀌면 아래 상수만 고친다. 요금표의 '요금계산 예시3'(450kWh, 기타계절 → 108,530원)을 테스트로 확인한다.

청구금액 = 기본요금 + 전력량요금 + 기후환경요금 ± 연료비조정요금 + 부가가치세(10%) + 전력산업기반기금(3.2%)
  - 기본요금은 그 달 사용량이 속한 구간 하나의 값 (누진 아님)
  - 전력량요금은 구간별 누진 (원 미만 절사)
  - 부가세 원 미만 반올림, 기금 10원 미만 절사, 청구액 10원 미만 절사
  - 슈퍼유저 요금(겨울 12~2월·여름 7~8월 1,000kWh 초과분 736.2원)은 반영한다
  - 복지할인(장애인·기초수급·다자녀·출산 가구 등)은 반영하지 않는다
"""

# (구간 상한 kWh, 기본요금 원/호, 전력량요금 원/kWh)
TIERS_OTHER = [(200, 910, 120.0), (400, 1_600, 214.6), (None, 7_300, 307.3)]     # 1~6월, 9~12월
TIERS_SUMMER = [(300, 910, 120.0), (450, 1_600, 214.6), (None, 7_300, 307.3)]    # 7~8월
CLIMATE_PER_KWH = 9       # 기후환경요금 (원/kWh, 매년 바뀔 수 있음)
FUEL_ADJ_PER_KWH = 5      # 연료비조정요금 (원/kWh, 분기마다 ±5 안에서 바뀜. 요금표 예시 기준 +5)
VAT = 0.10
FUND = 0.032              # 전력산업기반기금
SUPER_USER_KWH = 1_000
SUPER_USER_RATE = 736.2
SUMMER_MONTHS = {7, 8}
SUPER_USER_MONTHS = {12, 1, 2, 7, 8}


def bill(kwh, month=None):
    """한 가구 한 달 사용량(kWh) → 청구금액(원). month(1~12)가 7·8이면 하계 구간."""
    kwh = max(0.0, float(kwh))
    tiers = TIERS_SUMMER if month in SUMMER_MONTHS else TIERS_OTHER
    base, energy, lower = 0, 0.0, 0
    for upper, base_fee, rate in tiers:
        top = kwh if upper is None else min(kwh, upper)
        if top > lower:
            energy += (top - lower) * rate
        if upper is None or kwh <= upper:
            base = base_fee
            break
        lower = upper
    if month in SUPER_USER_MONTHS and kwh > SUPER_USER_KWH:
        energy += (kwh - SUPER_USER_KWH) * (SUPER_USER_RATE - tiers[-1][2])
    energy = int(energy)                                   # 원 미만 절사
    subtotal = base + energy + int(kwh * CLIMATE_PER_KWH) + int(kwh * FUEL_ADJ_PER_KWH)
    vat = int(subtotal * VAT + 0.5)                        # 원 미만 반올림
    fund = int(subtotal * FUND) // 10 * 10                 # 10원 미만 절사
    return (subtotal + vat + fund) // 10 * 10              # 10원 미만 절사


def bill_year_avg(kwh_by_month):
    """{월: kWh} → 월평균 청구금액. 계절마다 구간이 달라서 달마다 따로 계산해 평균 낸다."""
    vals = [bill(k, m) for m, k in kwh_by_month.items()]
    return sum(vals) / len(vals) if vals else 0
