-- 생활편의(교육·육아, 문화·여가) — 시군구(leaf) 1행
-- 원천: raw.poi (교육: neis_school·neis_academy·kinder_info / 문화: culture_facility·city_park·mois_cinema)
--       raw.population_age (mois_population, 최근 달) [출처: meta.data_source 각 source_id]
--
-- 1) 시설 → leaf 배정 (mart.poi_region)
--    좌표가 있으면 경계(dim.region_geom) 안에 드는 leaf (weight 1).
--    좌표가 없거나 경계 밖이면 주소의 시도|시군구를 dim.region_xwalk 'poi'로 매핑. 여러 leaf로 갈리면
--    (예: 일반구 없이 '화성시'만 적힌 주소, 개편 전 '인천 중구') 그 leaf들의 인구 비율로 나눠 센다.
--    원천 주소 오타로 매핑 못 한 시설(약 15곳)은 빠진다 → dim.region_xwalk_unmatched.
-- 2) mart.region_amenities: 분류별 개수, 인구 대비 비율
--    아이 인구 = 0~19세(10세 단위 자료라 0~9 + 10~19), 유아 = 0~9세
-- 3) mart.region_scores: 분야 점수 0~100
--    지표마다 '인구 대비 비율'의 전국 백분위와 '개수'의 전국 백분위를 평균 낸다
--    (비율만 쓰면 인구 적은 군이, 개수만 쓰면 큰 도시가 늘 위라서 둘을 섞는다).
--    교육 = 초등학교 · 중·고등학교 · 유치원 · 학원 지표 평균
--    문화 = 도서관 · 박물관·미술관 · 문예회관·생활문화센터·문학관 · 공원 면적 (· 영화관: 자료가 있을 때만) 평균
--    별점 1~4 = 점수 사분위
DROP TABLE IF EXISTS mart.poi_region;
CREATE TABLE mart.poi_region AS
WITH geo AS (
    SELECT p.source_id, p.poi_id, g.region_code, 1.0::numeric AS w, 'geom'::text AS method
    FROM raw.poi p JOIN dim.region_geom g ON p.geom IS NOT NULL AND ST_Contains(g.geom, p.geom)
),
pop AS (
    SELECT left(stdg_cd, 5) AS region_code, total FROM raw.population_age
    WHERE stats_ym = (SELECT max(stats_ym) FROM raw.population_age)
),
addr AS (   -- 여러 leaf로 갈리는 주소(구 없이 '화성시'만 등)는 leaf 인구 비율로 나눈다 (인구가 없으면 똑같이)
    SELECT p.source_id, p.poi_id, x.region_code,
           coalesce(pop.total::numeric / nullif(sum(pop.total) OVER (PARTITION BY p.source_id, p.poi_id), 0),
                    1.0 / count(*) OVER (PARTITION BY p.source_id, p.poi_id))::numeric AS w,
           'addr'::text AS method
    FROM raw.poi p
    JOIN dim.region_xwalk x ON x.source_id = 'poi' AND x.source_key = p.sido_nm || '|' || coalesce(p.sigungu_nm, '')
    LEFT JOIN pop ON pop.region_code = x.region_code
    WHERE NOT EXISTS (SELECT 1 FROM geo WHERE geo.source_id = p.source_id AND geo.poi_id = p.poi_id)
)
SELECT p.source_id, p.poi_id, p.category, r.region_code, r.w, r.method, p.size_value
FROM (SELECT * FROM geo UNION ALL SELECT * FROM addr) r
JOIN raw.poi p USING (source_id, poi_id);
CREATE INDEX ON mart.poi_region (region_code, category);

