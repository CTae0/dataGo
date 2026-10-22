-- 안전·의료·환경 (수집기: health_env.py)
--   병원·의원·약국·응급의료기관·소아과는 raw.poi에 넣는다 (좌표 있음, 지역 배정은 sql/mart/85_amenities.sql의 mart.poi_region)
--   미세먼지: 시군구별 시간 값(API가 최근 24시간만 준다)을 매일 받아 쌓는다 → 쌓일수록 연평균에 가까워진다
--   범죄: 경찰청 범죄 발생 지역별 통계 (연 1회 CSV, 시군구 열)
-- 새 DB에서는 이 파일이, 기존 DB에서는 sql/migrations/009_health_env.sql이 같은 내용으로 실행된다.

CREATE TABLE IF NOT EXISTS raw.air_sigungu_hourly (
    sido_nm     text    NOT NULL,       -- API 시도 이름 (예: '서울', '경기')
    city_nm     text    NOT NULL,       -- API 시군구 이름 (예: '강남구', '수원시')
    msr_time    timestamp NOT NULL,     -- 측정 시각 (KST, 1시간 값)
    pm25        numeric,                -- ㎍/㎥
    pm10        numeric,
    payload     jsonb   NOT NULL,
    fetched_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (sido_nm, city_nm, msr_time)
);

CREATE TABLE IF NOT EXISTS raw.crime_region (
    data_year   integer NOT NULL,       -- 통계 연도 (파일 이름의 연도)
    region_label text   NOT NULL,       -- CSV 열 이름 (예: '서울 종로구', '경기도 수원시')
    sido_nm     text    NOT NULL,
    sigungu_nm  text    NOT NULL,
    crime_major text    NOT NULL,       -- 범죄대분류 (강력범죄·절도범죄·폭력범죄 …)
    crime_minor text    NOT NULL,       -- 범죄중분류
    cnt         integer NOT NULL,
    PRIMARY KEY (data_year, region_label, crime_major, crime_minor)
);

INSERT INTO meta.data_source (source_id, title, provider, portal_url, license, attribution_required, attribution_text, raw_tables, notes) VALUES
    ('nmc_hospital', '국립중앙의료원_전국 병·의원 찾기 서비스', '국립중앙의료원',
     'https://www.data.go.kr/data/15000736/openapi.do', NULL, true,
     '출처: 공공데이터포털(data.go.kr) 「국립중앙의료원_전국 병·의원 찾기 서비스」',
     ARRAY['raw.poi'], '병원(종합병원·병원)·의원 위경도. 소아과는 기관 이름(소아·어린이·아동)으로 고른다. 이용조건 확인 필요.'),
    ('nmc_pharmacy', '국립중앙의료원_전국 약국 정보 조회 서비스', '국립중앙의료원',
     'https://www.data.go.kr/data/15000576/openapi.do', NULL, true,
     '출처: 공공데이터포털(data.go.kr) 「국립중앙의료원_전국 약국 정보 조회 서비스」',
     ARRAY['raw.poi'], '약국 위경도. 이용조건 확인 필요.'),
    ('nmc_emergency', '국립중앙의료원_전국 응급의료기관 정보 조회 서비스', '국립중앙의료원',
     'https://www.data.go.kr/data/15000563/openapi.do', NULL, true,
     '출처: 공공데이터포털(data.go.kr) 「국립중앙의료원_전국 응급의료기관 정보 조회 서비스」',
     ARRAY['raw.poi'], '응급의료기관 위경도. 시군구 안쪽 한 점에서 가장 가까운 기관까지 직선거리를 쓴다. 이용조건 확인 필요.'),
    ('airkorea_stats', '한국환경공단_에어코리아_대기오염통계 현황', '한국환경공단',
     'https://www.data.go.kr/data/15073855/openapi.do', '공공누리 제3유형', true,
     '출처: 공공데이터포털(data.go.kr) 「한국환경공단_에어코리아_대기오염통계 현황」 (확정 전 실시간 자료)',
     ARRAY['raw.air_sigungu_hourly'], '시군구별 1시간 PM2.5·PM10을 매일 쌓아 평균 낸다. 최종 확정 전 값. 공공누리 제3유형(변경 금지) — 평균만 내서 보여 준다.'),
    ('police_crime', '경찰청_범죄 발생 지역별 통계', '경찰청',
     'https://www.data.go.kr/data/3074462/fileData.do', NULL, true,
     '출처: 공공데이터포털(data.go.kr) 「경찰청_범죄 발생 지역별 통계」',
     ARRAY['raw.crime_region'], '시군구별 연간 범죄 발생 건수. 강력·절도·폭력범죄만 쓴다. 발생 장소 기준이라 상권·관광지는 주민 수보다 많게 잡힌다.')
ON CONFLICT (source_id) DO UPDATE SET
    title = EXCLUDED.title, provider = EXCLUDED.provider, portal_url = EXCLUDED.portal_url, license = EXCLUDED.license,
    attribution_required = EXCLUDED.attribution_required, attribution_text = EXCLUDED.attribution_text,
    raw_tables = EXCLUDED.raw_tables, notes = EXCLUDED.notes, updated_at = now();
