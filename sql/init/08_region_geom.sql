-- 시군구 경계 (PostGIS). 채우는 곳: pipeline/boundary.py (V-World LT_C_ADSIGG_INFO, 현행)
-- [출처표시] meta.data_source 'vworld_sigungu'
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS dim.region_geom (
    region_code  char(5) PRIMARY KEY,                 -- = dim.region leaf (V-World sig_cd)
    name         text,                                -- V-World full_nm
    geom         geometry(MultiPolygon, 4326) NOT NULL,
    label_point  geometry(Point, 4326),               -- 지도 라벨 위치 (ST_PointOnSurface)
    area_km2     numeric,
    fetched_on   date NOT NULL
);
CREATE INDEX IF NOT EXISTS region_geom_gix ON dim.region_geom USING gist (geom);

INSERT INTO meta.data_source (source_id, title, provider, portal_url, license, attribution_required, attribution_text, raw_tables, notes) VALUES
    ('vworld_sigungu', '브이월드 행정구역 시군구 경계 (LT_C_ADSIGG_INFO)', '국토교통부 공간정보 오픈플랫폼(V-World)',
     'https://www.vworld.kr/dtmk/dtmk_ntads_s002.do', '공공누리 제1유형(출처표시)', true,
     '지도 경계: 국토교통부 공간정보 오픈플랫폼(V-World) 행정구역 시군구',
     ARRAY['dim.region_geom'], '2026-10-21 수집. 인증키는 서비스 URL(localhost)에 묶여 있어 domain 파라미터 필요.')
ON CONFLICT (source_id) DO UPDATE SET
    title = EXCLUDED.title, provider = EXCLUDED.provider, portal_url = EXCLUDED.portal_url,
    license = EXCLUDED.license, attribution_required = EXCLUDED.attribution_required,
    attribution_text = EXCLUDED.attribution_text, raw_tables = EXCLUDED.raw_tables,
    notes = EXCLUDED.notes, updated_at = now();
