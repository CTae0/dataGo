-- 원천별 지역 키 → dim.region leaf(수집·지도 단위) 매핑
-- 한 원천 키가 여러 leaf를 덮을 수 있다 (예: 표준데이터 '수원시' → 일반구 4곳, '대구광역시' 상수도 → 대구 전체).
-- granularity: exact(그 지역 값) / si(구를 둔 시 단위 값) / sido(시도 단위 값) / sido_part(옛 시도 단위, 예: 통합 전 광주)
--              / legacy(없어지거나 쪼개진 옛 시군구, 예: 마산시 → 창원 마산합포·마산회원, 인천 중구 → 제물포·영종)
-- 채우는 곳: pipeline/region_xwalk.py
CREATE TABLE IF NOT EXISTS dim.region_xwalk (
    source_id     text    NOT NULL,   -- meta.data_source.source_id (또는 원천 안의 키 종류)
    source_key    text    NOT NULL,   -- 원천의 지역 키 그대로
    source_label  text,               -- 사람이 읽을 이름
    region_code   char(5) NOT NULL,   -- leaf
    granularity   text    NOT NULL CHECK (granularity IN ('exact', 'si', 'sido', 'sido_part', 'legacy')),
    match_method  text    NOT NULL,   -- name / alias / rule
    PRIMARY KEY (source_id, source_key, region_code)
);
CREATE INDEX IF NOT EXISTS region_xwalk_region_idx ON dim.region_xwalk (region_code);

-- 매핑 못 한 키 (검증: 이 표가 비어 있어야 한다)
CREATE TABLE IF NOT EXISTS dim.region_xwalk_unmatched (
    source_id    text NOT NULL,
    source_key   text NOT NULL,
    source_label text,
    reason       text,
    PRIMARY KEY (source_id, source_key)
);
