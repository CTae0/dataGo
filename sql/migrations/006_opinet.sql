-- 마이그레이션 006: 오피넷 시군구 유가 (sql/init/10_opinet.sql과 같은 내용)
-- 한국석유공사 오피넷 「시군구별 주유소 평균가격(현재)」 (수집기: opinet_price.py)
--   https://www.opinet.co.kr/api/avgSigunPrice.do?code=<키>&out=json&sido=<오피넷 시도코드>
--   인증키 OPINET_API_KEY. 파라미터 이름은 'code' (웹 안내의 certkey가 아님, 「오피넷 일반 API 이용 가이드」 2026.10).
--   '현재' 가격만 준다 → 하루 한 번 스냅샷으로 쌓아 기간 평균을 만든다. 일 호출 한도 300회 (2026-09부터).
-- 새 DB에서는 이 파일이, 기존 DB에서는 sql/migrations/006_opinet.sql이 같은 내용으로 실행된다.

CREATE TABLE IF NOT EXISTS raw.opinet_sigun_price (
    snapshot    date     NOT NULL,           -- 받은 날 (KST)
    sigun_cd    text     NOT NULL,           -- 오피넷 시군코드 4자리 (예: 0301 춘천, 1901 세종)
    sido_nm     text     NOT NULL,           -- 오피넷 시도 짧은 이름 (서울, 경기, 전남광주 …)
    sigun_nm    text     NOT NULL,           -- 시도 이름을 뗀 시군구 이름 (예: 춘천시, 수원시 — 일반구는 시 단위)
    prodcd      text     NOT NULL,           -- B027 보통휘발유, B034 고급휘발유, D047 자동차용경유, C004 실내등유, K015 자동차용부탄
    price       numeric  NOT NULL,           -- 원/L
    diff        numeric,                     -- 전일 대비
    fetched_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot, sigun_cd, prodcd)
);

INSERT INTO meta.data_source (source_id, title, provider, portal_url, license, attribution_required, attribution_text, raw_tables, notes) VALUES
    ('opinet_price', '한국석유공사 오피넷 — 시군구별 주유소 평균가격', '한국석유공사',
     'https://www.opinet.co.kr/user/custapi/openApiInfoDtl.do?apiId=7', '출처 명시 필수 (오피넷 저작권정책)', true,
     '출처: 한국석유공사 오피넷(www.opinet.co.kr)',
     ARRAY['raw.opinet_sigun_price'],
     '오피넷 저작권정책: 출처가 석유공사임을 반드시 명시, 내용 무단 변경 금지, 수익 목적이면 사전 협의 필요, 다른 사이트에서 링크하면 공사에 통지. 공개 전 확인할 것.')
ON CONFLICT (source_id) DO UPDATE SET
    title = EXCLUDED.title, provider = EXCLUDED.provider, portal_url = EXCLUDED.portal_url, license = EXCLUDED.license,
    attribution_required = EXCLUDED.attribution_required, attribution_text = EXCLUDED.attribution_text,
    raw_tables = EXCLUDED.raw_tables, notes = EXCLUDED.notes, updated_at = now();
