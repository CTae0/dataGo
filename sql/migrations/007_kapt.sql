-- 마이그레이션 007: K-apt 관리비 (sql/init/11_kapt.sql과 같은 내용)
-- K-apt(공동주택관리정보시스템) 관리비공개의무단지 일괄 파일 (수집·적재기: kapt_fee.py)
--   자료실 기본정보 + 면적정보 → raw.kapt_complex (단지 1행), 관리비정보 → raw.kapt_fee (단지 × 월)
--   주 1회 게시. 파일에 법정동코드가 없어 (시도, 시군구) 이름을 dim.region_xwalk 'kapt'로 매핑한다.
-- 새 DB에서는 이 파일이, 기존 DB에서는 sql/migrations/007_kapt.sql이 같은 내용으로 실행된다.

CREATE TABLE IF NOT EXISTS raw.kapt_complex (
    kapt_code     text PRIMARY KEY,          -- 단지코드 (예: A10021295)
    snapshot      date NOT NULL,             -- 파일 추출일 (파일 이름 YYYYMMDD)
    sido          text NOT NULL,
    sigungu       text NOT NULL,             -- 원천 표기 그대로 (예: 수원장안구, 종로구)
    eupmyeon      text,
    dongri        text,
    kapt_name     text,
    kapt_kind     text,                      -- 단지분류: 아파트, 주상복합, 도시형 생활주택 …
    households    integer,                   -- 세대수
    heat_type     text,                      -- 난방방식
    mgmt_area     numeric,                   -- 관리비부과면적 (㎡, 면적정보)
    private_area  numeric,                   -- 주거전용면적 단지 합계 (㎡, 면적정보)
    payload       jsonb NOT NULL             -- 기본정보 원본 행
);

CREATE TABLE IF NOT EXISTS raw.kapt_fee (
    kapt_code       text NOT NULL,
    ym              char(6) NOT NULL,        -- 발생년월
    snapshot        date NOT NULL,
    common_total    numeric,                 -- 공용관리비(합계), 원/월 (단지 전체)
    ltrm_repair     numeric,                 -- 장기수선충당금 월부과액
    indiv_total     numeric,                 -- 개별사용료계 (전기·수도·가스·난방 등, 생활비 다른 항목과 겹쳐 집계에 안 씀)
    payload         jsonb NOT NULL,          -- 원본 행 (항목 46개)
    PRIMARY KEY (kapt_code, ym)
);

INSERT INTO meta.data_source (source_id, title, provider, portal_url, license, attribution_required, attribution_text, raw_tables, notes) VALUES
    ('kapt_fee', 'K-apt 공동주택관리정보시스템 — 관리비공개의무단지 기본·면적·관리비 정보', '국토교통부 (운영: 한국부동산원)',
     'https://www.k-apt.go.kr/web/board/webReference/boardList.do?boardType=03', NULL, true,
     '출처: 국토교통부 공동주택관리정보시스템(K-apt)',
     ARRAY['raw.kapt_complex', 'raw.kapt_fee'],
     '자료실 엑셀(주 1회). 기관 안내: 실시간 수정되는 시스템이라 엑셀은 참고자료, 정확한 값은 data.go.kr OpenAPI. 이용허락 조건 미확인 — 공개 전 확인할 것.')
ON CONFLICT (source_id) DO UPDATE SET
    title = EXCLUDED.title, provider = EXCLUDED.provider, portal_url = EXCLUDED.portal_url, license = EXCLUDED.license,
    attribution_required = EXCLUDED.attribution_required, attribution_text = EXCLUDED.attribution_text,
    raw_tables = EXCLUDED.raw_tables, notes = EXCLUDED.notes, updated_at = now();
