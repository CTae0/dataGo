-- mart.region_features: 시군구(leaf)의 '어디 살고 싶은지' 질문용 특징 (PostGIS, dim.region_geom)
--   coast_km      바다와 맞닿은 해안선 길이(km). 국경선(휴전선) 쪽 경계는 뺀다
--   is_coastal    해안선 3km 이상
--   is_island     다른 시군구와 땅으로 이어지지 않음 (울릉·옹진·신안 등) 또는 제주
--   is_capital    수도권 (서울·인천·경기)
--   is_metro_area 광역시권: 특별시·광역시·특별자치시(세종) 또는 그와 땅을 맞댄 시군구
--   airport_*     가장 가까운 공항과 직선거리(km). '공항 1시간'은 직선 40km 이내로 본다 (api/cost_model.py AIRPORT_KM)
--   archetype     카드 그림 유형: metropolis / commuter_town / small_city / harbor_city / seaside_village /
--                 mountain_village / farmland / island
-- 공항 좌표: 국내 정기편 공항(한국공항공사 14곳 + 인천국제공항)의 위치, 소수점 2~3자리 근사
-- 계산 속도: 단순화한 도형을 임시 표에 넣고 공간 인덱스를 건 뒤 이웃·해안선을 구한다 (수십 초)

DROP TABLE IF EXISTS pg_temp.g;
CREATE TEMP TABLE g AS
SELECT region_code, ST_MakeValid(ST_SimplifyPreserveTopology(geom, 0.001)) AS geom, label_point
FROM dim.region_geom;
CREATE INDEX ON g USING gist (geom);
ANALYZE g;

-- 이웃: 경계가 맞닿은(0.0005° ≈ 50m 이내) 시군구 쌍
DROP TABLE IF EXISTS pg_temp.nb;
CREATE TEMP TABLE nb AS
SELECT a.region_code AS a, b.region_code AS b
FROM g a JOIN g b ON a.region_code < b.region_code AND ST_DWithin(a.geom, b.geom, 0.0005);

-- 해안선: 시군구 경계 중 '이웃과 맞닿지 않은 부분' = 바다 쪽 경계. 휴전선 쪽 내륙 국경(김포 북쪽 ~ 고성 서쪽)은 뺀다
DROP TABLE IF EXISTS pg_temp.coast;
CREATE TEMP TABLE coast AS
SELECT g.region_code,
       coalesce(ST_Length(ST_Difference(
           ST_Difference(ST_Boundary(g.geom), coalesce(ST_Buffer(nbr.geom, 0.0008), ST_GeomFromText('POLYGON EMPTY', 4326))),
           ST_MakeEnvelope(126.62, 37.70, 128.36, 38.70, 4326))::geography) / 1000, 0) AS coast_km
FROM g
LEFT JOIN LATERAL (
    SELECT ST_Union(o.geom) AS geom FROM g o
    WHERE o.region_code IN (SELECT b FROM nb WHERE a = g.region_code UNION SELECT a FROM nb WHERE b = g.region_code)
) nbr ON true;

DROP TABLE IF EXISTS mart.region_features;
CREATE TABLE mart.region_features AS
WITH airports(name, lon, lat) AS (VALUES
    ('인천국제공항', 126.441, 37.460), ('김포공항', 126.791, 37.558), ('김해공항', 128.938, 35.180),
    ('제주공항', 126.493, 33.507), ('대구공항', 128.659, 35.894), ('청주공항', 127.499, 36.717),
    ('무안공항', 126.383, 34.991), ('광주공항', 126.809, 35.126), ('여수공항', 127.616, 34.842),
    ('울산공항', 129.352, 35.594), ('포항경주공항', 129.420, 35.988), ('사천공항', 128.070, 35.089),
    ('양양공항', 128.669, 38.061), ('군산공항', 126.616, 35.904), ('원주공항', 127.960, 37.438)
),
metro AS (   -- 특별시·광역시·세종 (전남광주의 옛 광주 자치구 포함)
    SELECT r.region_code FROM dim.region r
    WHERE r.is_leaf AND (r.sido_code IN ('11', '26', '27', '28', '30', '31', '36')
          OR r.region_code IN (SELECT region_code FROM dim.region_code_history WHERE old_sido = '광주'))
),
metro_adj AS (
    SELECT a AS region_code FROM nb WHERE b IN (SELECT region_code FROM metro)
    UNION SELECT b FROM nb WHERE a IN (SELECT region_code FROM metro)
),
n_neighbors AS (
    SELECT region_code, count(*) AS n FROM (SELECT a AS region_code FROM nb UNION ALL SELECT b FROM nb) x GROUP BY 1
),
air AS (
    SELECT DISTINCT ON (g.region_code) g.region_code, ap.name AS airport_name,
           ST_Distance(g.label_point::geography, ST_SetSRID(ST_MakePoint(ap.lon, ap.lat), 4326)::geography) / 1000 AS airport_km
    FROM g CROSS JOIN airports ap
    ORDER BY g.region_code, 3
),
f AS (
    SELECT r.region_code, r.sido, r.sigungu, r.sigungu_type,
           round(c.coast_km::numeric, 1) AS coast_km,
           c.coast_km >= 3 AS is_coastal,
           (coalesce(nn.n, 0) = 0 OR r.sido_code = '50') AS is_island,
           r.sido_code IN ('11', '28', '41') AS is_capital,
           (r.region_code IN (SELECT region_code FROM metro) OR r.region_code IN (SELECT region_code FROM metro_adj)) AS is_metro_area,
           r.region_code IN (SELECT region_code FROM metro) AS is_metro_core,
           a.airport_name, round(a.airport_km::numeric, 1) AS airport_km,
           rg.area_km2
    FROM dim.region r
    JOIN coast c USING (region_code)
    LEFT JOIN n_neighbors nn USING (region_code)
    JOIN air a USING (region_code)
    JOIN dim.region_geom rg USING (region_code)
    WHERE r.is_leaf
)
SELECT f.*,
       CASE
         WHEN is_island THEN 'island'
         WHEN is_metro_core AND sigungu_type = '구' THEN 'metropolis'
         WHEN is_coastal AND sigungu_type IN ('시', '구') THEN 'harbor_city'
         WHEN is_coastal THEN 'seaside_village'
         WHEN sigungu_type = '군' AND (sido IN ('강원', '충북', '경북') OR area_km2 > 700) THEN 'mountain_village'
         WHEN sigungu_type = '군' THEN 'farmland'
         WHEN is_capital OR is_metro_area THEN 'commuter_town'
         ELSE 'small_city'
       END AS archetype
FROM f;
ALTER TABLE mart.region_features ADD PRIMARY KEY (region_code);
