-- 시군구(leaf) 가구 전기 사용량·전기요금
-- 원천: raw.kepco_house_power  한전 전력데이터개방포털 「가구평균 전력사용량」 (시군구 × 월) [출처: meta.data_source 'kepco_house_power']
--
-- 방법
--   1) 원천 키(시도명|시군구명) → leaf 매핑은 dim.region_xwalk 'kepco_house'.
--      한 leaf에 여러 키가 걸리면 granularity가 가장 좁은 것만 쓴다 (exact → legacy → si → sido).
--      예: 화성시 동탄구는 '화성시 동탄구'(exact) 행을 쓰고 '화성시'(si, 개편 뒤 남은 241가구) 행은 버린다.
--      인천 제물포구는 개편 전 달에는 '중구'·'동구'(legacy) 행을 가구 수로 가중 평균한다.
--   2) 가구 100호 미만 행은 버린다 (개편 뒤 남은 '부천시'·'인천 서구' 2호 같은 찌꺼기).
--   3) 월 값 = 가구 수 가중 평균 (kWh, 원). mart.power_monthly에 달마다 남긴다.
--   4) mart.power_region = leaf별 최근 12개월(받은 마지막 달 기준) 평균, 여름(7~8월)·겨울(12~2월) 평균.
--      12개월이 다 없는 leaf(새로 생긴 구)는 있는 달만으로 평균 내고 months에 개월 수를 남긴다.
-- 주의: 한전 '평균 전기요금'은 주택용 전 가구 평균이다 (1인~다인 가구 섞임, 복지할인 반영된 청구액).
--      가구원 수별 값은 이 원천에 없다 → 가구원 수 보정은 api/cost_model.py에서 따로 한다.

DROP TABLE IF EXISTS mart.power_monthly;
CREATE TABLE mart.power_monthly AS
WITH x AS (
    SELECT x.source_key, x.region_code, x.granularity,
           CASE x.granularity WHEN 'exact' THEN 1 WHEN 'legacy' THEN 2 WHEN 'si' THEN 3 ELSE 4 END AS prio
    FROM dim.region_xwalk x WHERE x.source_id = 'kepco_house'
),
p AS (
    SELECT k.ym, x.region_code, x.granularity, x.prio, k.house_cnt, k.power_kwh, k.bill
    FROM raw.kepco_house_power k
    JOIN x ON x.source_key = k.metro_nm || '|' || k.city_nm
    WHERE k.house_cnt >= 100 AND k.power_kwh > 0 AND k.bill > 0
),
best AS (
    SELECT p.*, min(prio) OVER (PARTITION BY ym, region_code) AS best_prio FROM p
)
SELECT ym, region_code,
       min(granularity)                                              AS granularity,
       sum(house_cnt)::integer                                       AS house_cnt,   -- legacy·si면 원천 단위 가구 수
       round(sum(power_kwh * house_cnt) / sum(house_cnt), 1)         AS power_kwh,
       round(sum(bill::numeric * house_cnt) / sum(house_cnt))::int   AS bill
FROM best WHERE prio = best_prio
GROUP BY ym, region_code;
ALTER TABLE mart.power_monthly ADD PRIMARY KEY (region_code, ym);

DROP TABLE IF EXISTS mart.power_region;
CREATE TABLE mart.power_region AS
WITH last AS (SELECT max(ym) AS ym FROM mart.power_monthly),
w AS (
    SELECT m.* FROM mart.power_monthly m, last
    WHERE m.ym > to_char(to_date(last.ym, 'YYYYMM') - interval '12 months', 'YYYYMM') AND m.ym <= last.ym
)
SELECT r.region_code,
       (SELECT ym FROM last)                                                    AS last_ym,
       count(w.ym)::int                                                         AS months,
       max(w.granularity)                                                       AS power_gran,
       round(avg(w.power_kwh), 1)                                               AS power_kwh,         -- 월평균 kWh
       round(avg(w.bill))::int                                                  AS power_bill,        -- 월평균 원
       round(avg(w.power_kwh) FILTER (WHERE right(w.ym, 2) IN ('07', '08')), 1) AS power_kwh_summer,
       round(avg(w.bill) FILTER (WHERE right(w.ym, 2) IN ('07', '08')))::int    AS power_bill_summer,
       round(avg(w.power_kwh) FILTER (WHERE right(w.ym, 2) IN ('12', '01', '02')), 1) AS power_kwh_winter,
       round(avg(w.bill) FILTER (WHERE right(w.ym, 2) IN ('12', '01', '02')))::int    AS power_bill_winter,
       max(w.house_cnt) FILTER (WHERE w.ym = (SELECT ym FROM last))             AS house_cnt
FROM dim.region r
JOIN w ON w.region_code = r.region_code
WHERE r.is_leaf
GROUP BY r.region_code;
ALTER TABLE mart.power_region ADD PRIMARY KEY (region_code);