DROP TABLE IF EXISTS mart.region_amenities;
CREATE TABLE mart.region_amenities AS
WITH pop AS (
    SELECT left(a.stdg_cd, 5) AS region_code, a.stats_ym, a.total, a.age0 AS kids0_9, a.age0 + a.age10 AS kids0_19
    FROM raw.population_age a
    WHERE a.stats_ym = (SELECT max(stats_ym) FROM raw.population_age)
),
c AS (
    SELECT region_code,
           sum(w) FILTER (WHERE category = 'school_elem')                          AS elem,
           sum(w) FILTER (WHERE category IN ('school_mid', 'school_high'))           AS secondary,
           sum(w) FILTER (WHERE category = 'kindergarten')                          AS kinder,
           sum(w) FILTER (WHERE category = 'academy')                               AS academy,
           sum(w) FILTER (WHERE category = 'library')                               AS library,
           sum(w) FILTER (WHERE category IN ('museum', 'gallery'))                  AS museum,
           sum(w) FILTER (WHERE category IN ('arts_center', 'culture_center', 'literature')) AS arts,
           sum(w) FILTER (WHERE category = 'cinema')                                AS cinema,
           sum(w) FILTER (WHERE category = 'park')                                  AS parks,
           sum(w * coalesce(size_value, 0)) FILTER (WHERE category = 'park')        AS park_m2
    FROM mart.poi_region GROUP BY region_code
)
SELECT r.region_code, pop.stats_ym AS pop_ym, pop.total AS population, pop.kids0_9, pop.kids0_19,
       round(coalesce(c.elem, 0), 1) AS elem, round(coalesce(c.secondary, 0), 1) AS secondary,
       round(coalesce(c.kinder, 0), 1) AS kinder, round(coalesce(c.academy, 0), 1) AS academy,
       round(coalesce(c.library, 0), 1) AS library, round(coalesce(c.museum, 0), 1) AS museum,
       round(coalesce(c.arts, 0), 1) AS arts, round(coalesce(c.cinema, 0), 1) AS cinema,
       round(coalesce(c.parks, 0), 1) AS parks, round(coalesce(c.park_m2, 0)) AS park_m2,
       -- 인구 대비
       round(coalesce(c.elem, 0) * 1000 / nullif(pop.kids0_19, 0), 2)        AS elem_per_1k_kids,
       round(coalesce(c.secondary, 0) * 1000 / nullif(pop.kids0_19, 0), 2)   AS secondary_per_1k_kids,
       round(coalesce(c.kinder, 0) * 1000 / nullif(pop.kids0_9, 0), 2)       AS kinder_per_1k_kids,
       round(coalesce(c.academy, 0) * 1000 / nullif(pop.kids0_19, 0), 1)     AS academy_per_1k_kids,
       round(coalesce(c.library, 0) * 100000 / nullif(pop.total, 0), 2)      AS library_per_100k,
       round(coalesce(c.museum, 0) * 100000 / nullif(pop.total, 0), 2)       AS museum_per_100k,
       round(coalesce(c.arts, 0) * 100000 / nullif(pop.total, 0), 2)         AS arts_per_100k,
       round(coalesce(c.cinema, 0) * 100000 / nullif(pop.total, 0), 2)       AS cinema_per_100k,
       round(coalesce(c.park_m2, 0) / nullif(pop.total, 0), 1)               AS park_m2_per_person
FROM dim.region r
LEFT JOIN pop USING (region_code)
LEFT JOIN c USING (region_code)
WHERE r.is_leaf;
ALTER TABLE mart.region_amenities ADD PRIMARY KEY (region_code);

DROP TABLE IF EXISTS mart.region_scores;
CREATE TABLE mart.region_scores AS
WITH a AS (SELECT * FROM mart.region_amenities WHERE population > 0),
p AS (   -- 지표 = (비율 백분위 + 개수 백분위) / 2, 0~100
    SELECT region_code,
           (percent_rank() OVER (ORDER BY elem_per_1k_kids) + percent_rank() OVER (ORDER BY elem)) * 50           AS i_elem,
           (percent_rank() OVER (ORDER BY secondary_per_1k_kids) + percent_rank() OVER (ORDER BY secondary)) * 50 AS i_secondary,
           (percent_rank() OVER (ORDER BY kinder_per_1k_kids) + percent_rank() OVER (ORDER BY kinder)) * 50       AS i_kinder,
           (percent_rank() OVER (ORDER BY academy_per_1k_kids) + percent_rank() OVER (ORDER BY academy)) * 50    AS i_academy,
           (percent_rank() OVER (ORDER BY library_per_100k) + percent_rank() OVER (ORDER BY library)) * 50        AS i_library,
           (percent_rank() OVER (ORDER BY museum_per_100k) + percent_rank() OVER (ORDER BY museum)) * 50          AS i_museum,
           (percent_rank() OVER (ORDER BY arts_per_100k) + percent_rank() OVER (ORDER BY arts)) * 50              AS i_arts,
           (percent_rank() OVER (ORDER BY park_m2_per_person) + percent_rank() OVER (ORDER BY park_m2)) * 50      AS i_park,
           CASE WHEN (SELECT sum(cinema) FROM a) > 0
                THEN (percent_rank() OVER (ORDER BY cinema_per_100k) + percent_rank() OVER (ORDER BY cinema)) * 50 END AS i_cinema
    FROM a
),
s AS (
    SELECT region_code,
           round(((i_elem + i_secondary + i_kinder + i_academy) / 4)::numeric, 1) AS edu_score,
           round(((i_library + i_museum + i_arts + i_park + coalesce(i_cinema, 0))
                  / (4 + CASE WHEN i_cinema IS NULL THEN 0 ELSE 1 END))::numeric, 1) AS culture_score
    FROM p
)
SELECT s.*,
       ntile(4) OVER (ORDER BY edu_score)     AS edu_stars,
       ntile(4) OVER (ORDER BY culture_score) AS culture_stars
FROM s;
ALTER TABLE mart.region_scores ADD PRIMARY KEY (region_code);
