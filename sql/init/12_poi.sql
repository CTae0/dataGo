-- 생활편의 시설(POI)과 연령별 인구 (수집기: poi.py)
--   시설 1행 = 원천 × 시설. 좌표가 있으면 geom, 없으면 주소에서 뽑은 시도·시군구 이름으로 지역을 정한다
--   (지역 배정은 sql/mart/85_amenities.sql). 원천마다 받을 때 통째로 갈아 끼운다.
-- 새 DB에서는 이 파일이, 기존 DB에서는 sql/migrations/008_poi.sql이 같은 내용으로 실행된다.

CREATE TABLE IF NOT EXISTS raw.poi (
    source_id   text NOT NULL,          -- meta.data_source.source_id
    poi_id      text NOT NULL,          -- 원천 안의 고유 번호
    category    text NOT NULL,          -- school_elem / school_mid / school_high / academy / kindergarten / library /
                                        -- museum / gallery / arts_center / culture_center / literature / park / cinema
    name        text,
    addr        text,
    sido_nm     text,                   -- 주소에서 뽑은 시도 (좌표 없는 원천의 지역 배정용)
    sigungu_nm  text,                   -- 주소에서 뽑은 시군구 (예: '용인시 수지구', '종로구')
    sgg_cd      text,                   -- 원천이 준 시군구 코드 (참고용)
    lon         double precision,
    lat         double precision,
    geom        geometry(Point, 4326),
    size_value  numeric,                -- 크기 값 (공원 면적 ㎡, 유치원 정원 등)
    payload     jsonb NOT NULL,
    snapshot    date NOT NULL,
    PRIMARY KEY (source_id, poi_id)
);
CREATE INDEX IF NOT EXISTS poi_geom_gix ON raw.poi USING gist (geom);
CREATE INDEX IF NOT EXISTS poi_category_idx ON raw.poi (category);

-- 행정안전부 법정동별 성·연령별 주민등록 인구 (시군구 단위, 월). 10세 단위 연령대 남녀 합
CREATE TABLE IF NOT EXISTS raw.population_age (
    stats_ym    char(6) NOT NULL,
    stdg_cd     text    NOT NULL,       -- 법정동코드 10자리 (앞 5자리 = 시군구)
    sido_nm     text,
    sigungu_nm  text,
    total       integer NOT NULL,
    age0        integer, age10 integer, age20 integer, age30 integer, age40 integer,
    age50       integer, age60 integer, age70 integer, age80 integer, age90 integer, age100 integer,
    payload     jsonb   NOT NULL,
    PRIMARY KEY (stats_ym, stdg_cd)
);

INSERT INTO meta.data_source (source_id, title, provider, portal_url, license, attribution_required, attribution_text, raw_tables, notes) VALUES
    ('culture_facility', '한국문화정보원_전국문화기반시설총람 정보 조회서비스', '한국문화정보원 (원자료: 문화체육관광부 전국 문화기반시설 총람)',
     'https://www.data.go.kr/data/15125097/openapi.do', NULL, true,
     '출처: 공공데이터포털(data.go.kr) 「한국문화정보원_전국문화기반시설총람 정보 조회서비스」',
     ARRAY['raw.poi'], '공공도서관·박물관·미술관·문예회관·생활문화센터·문학관. 연 1회 발간(직전 연도 기준). 좌표 없음 → 주소로 지역 배정. 이용조건 확인 필요.'),
    ('city_park', '전국도시공원정보표준데이터', '각 지방자치단체',
     'https://www.data.go.kr/data/15012890/standard.do', NULL, true,
     '출처: 공공데이터포털(data.go.kr) 「전국도시공원정보표준데이터」, 각 지방자치단체 제공',
     ARRAY['raw.poi'], '위경도·면적 포함. 이용조건 확인 필요.'),
    ('mois_cinema', '행정안전부_문화_영화상영관 조회서비스', '행정안전부 (지방행정 인허가)',
     'https://www.data.go.kr/data/15154848/openapi.do', NULL, true,
     '출처: 공공데이터포털(data.go.kr) 「행정안전부_문화_영화상영관 조회서비스」',
     ARRAY['raw.poi'], '영업 중인 상영관만. 이용조건 확인 필요.'),
    ('neis_school', '나이스 교육정보 개방포털 — 학교기본정보', '교육부·시도교육청 (한국교육학술정보원)',
     'https://open.neis.go.kr/portal/data/service/selectServicePage.do?infId=OPEN17020190531110010104913', NULL, true,
     '출처: 나이스 교육정보 개방포털(open.neis.go.kr) 「학교기본정보」',
     ARRAY['raw.poi'], '인증키 EDU_API_KEY. 좌표 없음 → 도로명주소로 지역 배정. 이용조건 확인 필요.'),
    ('neis_academy', '나이스 교육정보 개방포털 — 학원교습소정보', '교육부·시도교육청 (한국교육학술정보원)',
     'https://open.neis.go.kr/portal/mainPage.do', NULL, true,
     '출처: 나이스 교육정보 개방포털(open.neis.go.kr) 「학원교습소정보」',
     ARRAY['raw.poi'], '인증키 EDU_API_KEY. 이용조건 확인 필요.'),
    ('kinder_info', '유치원알리미 — 유치원 일반현황', '교육부 (한국교육개발원)',
     'https://e-childschoolinfo.moe.go.kr/openApi/openApiList.do', NULL, true,
     '출처: 유치원알리미(e-childschoolinfo.moe.go.kr) 「유치원 일반현황」',
     ARRAY['raw.poi'], '인증키 EDU_CHILD_API_KEY. 위경도 포함. 이용조건 확인 필요.'),
    ('mois_population', '행정안전부_법정동별(행정동 통반단위) 성/연령별 주민등록 인구수', '행정안전부',
     'https://www.data.go.kr/data/15108074/openapi.do', NULL, true,
     '출처: 공공데이터포털(data.go.kr) 「행정안전부_법정동별 성/연령별 주민등록 인구수」',
     ARRAY['raw.population_age'], '시군구 단위(lv=2), 10세 단위 연령대. 시설 수를 인구로 나누는 분모. 이용조건 확인 필요.')
ON CONFLICT (source_id) DO UPDATE SET
    title = EXCLUDED.title, provider = EXCLUDED.provider, portal_url = EXCLUDED.portal_url, license = EXCLUDED.license,
    attribution_required = EXCLUDED.attribution_required, attribution_text = EXCLUDED.attribution_text,
    raw_tables = EXCLUDED.raw_tables, notes = EXCLUDED.notes, updated_at = now();
