-- 스키마 구분
--   raw  : 원천 그대로(또는 최소 정리) 적재
--   dim  : 기준 정보(지역 등)
--   mart : 서비스에서 바로 쓰는 집계 (다음 단계)
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS dim;
CREATE SCHEMA IF NOT EXISTS mart;

-- ── 지역 기준 ────────────────────────────────────────────
-- 시군구 1행. 코드는 법정동 코드 앞 5자리(국토부 실거래가 API의 LAWD_CD).
-- 강원은 2023-06-11 강원특별자치도 출범으로 시도 코드가 42 → 51로 바뀌었다.
CREATE TABLE IF NOT EXISTS dim.region (
    region_code     char(5)     PRIMARY KEY,   -- 현재 코드 (강원: 51xxx)
    legacy_code     char(5),                   -- 이전 코드 (강원: 42xxx)
    code_changed_on date,                      -- 코드가 바뀐 날
    sido            text        NOT NULL,      -- 짧은 이름 (강원, 서울 …)
    sido_full       text        NOT NULL,
    sigungu         text        NOT NULL,
    sigungu_type    text        NOT NULL CHECK (sigungu_type IN ('시', '군', '구')),
    in_scope        boolean     NOT NULL DEFAULT false,  -- 1단계 서비스 범위 여부
    UNIQUE (sido, sigungu)
);
CREATE INDEX IF NOT EXISTS region_legacy_code_idx ON dim.region (legacy_code);

-- ── 원천: 행정안전부 지방공공요금 (data.go.kr 3045228) ──────
-- merge_public_fee.py가 만든 public_fee_long.csv를 그대로 받는다.
-- 2016-12 이후는 시도 평균, 2013·2016년 일부 달만 시군구 값이 있다.
CREATE TABLE IF NOT EXISTS raw.mois_public_fee (
    ym          char(7)  NOT NULL,          -- YYYY-MM
    level       text     NOT NULL CHECK (level IN ('sido', 'sigungu')),
    sido        text     NOT NULL,
    sigungu     text     NOT NULL DEFAULT '',  -- 시도 단위 행은 ''
    category    text     NOT NULL,          -- utility / dining / personal_service
    item        text     NOT NULL,          -- water_20m3, trash_20l …
    value       numeric  NOT NULL,          -- 원
    raw_column  text,
    source_name text,
    source_file text,
    reg_date    text,                       -- 포털 등록일 (현재 파일은 'current')
    loaded_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (ym, level, sido, sigungu, item)
);

-- ── 원천: 국토부 전월세 실거래가 (다음 단계에서 수집기 작성) ──
-- 4종(아파트, 오피스텔, 단독·다가구, 연립·다세대) 응답을 한 테이블에 쌓는다.
-- 응답 항목이 유형마다 달라 원본은 jsonb로 보관하고, 자주 쓰는 값만 컬럼으로 뺀다.
-- 같은 (유형, 코드, 연월)은 수집기가 통째로 지우고 다시 넣는다. 내용이 똑같은 거래도
-- 실제로 여러 건일 수 있어서 내용 해시로 중복을 막지 않고, 응답 안 순번(item_seq)으로 구분한다.
CREATE TABLE IF NOT EXISTS raw.molit_rent (
    house_type      text        NOT NULL CHECK (house_type IN ('apt', 'officetel', 'detached', 'row_house')),
    lawd_cd         char(5)     NOT NULL,   -- 요청에 쓴 코드 (42xxx 또는 51xxx)
    deal_ym         char(6)     NOT NULL,   -- 요청에 쓴 계약년월 YYYYMM
    item_seq        integer     NOT NULL,   -- 응답 안 순번 (1부터)
    payload         jsonb       NOT NULL,   -- 응답 item 1건 원본
    deposit         bigint,                 -- 보증금(만원)
    monthly_rent    bigint,                 -- 월세(만원), 전세는 0
    area_m2         numeric,                -- 전용면적(단독·다가구는 연면적)
    fetched_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (house_type, lawd_cd, deal_ym, item_seq)
);

-- 수집 이력: 어떤 (유형, 코드, 연월)을 받았고 몇 건이었는지. 이어받기·코드 검증에 쓴다.
CREATE TABLE IF NOT EXISTS raw.molit_rent_fetch_log (
    house_type  text        NOT NULL,
    lawd_cd     char(5)     NOT NULL,
    deal_ym     char(6)     NOT NULL,
    total_count integer,
    result_code text,
    fetched_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (house_type, lawd_cd, deal_ym)
);
