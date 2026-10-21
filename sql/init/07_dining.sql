-- 외식비 원천 2종 (조사: docs/research/dining_sources.md)
--   mois_dining : 행정안전부 지방물가정보 개인서비스(외식비) 가격 — 시도 × 9품목 × 월   (수집기: mois_dining.py)
--   good_price  : 행정안전부_착한가격업소 현황 (data.go.kr 3045247) — 업소 × 메뉴 4개, 분기 (적재기: good_price.py)
-- 기존 DB에는 sql/migrations/004_dining.sql로 같은 내용을 적용한다.

-- ── 원천: 행정안전부 지방물가정보 외식비 (hamoni.mois.go.kr) ──
-- 원자료는 국가데이터처 소비자물가조사 조사 가격. 2011-09부터 매월. 세종은 충남 값에 포함돼 있다.
-- 시도 이름이 바뀌어도(예: 2026-07 '전남광주(광주)') ctpv_no는 그대로라서 ctpv_no를 키로 쓴다.
CREATE TABLE IF NOT EXISTS raw.mois_dining_price (
    ym          char(6)  NOT NULL,           -- 조사 연월 YYYYMM
    ctpv_no     text     NOT NULL,           -- 하모니 시도 코드 (6110000 = 서울 …)
    sido        text     NOT NULL,           -- 짧은 시도 이름 (광주·전남은 통합 전 이름으로 고정)
    ctpv_nm     text,                        -- 응답의 시도 이름 그대로
    item_cd     text     NOT NULL,           -- BA 냉면 … BI 김밥
    item_nm     text     NOT NULL,
    price       integer  NOT NULL,           -- 원
    price_src   text     NOT NULL DEFAULT 'hamoni',  -- hamoni / tprice(중복 행이 엇갈려 참가격 값으로 정함) / hamoni_first(못 정함)
    fetched_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (ym, ctpv_no, item_cd)
);

-- ── 원천: 행정안전부_착한가격업소 현황 (data.go.kr 3045247, 분기 파일) ──
-- 싼 가게만 지정한 표본이라 '외식비 수준'으로 쓰지 않는다. 시군구별 업소 수(가성비 식당 접근성) 지표용.
-- snapshot = 파일 기준일 (파일 이름의 _YYYYMMDD). 스냅샷마다 행을 쌓는다.
CREATE TABLE IF NOT EXISTS raw.good_price_store (
    snapshot    date     NOT NULL,
    item_seq    integer  NOT NULL,           -- 파일 안 행 순번
    sido_nm     text,
    sigungu_nm  text,
    biz_type    text,                        -- 업종: 한식, 중식, 미용업 …
    is_dining   boolean  NOT NULL,           -- 외식업 여부 (한식·중식·일식·양식·기타요식업·베이커리 등)
    store_nm    text,
    address     text,                        -- 도로명 주소
    payload     jsonb    NOT NULL,           -- 원본 행
    PRIMARY KEY (snapshot, item_seq)
);

CREATE TABLE IF NOT EXISTS raw.good_price_menu (
    snapshot    date     NOT NULL,
    item_seq    integer  NOT NULL,
    menu_no     smallint NOT NULL,           -- 1~4
    menu_nm     text     NOT NULL,
    price       integer,                     -- 원. 숫자로 못 읽으면 NULL
    PRIMARY KEY (snapshot, item_seq, menu_no),
    FOREIGN KEY (snapshot, item_seq) REFERENCES raw.good_price_store ON DELETE CASCADE
);

-- ── 출처 ──
INSERT INTO meta.data_source (source_id, title, provider, portal_url, license, attribution_required, attribution_text, raw_tables, notes) VALUES
    ('mois_dining', '행정안전부 지방물가정보 — 개인서비스(외식비) 가격 현황', '행정안전부 (원자료: 국가데이터처 소비자물가조사)',
     'https://www.mois.go.kr/frt/sub/a02/lpid020101/screen.do', NULL, true,
     '출처: 행정안전부 지방물가정보 「개인서비스(외식비) 가격 현황」 (원자료: 국가데이터처)',
     ARRAY['raw.mois_dining_price'],
     '시도 평균. 기관 주석: 시도 간 조사 대상처·품질이 달라 시도 간 비교가 적절하지 않을 수 있음. 이용허락 조건 미확인 — 공개 전 확인할 것.'),
    ('good_price', '행정안전부_착한가격업소 현황', '행정안전부',
     'https://www.data.go.kr/data/3045247/fileData.do', '이용허락범위 제한 없음', false,
     '출처: 공공데이터포털(data.go.kr) 「행정안전부_착한가격업소 현황」',
     ARRAY['raw.good_price_store', 'raw.good_price_menu'],
     '착한가격업소만 모은 표본(일반 가격보다 낮음). 외식비 수준이 아니라 업소 수 지표로 쓸 것.')
ON CONFLICT (source_id) DO UPDATE SET
    title = EXCLUDED.title, provider = EXCLUDED.provider, portal_url = EXCLUDED.portal_url,
    license = EXCLUDED.license, attribution_required = EXCLUDED.attribution_required,
    attribution_text = EXCLUDED.attribution_text, raw_tables = EXCLUDED.raw_tables,
    notes = EXCLUDED.notes, updated_at = now();
