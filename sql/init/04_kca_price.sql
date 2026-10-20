-- ── 원천: 한국소비자원_생필품 가격 정보_GW (data.go.kr 15158701) ──────────────
-- [저작자표시 필요 — 공공누리 1유형(출처표시)] meta.data_source 'kca_price'
-- 참가격(price.go.kr) 조사: 전국 대형마트·SSM·백화점·편의점 판매점 × 생필품, 격주 금요일 조사
-- 수집기: kca_price.py

-- 기준코드 (classCode: AR 지역, AL 상품분류, BU 업태, UT 단위)
CREATE TABLE IF NOT EXISTS raw.kca_code (
    class_code  text NOT NULL,
    code        text NOT NULL,
    code_name   text,
    high_code   text,
    fetched_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (class_code, code)
);

-- 판매점. 지역은 area_code(시도) / area_detail_code(시군구) → raw.kca_code(AR)로 이름을 얻는다.
-- 주의: API의 xMapCoord에 위도, yMapCoord에 경도가 들어 있다(이름과 반대). 좌표는 일부 점포만 있다.
CREATE TABLE IF NOT EXISTS raw.kca_store (
    entp_id           text PRIMARY KEY,
    entp_name         text,
    type_code         text,          -- BU: LM 대형마트, SM 슈퍼마켓(SSM), DP 백화점, CS 편의점
    area_code         text,          -- AR 시도
    area_detail_code  text,          -- AR 시군구
    tel               text,
    post_no           text,
    addr_jibun        text,
    addr_road         text,
    lat               numeric,       -- xMapCoord
    lon               numeric,       -- yMapCoord
    payload           jsonb NOT NULL,
    fetched_at        timestamptz NOT NULL DEFAULT now()
);

-- 상품. 단위가격 = 가격 / total_cnt * base_cnt (예: 100g당)
CREATE TABLE IF NOT EXISTS raw.kca_product (
    good_id          text PRIMARY KEY,
    good_name        text,
    maker_code       text,
    small_class_code text,           -- AL 소분류 (상위로 올라가면 중분류·대분류)
    base_cnt         numeric,        -- 단위가격 기준량
    unit_code        text,           -- UT
    total_cnt        numeric,        -- 상품 용량
    total_unit_code  text,           -- UT
    detail           text,
    payload          jsonb NOT NULL,
    fetched_at       timestamptz NOT NULL DEFAULT now()
);

-- 조사일 탐색 결과 (금요일마다 1회 찔러 보고 자료가 있는 날만 가격을 받는다)
CREATE TABLE IF NOT EXISTS raw.kca_survey_day (
    inspect_day date PRIMARY KEY,
    has_data    boolean NOT NULL,
    probed_at   timestamptz NOT NULL DEFAULT now()
);

-- 가격 (조사일 × 판매점 × 상품)
CREATE TABLE IF NOT EXISTS raw.kca_price (
    inspect_day    date    NOT NULL,
    entp_id        text    NOT NULL,
    good_id        text    NOT NULL,
    price          integer,
    dc_yn          text,
    dc_start_day   text,
    dc_end_day     text,
    plusone_yn     text,
    input_dttm     text,
    fetched_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (inspect_day, entp_id, good_id)
);
CREATE INDEX IF NOT EXISTS kca_price_good_idx ON raw.kca_price (good_id, inspect_day);

-- 가격 수집 이력: (조사일, 상품) 단위. 이어받기에 쓴다.
CREATE TABLE IF NOT EXISTS raw.kca_price_fetch_log (
    inspect_day date NOT NULL,
    good_id     text NOT NULL,
    n_items     integer NOT NULL,
    fetched_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (inspect_day, good_id)
);

INSERT INTO meta.data_source (source_id, title, provider, portal_url, license, attribution_required, attribution_text, raw_tables, notes) VALUES
    ('kca_price', '한국소비자원_생필품 가격 정보_GW', '한국소비자원 (참가격 가격정보 종합포털)',
     'https://www.data.go.kr/data/15158701/openapi.do', '공공누리 제1유형(출처표시)', true,
     '출처: 한국소비자원 참가격(www.price.go.kr) / 공공데이터포털(data.go.kr) 「한국소비자원_생필품 가격 정보」',
     ARRAY['raw.kca_price', 'raw.kca_store', 'raw.kca_product', 'raw.kca_code'],
     '2026-10-21 활용신청. 이용허락: 공공저작물 출처표시(제1유형).')
ON CONFLICT (source_id) DO UPDATE SET
    title = EXCLUDED.title, provider = EXCLUDED.provider, portal_url = EXCLUDED.portal_url,
    license = EXCLUDED.license, attribution_required = EXCLUDED.attribution_required,
    attribution_text = EXCLUDED.attribution_text, raw_tables = EXCLUDED.raw_tables,
    notes = EXCLUDED.notes, updated_at = now();
