-- 안전·의료·환경 — 시군구(leaf) 1행  (85_amenities.sql 다음에 돈다: mart.poi_region·mart.region_scores를 쓴다)
-- 원천: raw.poi (nmc_hospital·nmc_pharmacy·nmc_emergency), raw.crime_region (police_crime),
--       raw.air_sigungu_hourly (airkorea_stats), raw.population_age (mois_population) [출처: meta.data_source]
--
-- 1) mart.region_health_env: 개수·비율·거리·농도
--    병원 = 종합병원·병원(요양병원 포함) + 의원 (치과·한방 제외), 소아과 = 이름에 소아·어린이·아동이 든 병·의원
--    응급실 거리 = 시군구 경계 안쪽 대표점(ST_PointOnSurface)에서 가장 가까운 응급의료기관까지 직선거리(km)
--                  — 사람이 사는 곳의 평균 거리가 아니라 넓은 군에서는 실제와 다를 수 있다
--    범죄 = 최근 연도 강력·절도·폭력범죄 발생 건수. 원천 지역이 여러 leaf로 갈리면(일반구 있는 시, 개편 전 인천 구)
--           leaf 인구 비율로 나눈다. 발생 장소 기준이라 상권·관광지(중구 등)는 주민 대비 많게 나온다.
--    미세먼지 = 최근 365일 안에 쌓인 1시간 PM2.5의 평균. 원천이 시(일반구 전체) 값이면 일반구에 같은 값.
--               점수(i_air)는 30일 넘게 쌓인 뒤부터 (그 전에는 비워 두고 API가 중위값으로 채운다)
-- 2) mart.region_health_scores: 지표 점수 0~100 (높을수록 좋음) + 분야 점수·별점
--    병원·약국·소아과 = (인구 대비 백분위 + 면적 대비 백분위) / 2   (교육·문화와 같은 방식)
--    응급실 = 거리가 가까울수록, 치안 = 주민 1천 명당 범죄가 적을수록, 공기 = PM2.5가 낮을수록 높은 백분위
--    의료 = 병원·약국·응급실 평균, 안전 = 치안, 환경 = 공기와 공원(region_scores.park_score) 평균
DROP TABLE IF EXISTS mart.region_health_env;
CREATE TABLE mart.region_health_env AS
WITH pop AS (
    SELECT left(stdg_cd, 5) AS region_code, total, age0 AS kids0_9 FROM raw.population_age
    WHERE stats_ym = (SELECT max(stats_ym) FROM raw.population_age)
),
c AS (
    SELECT region_code,
           sum(w) FILTER (WHERE category IN ('hospital', 'clinic')) AS hospitals,
           sum(w) FILTER (WHERE category = 'hospital')              AS hospitals_big,
           sum(w) FILTER (WHERE category = 'pharmacy')              AS pharmacies,
           sum(w) FILTER (WHERE category = 'pediatric')             AS pediatrics,
           sum(w) FILTER (WHERE category = 'emergency')             AS emergencies
    FROM mart.poi_region GROUP BY region_code
),
er AS (   -- 가장 가까운 응급의료기관 (KNN)
    SELECT g.region_code, round((ST_Distance(pt::geography, e.geom::geography) / 1000)::numeric, 1) AS emergency_km,
           e.name AS emergency_name
    FROM (SELECT region_code, ST_PointOnSurface(geom) AS pt FROM dim.region_geom) g
    CROSS JOIN LATERAL (SELECT name, geom FROM raw.poi WHERE category = 'emergency' AND geom IS NOT NULL
                        ORDER BY geom <-> g.pt LIMIT 1) e
),
crime_src AS (
    SELECT sido_nm || '|' || sigungu_nm AS source_key, data_year, sum(cnt) AS cnt
    FROM raw.crime_region
    WHERE data_year = (SELECT max(data_year) FROM raw.crime_region)
      AND crime_major IN ('강력범죄', '절도범죄', '폭력범죄')
    GROUP BY 1, 2
),
crime AS (   -- 원천 지역 → leaf, 여러 leaf면 인구 비율로 나눈다
    SELECT x.region_code, s.data_year AS crime_year, x.granularity AS crime_gran,
           s.cnt * coalesce(p.total::numeric / nullif(sum(p.total) OVER (PARTITION BY x.source_key), 0),
                            1.0 / count(*) OVER (PARTITION BY x.source_key)) AS crimes
    FROM crime_src s
    JOIN dim.region_xwalk x ON x.source_id = 'police_crime' AND x.source_key = s.source_key
    LEFT JOIN pop p ON p.region_code = x.region_code
),
crime_leaf AS (
    SELECT region_code, max(crime_year) AS crime_year, sum(crimes) AS crimes, max(crime_gran) AS crime_gran
    FROM crime GROUP BY region_code
),
air_src AS (
    SELECT sido_nm || '|' || city_nm AS source_key, avg(pm25) AS pm25, count(pm25) AS hours,
           min(msr_time) AS t0, max(msr_time) AS t1
    FROM raw.air_sigungu_hourly
    WHERE msr_time >= (SELECT max(msr_time) FROM raw.air_sigungu_hourly) - interval '365 days'
    GROUP BY 1
),
air AS (
    SELECT x.region_code, round(avg(a.pm25), 1) AS pm25, min(a.hours) AS pm25_hours,
           min(a.t0)::date AS pm25_from, max(a.t1)::date AS pm25_to, max(x.granularity) AS pm25_gran
    FROM air_src a JOIN dim.region_xwalk x ON x.source_id = 'airkorea' AND x.source_key = a.source_key
    GROUP BY x.region_code
)
SELECT r.region_code, pop.total AS population, pop.kids0_9, g.area_km2,
       round(coalesce(c.hospitals, 0), 1) AS hospitals, round(coalesce(c.hospitals_big, 0), 1) AS hospitals_big,
       round(coalesce(c.pharmacies, 0), 1) AS pharmacies, round(coalesce(c.pediatrics, 0), 1) AS pediatrics,
       round(coalesce(c.emergencies, 0), 1) AS emergencies,
       er.emergency_km, er.emergency_name,
       round(cl.crimes) AS crimes, cl.crime_year, cl.crime_gran,
       air.pm25, air.pm25_hours, air.pm25_from, air.pm25_to, air.pm25_gran,
       -- 인구 대비
       round(coalesce(c.hospitals, 0) * 10000 / nullif(pop.total, 0), 2)    AS hospitals_per_10k,
       round(coalesce(c.pharmacies, 0) * 10000 / nullif(pop.total, 0), 2)   AS pharmacies_per_10k,
       round(coalesce(c.pediatrics, 0) * 10000 / nullif(pop.kids0_9, 0), 2) AS pediatrics_per_10k_kids,
       round(cl.crimes * 1000 / nullif(pop.total, 0), 2)                    AS crimes_per_1k,
       -- 면적 대비 (㎢당)
       round(coalesce(c.hospitals, 0) / nullif(g.area_km2, 0), 3)            AS hospitals_per_km2,
       round(coalesce(c.pharmacies, 0) / nullif(g.area_km2, 0), 3)           AS pharmacies_per_km2,
       round(coalesce(c.pediatrics, 0) / nullif(g.area_km2, 0), 4)           AS pediatrics_per_km2
