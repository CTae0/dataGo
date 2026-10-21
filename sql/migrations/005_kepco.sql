-- 마이그레이션 005: 한전 가구평균 전력사용량 (sql/init/09_kepco.sql과 같은 내용)
-- 한국전력공사 전력데이터개방포털 「가구평균 전력사용량」 (수집기: kepco_power.py)
--   https://bigdata.kepco.co.kr  OPEN API: /openapi/v1/powerUsage/houseAve.do (인증키 KEPCO_API_KEY)
--   시군구 × 월: 전기 쓰는 가구 수, 가구당 평균 사용량(kWh), 가구당 평균 전기요금(원). 2014-01부터.
-- 응답에 시군구 코드가 없고 이름만 온다 → (시도명, 시군구명)을 키로 두고 dim.region_xwalk 'kepco_house'로 매핑.
-- 새 DB에서는 이 파일이, 기존 DB에서는 sql/migrations/005_kepco.sql이 같은 내용으로 실행된다.

CREATE TABLE IF NOT EXISTS raw.kepco_house_power (
    ym          char(6)  NOT NULL,           -- YYYYMM
    metro_nm    text     NOT NULL,           -- 응답 시도명 (예: 광주광역시, 전라남도 — 통합 전 이름으로 온다)
    city_nm     text     NOT NULL,           -- 응답 시군구명 (예: 청주시 상당구, 화성시 — 시 전체 행과 구 행이 같이 오기도 함)
    metro_cd    text     NOT NULL,           -- 요청한 시도코드 (한전 법정동 시도코드)
    house_cnt   integer,                     -- 전기 사용 가구 수(호)
    power_kwh   numeric,                     -- 가구당 평균 사용량 (kWh/월)
    bill        integer,                     -- 가구당 평균 전기요금 (원/월)
    payload     jsonb    NOT NULL,
    fetched_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (ym, metro_nm, city_nm)
);

-- 받은 (연월, 시도코드) 기록. 빈 응답도 남겨서 다시 부르지 않는다 (최근 달은 수집기가 다시 확인).
CREATE TABLE IF NOT EXISTS raw.kepco_fetch_log (
    ym          char(6)  NOT NULL,
    metro_cd    text     NOT NULL,
    rows        integer  NOT NULL,
    fetched_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (ym, metro_cd)
);

INSERT INTO meta.data_source (source_id, title, provider, portal_url, license, attribution_required, attribution_text, raw_tables, notes) VALUES
    ('kepco_house_power', '한국전력공사 전력데이터개방포털 — 가구평균 전력사용량', '한국전력공사',
     'https://bigdata.kepco.co.kr/cmsmain.do?scode=S01&pcode=000493&pstate=house', NULL, true,
     '출처: 한국전력공사 전력데이터개방포털 「가구평균 전력사용량」',
     ARRAY['raw.kepco_house_power'],
     '주택용 전기 사용 가구의 시군구 월평균. data.go.kr 15101404(LINK)와 같은 자료. 이용허락 조건 미확인 — 공개 전 포털 이용약관 확인할 것.')
ON CONFLICT (source_id) DO UPDATE SET
    title = EXCLUDED.title, provider = EXCLUDED.provider, portal_url = EXCLUDED.portal_url, license = EXCLUDED.license,
    attribution_required = EXCLUDED.attribution_required, attribution_text = EXCLUDED.attribution_text,
    raw_tables = EXCLUDED.raw_tables, notes = EXCLUDED.notes, updated_at = now();
