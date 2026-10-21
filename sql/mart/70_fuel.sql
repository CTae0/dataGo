-- mart.fuel_region: 시군구(leaf) 주유소 평균가격 — 1행 = leaf
-- 원천: raw.opinet_sigun_price  한국석유공사 오피넷 시군구별 주유소 평균가격(현재), 하루 1번 스냅샷 [출처: 'opinet_price']
-- 방법
--   - leaf 매핑은 dim.region_xwalk 'opinet'. 일반구가 있는 시(수원 등)는 시 값이 구마다 들어간다 (fuel_gran = 'si').
--   - *_now = 가장 최근 스냅샷 값, *_30d = 최근 30일 스냅샷 평균 (쌓인 날이 적으면 있는 날만).
--   - 제품: B027 보통휘발유, D047 자동차용경유, K015 자동차용부탄(LPG). 원/L.
DROP TABLE IF EXISTS mart.fuel_region;
CREATE TABLE mart.fuel_region AS
WITH last AS (SELECT max(snapshot) AS d FROM raw.opinet_sigun_price),
p AS (
    SELECT o.snapshot, x.region_code, x.granularity, o.prodcd, o.price
    FROM raw.opinet_sigun_price o
    JOIN dim.region_xwalk x ON x.source_id = 'opinet' AND x.source_key = o.sigun_cd
    WHERE o.snapshot > (SELECT d FROM last) - 30 AND o.price > 0
)
SELECT region_code,
       (SELECT d FROM last)                                                          AS fuel_date,
       count(DISTINCT snapshot)::int                                                 AS fuel_days,
       min(granularity)                                                              AS fuel_gran,
       round(avg(price) FILTER (WHERE prodcd = 'B027' AND snapshot = (SELECT d FROM last)), 1) AS gasoline_now,
       round(avg(price) FILTER (WHERE prodcd = 'D047' AND snapshot = (SELECT d FROM last)), 1) AS diesel_now,
       round(avg(price) FILTER (WHERE prodcd = 'K015' AND snapshot = (SELECT d FROM last)), 1) AS lpg_now,
       round(avg(price) FILTER (WHERE prodcd = 'B027'), 1)                           AS gasoline_30d,
       round(avg(price) FILTER (WHERE prodcd = 'D047'), 1)                           AS diesel_30d,
       round(avg(price) FILTER (WHERE prodcd = 'K015'), 1)                           AS lpg_30d
FROM p GROUP BY region_code;
ALTER TABLE mart.fuel_region ADD PRIMARY KEY (region_code);