FROM dim.region r
LEFT JOIN dim.region_geom g USING (region_code)
LEFT JOIN pop USING (region_code)
LEFT JOIN c USING (region_code)
LEFT JOIN er USING (region_code)
LEFT JOIN crime_leaf cl USING (region_code)
LEFT JOIN air USING (region_code)
WHERE r.is_leaf;
ALTER TABLE mart.region_health_env ADD PRIMARY KEY (region_code);

DROP TABLE IF EXISTS mart.region_health_scores;
CREATE TABLE mart.region_health_scores AS
-- 공기 점수는 1시간 값이 30일(720시간) 넘게 쌓인 곳만 매긴다 (하루치는 그날 날씨라 순위에 쓰지 않는다)
WITH h AS (SELECT *, coalesce(pm25_hours >= 720, false) AS air_ok FROM mart.region_health_env WHERE population > 0),
p AS (
    SELECT region_code,
           (percent_rank() OVER (ORDER BY hospitals_per_10k) + percent_rank() OVER (ORDER BY hospitals_per_km2)) * 50  AS i_hospital,
           (percent_rank() OVER (ORDER BY pharmacies_per_10k) + percent_rank() OVER (ORDER BY pharmacies_per_km2)) * 50 AS i_pharmacy,
           (percent_rank() OVER (ORDER BY pediatrics_per_10k_kids) + percent_rank() OVER (ORDER BY pediatrics_per_km2)) * 50 AS i_pediatric,
           (1 - percent_rank() OVER (ORDER BY emergency_km)) * 100                                                    AS i_emergency,
           CASE WHEN crimes_per_1k IS NOT NULL
                THEN (1 - percent_rank() OVER (PARTITION BY crimes_per_1k IS NULL ORDER BY crimes_per_1k)) * 100 END   AS i_safety,
           CASE WHEN air_ok
                THEN (1 - percent_rank() OVER (PARTITION BY air_ok ORDER BY pm25)) * 100 END                            AS i_air
    FROM h
),
s AS (
    SELECT p.region_code,
           round(((i_hospital + i_pharmacy) / 2)::numeric, 1) AS hospital_score,   -- 질문 '병원·약국'
           round(i_pediatric::numeric, 1)  AS pediatric_score,
           round(i_emergency::numeric, 1)  AS emergency_score,
           round(i_safety::numeric, 1)     AS safety_score,
           round(i_air::numeric, 1)        AS air_score,
           round(((i_hospital + i_pharmacy + i_emergency) / 3)::numeric, 1) AS medical_score,
           round(i_safety::numeric, 1)     AS safety_total,
           round(CASE WHEN i_air IS NULL THEN sc.park_score
                      ELSE (i_air + coalesce(sc.park_score, i_air)) / 2 END::numeric, 1) AS env_score
    FROM p LEFT JOIN mart.region_scores sc USING (region_code)
)
SELECT region_code, hospital_score, pediatric_score, emergency_score, safety_score, air_score,
       medical_score, env_score,
       ntile(4) OVER (ORDER BY medical_score) AS medical_stars,
       CASE WHEN safety_total IS NOT NULL THEN ntile(4) OVER (PARTITION BY safety_total IS NULL ORDER BY safety_total) END AS safety_stars,
       CASE WHEN env_score IS NOT NULL THEN ntile(4) OVER (PARTITION BY env_score IS NULL ORDER BY env_score) END AS env_stars
FROM s;
ALTER TABLE mart.region_health_scores ADD PRIMARY KEY (region_code);
