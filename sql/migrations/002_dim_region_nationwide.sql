-- 이미 만들어진 DB의 dim.region을 전국용 구조로 바꾼다.
-- dim.region을 참조하는 FK는 없고, 데이터는 pipeline/dim_region.py가 다시 채운다.
-- 실행: docker compose exec -T db psql -U eodi -d eodi -f /sql/migrations/002_dim_region_nationwide.sql
--       python -m pipeline.dim_region
BEGIN;
DROP TABLE IF EXISTS dim.region CASCADE;   -- dim.lawd_cd_for()는 아래에서 다시 만든다
CREATE TABLE dim.region (
    region_code     char(5)     PRIMARY KEY,
    sido_code       char(2)     NOT NULL,
    sido            text        NOT NULL,
    sido_full       text        NOT NULL,
    sigungu         text        NOT NULL,
    sigungu_raw     text        NOT NULL,
    sigungu_type    text        NOT NULL CHECK (sigungu_type IN ('시', '군', '구')),
    level           text        NOT NULL CHECK (level IN ('sigungu', 'gu', 'si')),
    parent_code     char(5),
    is_leaf         boolean     NOT NULL,
    legacy_code     char(5),
    code_changed_on date,
    created_on      date,
    in_scope        boolean     NOT NULL DEFAULT false,
    UNIQUE (sido_code, sigungu)
);
CREATE INDEX region_legacy_code_idx ON dim.region (legacy_code);
CREATE INDEX region_parent_idx ON dim.region (parent_code);

CREATE TABLE IF NOT EXISTS dim.region_code_history (
    old_code    char(5) NOT NULL,
    region_code char(5) NOT NULL,
    changed_on  date,
    old_sido    text,
    note        text,
    PRIMARY KEY (old_code, region_code)
);

CREATE OR REPLACE FUNCTION dim.lawd_cd_for(p_region_code char(5), p_deal_ym char(6))
RETURNS char(5) LANGUAGE sql STABLE AS $$
    SELECT region_code FROM dim.region WHERE region_code = p_region_code
$$;
COMMIT;
