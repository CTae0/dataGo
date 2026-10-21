-- mart.rent_monthly: 시군구(leaf) × 주택유형 × 계약월 × 면적대 × 전세/월세
-- 원천: raw.molit_rent (국토부 전월세 실거래가) [출처: meta.data_source 'molit_rent']
--
-- 면적대 (가구 유형과 맞춤): s ≤40㎡(1인) / m 40~60㎡(2인) / l 60~85㎡(가족) / xl >85㎡
-- 환산 월세 = 월세 + 보증금 × 전환율 / 12  (전세는 월세 0)
--   전환율은 아래 rate 한 곳에서 바꾼다. 5.5%는 임시값 — 한국부동산원 전월세전환율로 바꿀 것.
DROP TABLE IF EXISTS mart.rent_monthly;
CREATE TABLE mart.rent_monthly AS
WITH params AS (SELECT 0.055::numeric AS rate),
deals AS (
    SELECT m.lawd_cd AS region_code, m.house_type, m.deal_ym,
           CASE WHEN m.area_m2 <= 40 THEN 's' WHEN m.area_m2 <= 60 THEN 'm'
                WHEN m.area_m2 <= 85 THEN 'l' ELSE 'xl' END AS size_band,
           CASE WHEN coalesce(m.monthly_rent, 0) = 0 THEN 'jeonse' ELSE 'wolse' END AS rent_kind,
           m.deposit, coalesce(m.monthly_rent, 0) AS monthly_rent, m.area_m2,
           coalesce(m.monthly_rent, 0) + m.deposit * p.rate / 12 AS monthly_cost   -- 만원/월
    FROM raw.molit_rent m CROSS JOIN params p
    WHERE m.deposit IS NOT NULL AND m.area_m2 > 0
)
SELECT region_code, house_type, deal_ym, size_band, rent_kind,
       count(*)                                                        AS deals,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY deposit)            AS deposit_median,      -- 만원
       percentile_cont(0.5) WITHIN GROUP (ORDER BY monthly_rent)       AS monthly_rent_median, -- 만원
       percentile_cont(0.5) WITHIN GROUP (ORDER BY monthly_cost)       AS monthly_cost_median, -- 만원 (환산)
       percentile_cont(0.5) WITHIN GROUP (ORDER BY monthly_cost / area_m2) AS monthly_cost_per_m2_median,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY area_m2)            AS area_median
FROM deals
GROUP BY 1, 2, 3, 4, 5;
ALTER TABLE mart.rent_monthly ADD PRIMARY KEY (region_code, house_type, deal_ym, size_band, rent_kind);

-- 지도용: 최근 12개월(거래가 있는 마지막 달 기준) × 면적대, 주택유형 합산
DROP TABLE IF EXISTS mart.rent_recent;
CREATE TABLE mart.rent_recent AS
WITH last_ym AS (SELECT max(deal_ym) AS ym FROM raw.molit_rent),
win AS (
    SELECT to_char(to_date(ym || '01', 'YYYYMMDD') - interval '11 months', 'YYYYMM') AS from_ym, ym AS to_ym
    FROM last_ym
),
deals AS (
    SELECT m.lawd_cd AS region_code,
           CASE WHEN m.area_m2 <= 40 THEN 's' WHEN m.area_m2 <= 60 THEN 'm'
                WHEN m.area_m2 <= 85 THEN 'l' ELSE 'xl' END AS size_band,
           coalesce(m.monthly_rent, 0) = 0 AS is_jeonse, m.deposit,
           coalesce(m.monthly_rent, 0) + m.deposit * 0.055 / 12 AS monthly_cost
    FROM raw.molit_rent m, win
    WHERE m.deal_ym BETWEEN win.from_ym AND win.to_ym AND m.deposit IS NOT NULL AND m.area_m2 > 0
)
SELECT d.region_code, d.size_band, w.from_ym, w.to_ym,
       count(*)                                                                      AS deals,
       count(*) FILTER (WHERE is_jeonse)                                             AS jeonse_deals,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY deposit) FILTER (WHERE is_jeonse) AS jeonse_deposit_median,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY monthly_cost)                     AS monthly_cost_median
FROM deals d, win w
GROUP BY 1, 2, 3, 4;
ALTER TABLE mart.rent_recent ADD PRIMARY KEY (region_code, size_band);

-- 아파트만: 질문지에서 '아파트파'를 고르면 이 값을 쓴다 (표본이 적으면 모델이 전체 유형 값으로 대체)
DROP TABLE IF EXISTS mart.rent_recent_apt;
CREATE TABLE mart.rent_recent_apt AS
WITH last_ym AS (SELECT max(deal_ym) AS ym FROM raw.molit_rent),
win AS (
    SELECT to_char(to_date(ym || '01', 'YYYYMMDD') - interval '11 months', 'YYYYMM') AS from_ym, ym AS to_ym
    FROM last_ym
),
deals AS (
    SELECT m.lawd_cd AS region_code,
           CASE WHEN m.area_m2 <= 40 THEN 's' WHEN m.area_m2 <= 60 THEN 'm'
                WHEN m.area_m2 <= 85 THEN 'l' ELSE 'xl' END AS size_band,
           coalesce(m.monthly_rent, 0) = 0 AS is_jeonse, m.deposit,
           coalesce(m.monthly_rent, 0) + m.deposit * 0.055 / 12 AS monthly_cost
    FROM raw.molit_rent m, win
    WHERE m.house_type = 'apt' AND m.deal_ym BETWEEN win.from_ym AND win.to_ym
      AND m.deposit IS NOT NULL AND m.area_m2 > 0
)
SELECT d.region_code, d.size_band,
       count(*)                                                                      AS deals,
       count(*) FILTER (WHERE is_jeonse)                                             AS jeonse_deals,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY deposit) FILTER (WHERE is_jeonse) AS jeonse_deposit_median,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY monthly_cost)                     AS monthly_cost_median
FROM deals d
GROUP BY 1, 2;
ALTER TABLE mart.rent_recent_apt ADD PRIMARY KEY (region_code, size_band);
