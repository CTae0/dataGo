-- 지역 데이터는 pipeline/dim_region.py가 채운다 (전국 법정동 → dim.region, dim.region_code_history).
--   python -m pipeline.dim_region
--
-- 실거래가 API에 넣을 코드를 계약년월로 고르는 함수.
-- 2026-10-21 확인(molit_rent.py probe): 국토부 API는 과거 거래까지 모두 '현재 코드'로 응답하고,
--   옛 코드(강원 42xxx, 전북 45xxx, 전남 46xxx, 광주 29xxx 등)는 항상 0건이다.
--   그래서 기간과 상관없이 region_code를 돌려준다. API가 바뀌면 이 함수만 고치면 된다.
CREATE OR REPLACE FUNCTION dim.lawd_cd_for(p_region_code char(5), p_deal_ym char(6))
RETURNS char(5) LANGUAGE sql STABLE AS $$
    SELECT region_code FROM dim.region WHERE region_code = p_region_code
$$;
