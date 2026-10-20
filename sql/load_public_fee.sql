-- merge_public_fee.py 결과를 raw.mois_public_fee에 다시 적재한다 (여러 번 돌려도 같은 결과).
-- 실행: docker compose exec db psql -U eodi -d eodi -f /sql/load_public_fee.sql
BEGIN;

CREATE TEMP TABLE stg_public_fee (LIKE raw.mois_public_fee INCLUDING DEFAULTS) ON COMMIT DROP;
ALTER TABLE stg_public_fee DROP COLUMN loaded_at;

-- CSV는 BOM이 붙은 UTF-8이다. PostgreSQL COPY는 첫 컬럼명에 BOM이 남지만 HEADER로 건너뛰므로 문제없다.
COPY stg_public_fee (ym, level, sido, sigungu, category, item, value, raw_column, source_name, source_file, reg_date)
FROM '/data/public_fee/merged/public_fee_long.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8', FORCE_NOT_NULL (sigungu));

TRUNCATE raw.mois_public_fee;
INSERT INTO raw.mois_public_fee (ym, level, sido, sigungu, category, item, value, raw_column, source_name, source_file, reg_date)
SELECT ym, level, sido, coalesce(sigungu, ''), category, item, value, raw_column, source_name, source_file, reg_date
FROM stg_public_fee;

COMMIT;

SELECT level, count(*) AS rows, min(ym) AS from_ym, max(ym) AS to_ym
FROM raw.mois_public_fee GROUP BY level ORDER BY level;

-- 강원 시군구 값이 dim.region과 이름으로 모두 연결되는지 확인 (결과가 비어 있어야 정상)
SELECT DISTINCT f.sigungu AS unmatched_gangwon_sigungu
FROM raw.mois_public_fee f
LEFT JOIN dim.region r ON r.sido = f.sido AND r.sigungu = f.sigungu
WHERE f.level = 'sigungu' AND f.sido = '강원' AND r.region_code IS NULL;
