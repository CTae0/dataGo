-- mart.region_summary: 시군구(leaf) 1행 = 지도·API가 읽는 단일 표
-- 각 값 옆의 *_gran 은 그 값이 어느 단위에서 왔는지(exact/si/legacy/sido_part/sido). 화면에서 '시도 평균 대체'를 구분해 표시한다.
-- sources: 이 행에 쓰인 원천 source_id 목록 → meta.data_source에서 출처 문구를 찾아 함께 표시 (ATTRIBUTION.md)
DROP TABLE IF EXISTS mart.region_summary;
CREATE TABLE mart.region_summary AS
WITH rent AS (
    SELECT region_code,
           max(from_ym) AS rent_from_ym, max(to_ym) AS rent_to_ym,
           sum(deals) AS rent_deals,
           max(jeonse_deposit_median) FILTER (WHERE size_band = 's') AS jeonse_s,   -- 만원
           max(jeonse_deposit_median) FILTER (WHERE size_band = 'm') AS jeonse_m,
           max(jeonse_deposit_median) FILTER (WHERE size_band = 'l') AS jeonse_l,
           max(monthly_cost_median)   FILTER (WHERE size_band = 's') AS cost_s,     -- 만원/월 (환산)
           max(monthly_cost_median)   FILTER (WHERE size_band = 'm') AS cost_m,
           max(monthly_cost_median)   FILTER (WHERE size_band = 'l') AS cost_l,
           max(deals) FILTER (WHERE size_band = 's') AS deals_s,
           max(deals) FILTER (WHERE size_band = 'm') AS deals_m,
           max(deals) FILTER (WHERE size_band = 'l') AS deals_l,
           max(jeonse_deals) FILTER (WHERE size_band = 's') AS jeonse_deals_s,   -- 전세 중위값의 표본 수
           max(jeonse_deals) FILTER (WHERE size_band = 'm') AS jeonse_deals_m,
           max(jeonse_deals) FILTER (WHERE size_band = 'l') AS jeonse_deals_l
    FROM mart.rent_recent GROUP BY region_code
),
util AS (
    SELECT region_code,
           max(value) FILTER (WHERE item = 'water_20m3') AS water_20m3,
           max(granularity) FILTER (WHERE item = 'water_20m3') AS water_gran,
           max(value) FILTER (WHERE item = 'sewer_20m3') AS sewer_20m3,
           max(granularity) FILTER (WHERE item = 'sewer_20m3') AS sewer_gran,
           max(value) FILTER (WHERE item = 'trash_20l') AS trash_20l,
           max(granularity) FILTER (WHERE item = 'trash_20l') AS trash_gran,
           max(value) FILTER (WHERE item = 'gas_total') AS gas_total,
           max(value) FILTER (WHERE item = 'bus_card') AS bus_card,
           max(value) FILTER (WHERE item = 'taxi') AS taxi,
           array_agg(DISTINCT source_id) AS util_sources
    FROM mart.utility_region GROUP BY region_code
),
groc AS (
    SELECT region_code,
           max(price_index) FILTER (WHERE category = 'all')      AS grocery_index,
           max(granularity) FILTER (WHERE category = 'all')      AS grocery_gran,
           max(price_index) FILTER (WHERE category = '신선식품') AS grocery_fresh_index,
           max(price_index) FILTER (WHERE category = '가공식품') AS grocery_processed_index,
           max(price_index) FILTER (WHERE category = '생활용품') AS grocery_household_index,
           max(stores_in_region) FILTER (WHERE category = 'all') AS grocery_stores
    FROM mart.grocery_region GROUP BY region_code
),
rent_apt AS (   -- 아파트만 (mart.rent_recent_apt): 만원, 만원/월
    SELECT region_code,
           max(jeonse_deposit_median) FILTER (WHERE size_band = 's') AS jeonse_apt_s,
           max(monthly_cost_median)   FILTER (WHERE size_band = 's') AS cost_apt_s,
           max(deals)        FILTER (WHERE size_band = 's') AS deals_apt_s,
           max(jeonse_deals) FILTER (WHERE size_band = 's') AS jeonse_deals_apt_s,
           max(jeonse_deposit_median) FILTER (WHERE size_band = 'm') AS jeonse_apt_m,
           max(monthly_cost_median)   FILTER (WHERE size_band = 'm') AS cost_apt_m,
           max(deals)        FILTER (WHERE size_band = 'm') AS deals_apt_m,
           max(jeonse_deals) FILTER (WHERE size_band = 'm') AS jeonse_deals_apt_m,
           max(jeonse_deposit_median) FILTER (WHERE size_band = 'l') AS jeonse_apt_l,
           max(monthly_cost_median)   FILTER (WHERE size_band = 'l') AS cost_apt_l,
           max(deals)        FILTER (WHERE size_band = 'l') AS deals_apt_l,
           max(jeonse_deals) FILTER (WHERE size_band = 'l') AS jeonse_deals_apt_l
    FROM mart.rent_recent_apt GROUP BY region_code
)
SELECT r.region_code, r.sido_code, r.sido, r.sigungu, r.level, r.parent_code,
       rent.rent_from_ym, rent.rent_to_ym, rent.rent_deals,
       rent.jeonse_s, rent.jeonse_m, rent.jeonse_l, rent.cost_s, rent.cost_m, rent.cost_l,
       rent.deals_s, rent.deals_m, rent.deals_l,
       rent.jeonse_deals_s, rent.jeonse_deals_m, rent.jeonse_deals_l,
       util.water_20m3, util.water_gran, util.sewer_20m3, util.sewer_gran,
       util.trash_20l, util.trash_gran, util.gas_total, util.bus_card, util.taxi,
       groc.grocery_index, groc.grocery_gran, groc.grocery_fresh_index, groc.grocery_processed_index,
       groc.grocery_household_index, groc.grocery_stores,
       rent_apt.jeonse_apt_s, rent_apt.cost_apt_s, rent_apt.deals_apt_s, rent_apt.jeonse_deals_apt_s, rent_apt.jeonse_apt_m, rent_apt.cost_apt_m, rent_apt.deals_apt_m, rent_apt.jeonse_deals_apt_m, rent_apt.jeonse_apt_l, rent_apt.cost_apt_l, rent_apt.deals_apt_l, rent_apt.jeonse_deals_apt_l,
       pw.power_kwh, pw.power_bill, pw.power_gran, pw.kwh_m01, pw.kwh_m02, pw.kwh_m03, pw.kwh_m04, pw.kwh_m05, pw.kwh_m06, pw.kwh_m07, pw.kwh_m08, pw.kwh_m09, pw.kwh_m10, pw.kwh_m11, pw.kwh_m12,
       mg.mgmt_per_m2, mg.mgmt_gran, mg.mgmt_complexes,
       ARRAY(SELECT DISTINCT s FROM unnest(
           coalesce(util.util_sources, '{}')
           || CASE WHEN rent.region_code IS NOT NULL THEN ARRAY['molit_rent'] ELSE '{}' END
           || CASE WHEN groc.grocery_index IS NOT NULL THEN ARRAY['kca_price'] ELSE '{}' END
           || CASE WHEN pw.power_kwh IS NOT NULL THEN ARRAY['kepco_house_power'] ELSE '{}' END
           || CASE WHEN mg.mgmt_per_m2 IS NOT NULL THEN ARRAY['kapt_fee'] ELSE '{}' END) AS s
             ORDER BY s) AS sources,
       now() AS built_at
FROM dim.region r
LEFT JOIN rent USING (region_code)
LEFT JOIN util USING (region_code)
LEFT JOIN groc USING (region_code)
LEFT JOIN rent_apt USING (region_code)
LEFT JOIN mart.power_region pw USING (region_code)   -- sql/mart/60_power.sql (전기)
LEFT JOIN mart.mgmt_region mg USING (region_code)    -- sql/mart/80_mgmt.sql (아파트 관리비)
WHERE r.is_leaf;
ALTER TABLE mart.region_summary ADD PRIMARY KEY (region_code);
