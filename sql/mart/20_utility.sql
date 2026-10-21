-- mart.utility_region: 시군구(leaf) × 항목 1행, 가장 정밀한 원천 하나를 고른다.
-- 원천 [출처 표시 필요]: std_trash_bag_price, std_water_sewage_fee (시군구), mois_public_fee (시도 평균)
--
-- 항목: trash_20l(원/장), water_20m3·sewer_20m3(원/월, 20㎥ 사용), gas_total(원/월 환산), bus_card, taxi(원)
-- 우선순위: 시군구 값(exact) > 구를 둔 시 값(si) > 옛 시군구(legacy) > 시도 평균(sido / sido_part)
-- 상하수도 20㎥: 표준데이터 구간 단가 × 구간에 든 사용량의 합. 기본요금은 표준데이터에 없어 빠져 있다(과소 추정).

DROP TABLE IF EXISTS mart.utility_candidates;
CREATE TABLE mart.utility_candidates AS
WITH
-- 종량제봉투: 가정용 생활쓰레기 규격봉투 20ℓ (사용대상 표기가 제각각이라 '가정'이 들어간 것)
trash AS (
    SELECT t.sido_nm || '|' || t.sigungu_nm AS source_key,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY t.price_20l) AS value, max(t.data_date) AS ref_date
    FROM raw.std_trash_bag_price t
    WHERE t.price_20l IS NOT NULL AND t.target LIKE '%가정%' AND t.purpose = '생활쓰레기' AND t.bag_type = '규격봉투'
    GROUP BY 1
),
-- 상하수도: 가정용 구간 단가로 20㎥ 요금
tiers AS (
    SELECT instt_nm AS source_key, kind, sector, unit_price, data_date,
           CASE WHEN usage_from > 0 THEN usage_from - 1 ELSE 0 END AS lo,
           CASE WHEN usage_to IS NULL OR usage_to = 0 OR usage_to >= 9999999 THEN 1e9 ELSE usage_to END AS hi
    FROM raw.std_water_sewage_fee
    WHERE sector LIKE '가정%' AND unit_price IS NOT NULL
),
tier_sector AS (   -- 기관마다 '가정용'이 여러 갈래면 정확히 '가정용'을 먼저
    SELECT DISTINCT ON (source_key, kind) source_key, kind, sector
    FROM tiers ORDER BY source_key, kind, (sector = '가정용') DESC, sector
),
-- 1㎥씩 20번: 그 ㎥가 속한 구간의 단가를 더한다. 구간이 겹치면(원천에 같은 시작점 행이 수천 개인 기관이 있다,
-- 예: 군포시 '1~3928', '1~559354' …) 겹친 단가의 중위값 → 행이 몇 개든 20㎥ 요금이 부풀지 않는다.
per_m3 AS (
    SELECT t.source_key, t.kind, m.n,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY t.unit_price) AS price, max(t.data_date) AS data_date
    FROM tiers t JOIN tier_sector s USING (source_key, kind, sector)
    CROSS JOIN generate_series(1, 20) AS m(n)
    WHERE m.n > t.lo AND m.n <= t.hi
    GROUP BY 1, 2, 3
),
water AS (
    SELECT source_key, CASE kind WHEN '상수도' THEN 'water_20m3' ELSE 'sewer_20m3' END AS item,
           sum(price) AS value, max(data_date) AS ref_date
    FROM per_m3
    GROUP BY 1, 2
    HAVING count(*) = 20     -- 1~20㎥를 다 덮는 구간표만 (빈 구간이 있으면 신뢰하지 않음)
),
-- 행안부 시도 평균: 최신 연월
mois_last AS (SELECT max(ym) AS ym FROM raw.mois_public_fee WHERE level = 'sido'),
mois AS (
    SELECT f.sido AS source_key, f.item, f.value, to_date(f.ym || '-01', 'YYYY-MM-DD') AS ref_date
    FROM raw.mois_public_fee f, mois_last l
    WHERE f.level = 'sido' AND f.ym = l.ym
      AND f.item IN ('water_20m3', 'sewer_20m3', 'trash_20l', 'gas_total', 'bus_card', 'taxi')
)
SELECT x.region_code, 'trash_20l'::text AS item, t.value, x.granularity, 'std_trash_bag_price'::text AS source_id, t.ref_date
FROM trash t JOIN dim.region_xwalk x ON x.source_id = 'std_trash' AND x.source_key = t.source_key
UNION ALL
SELECT x.region_code, w.item, w.value, x.granularity, 'std_water_sewage_fee', w.ref_date
FROM water w JOIN dim.region_xwalk x ON x.source_id = 'std_water' AND x.source_key = w.source_key
UNION ALL
SELECT x.region_code, m.item, m.value, x.granularity, 'mois_public_fee', m.ref_date
FROM mois m JOIN dim.region_xwalk x ON x.source_id = 'mois_public_fee' AND x.source_key = m.source_key;

DROP TABLE IF EXISTS mart.utility_region;
CREATE TABLE mart.utility_region AS
SELECT DISTINCT ON (region_code, item) region_code, item, value, granularity, source_id, ref_date
FROM mart.utility_candidates
ORDER BY region_code, item,
         CASE granularity WHEN 'exact' THEN 1 WHEN 'si' THEN 2 WHEN 'legacy' THEN 3
                          WHEN 'sido_part' THEN 4 ELSE 5 END,
         ref_date DESC NULLS LAST;
ALTER TABLE mart.utility_region ADD PRIMARY KEY (region_code, item);
