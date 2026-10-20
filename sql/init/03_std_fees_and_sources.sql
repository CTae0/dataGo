-- ── 데이터 출처(저작자 표시) ────────────────────────────────
-- 서비스 화면(지도, 상세, 푸터 등)에 출처를 표시할 때 이 테이블을 그대로 읽어 쓴다.
-- attribution_required = true 인 출처는 해당 데이터를 쓰는 화면에 반드시 attribution_text를 보여야 한다.
CREATE SCHEMA IF NOT EXISTS meta;

CREATE TABLE IF NOT EXISTS meta.data_source (
    source_id            text PRIMARY KEY,      -- 코드에서 쓰는 이름
    title                text NOT NULL,         -- 데이터셋 이름 (포털 표기 그대로)
    provider             text NOT NULL,         -- 제공기관
    portal_url           text NOT NULL,
    license              text,                  -- 이용허락 조건
    attribution_required boolean NOT NULL DEFAULT true,
    attribution_text     text NOT NULL,         -- 화면에 그대로 붙일 문구
    raw_tables           text[] NOT NULL,       -- 이 출처를 담은 테이블
    notes                text,
    updated_at           timestamptz NOT NULL DEFAULT now()
);

INSERT INTO meta.data_source (source_id, title, provider, portal_url, license, attribution_required, attribution_text, raw_tables, notes) VALUES
    ('std_water_sewage_fee', '전국상하수도요금표준데이터', '각 지방자치단체 (소관: 기후에너지환경부)',
     'https://www.data.go.kr/data/15139217/standard.do', '저작자표시', true,
     '출처: 공공데이터포털(data.go.kr) 「전국상하수도요금표준데이터」, 각 지방자치단체 제공',
     ARRAY['raw.std_water_sewage_fee'], '2026-10-21 활용신청. 이용허락 조건은 신청 시 확인한 내용(저작자표시).'),
    ('std_trash_bag_price', '전국종량제봉투가격표준데이터', '각 지방자치단체 (소관: 기후에너지환경부)',
     'https://www.data.go.kr/data/15025538/standard.do', '저작자표시', true,
     '출처: 공공데이터포털(data.go.kr) 「전국종량제봉투가격표준데이터」, 각 지방자치단체 제공',
     ARRAY['raw.std_trash_bag_price'], '2026-10-21 활용신청. 이용허락 조건은 신청 시 확인한 내용(저작자표시).'),
    ('mois_public_fee', '행정안전부_지방공공요금 현황', '행정안전부',
     'https://www.data.go.kr/data/3045228/fileData.do', NULL, true,
     '출처: 공공데이터포털(data.go.kr) 「행정안전부_지방공공요금 현황」',
     ARRAY['raw.mois_public_fee'], '이용허락 조건 미확인 — 공개 전 포털에서 확인할 것. 확인 전까지 표시하는 것으로 둔다.'),
    ('molit_rent', '국토교통부_전월세 실거래가 자료 (아파트·오피스텔·단독다가구·연립다세대)', '국토교통부',
     'https://www.data.go.kr/data/15126474/openapi.do', NULL, true,
     '출처: 국토교통부 실거래가 공개시스템 / 공공데이터포털(data.go.kr)',
     ARRAY['raw.molit_rent'], '이용허락 조건 미확인 — 공개 전 포털에서 확인할 것. 확인 전까지 표시하는 것으로 둔다.')
ON CONFLICT (source_id) DO UPDATE SET
    title = EXCLUDED.title, provider = EXCLUDED.provider, portal_url = EXCLUDED.portal_url,
    license = EXCLUDED.license, attribution_required = EXCLUDED.attribution_required,
    attribution_text = EXCLUDED.attribution_text, raw_tables = EXCLUDED.raw_tables,
    notes = EXCLUDED.notes, updated_at = now();

-- ── 원천: 전국상하수도요금표준데이터 (api.data.go.kr tn_pubr_public_water_sewage_fees_api) ──
-- [저작자표시 필요] meta.data_source 'std_water_sewage_fee'
-- 1행 = 지자체 × 업종 × 상/하수도 × 사용량 구간의 ㎥당 단가. 수집할 때마다 통째로 바꾼다.
-- (기본요금·구경별 요금은 이 표준에 없다)
CREATE TABLE IF NOT EXISTS raw.std_water_sewage_fee (
    item_seq      integer PRIMARY KEY,   -- 응답 순번
    instt_code    text,                  -- 제공기관 코드 (행정기관 코드, 법정동 코드 아님)
    instt_nm      text,                  -- 예: '강원특별자치도 춘천시'
    mng_inst_nm   text,
    mng_no        text,
    sector        text,                  -- 업종구분명: 가정용, 일반용, 욕탕용 …
    kind          text,                  -- 상하수도구분: 상수도 / 하수도
    usage_from    numeric,               -- 시작사용량(㎥)
    usage_to      numeric,               -- 종료사용량(㎥), 9999999 = 이상
    unit_price    numeric,               -- 단가(원/㎥)
    data_date     date,                  -- 데이터기준일자
    payload       jsonb NOT NULL,
    fetched_at    timestamptz NOT NULL DEFAULT now()
);

-- ── 원천: 전국종량제봉투가격표준데이터 (api.data.go.kr tn_pubr_public_weighted_envlp_api) ──
-- [저작자표시 필요] meta.data_source 'std_trash_bag_price'
-- 1행 = 시군구 × 봉투 종류·처리방식·용도·대상. 가격 0은 '해당 규격 없음'이라 prices에서 뺀다.
CREATE TABLE IF NOT EXISTS raw.std_trash_bag_price (
    item_seq      integer PRIMARY KEY,
    instt_code    text,
    instt_nm      text,
    sido_nm       text,                  -- 시도명
    sigungu_nm    text,                  -- 시군구명
    bag_type      text,                  -- 종량제봉투종류: 규격봉투, 공공용봉투 …
    method        text,                  -- 처리방식: 소각용, 매립용 …
    purpose       text,                  -- 용도: 생활쓰레기, 음식물쓰레기, 재사용 …
    target        text,                  -- 사용대상: 가정용, 사업장용 …
    price_20l     integer,               -- 20ℓ 가격 (지역 비교 기준)
    prices        jsonb,                 -- {"1": 50, "3": 90, "20": 510, …} 리터 → 원
    data_date     date,
    payload       jsonb NOT NULL,
    fetched_at    timestamptz NOT NULL DEFAULT now()
);
