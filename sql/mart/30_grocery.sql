-- mart.grocery_region: 시군구(leaf) 장바구니 물가 지수 (전국 중위 = 100)
-- 원천: raw.kca_price / kca_store / kca_product (한국소비자원 참가격) [출처표시: meta.data_source 'kca_price']
--
-- 방법 (빠진 상품이 있어도 비교되도록 상대가격 지수):
--   1) 최근 조사일 2회의 상품별 전국 중위가격
--   2) 판매점 지수 = exp(평균(ln(가격 / 전국 중위)))  — 그 점포 상품들의 기하평균 상대가격
--      (상품을 30개 이상 조사한 점포만)
--   3) 시군구 지수 = 그 시군구 점포 지수의 중위 × 100.  점포가 없으면 같은 시도의 중위로 대체(granularity 'sido')
--   4) 대분류(신선식품·가공식품·생활용품)별로도 같은 방식
-- 한계: 대형마트·SSM·백화점 체인만 조사(전통시장 없음). 체인 가격은 지역 차이가 작다.

DROP TABLE IF EXISTS mart.grocery_store_index;
CREATE TABLE mart.grocery_store_index AS
WITH days AS (SELECT inspect_day FROM raw.kca_survey_day WHERE has_data
              AND inspect_day IN (SELECT DISTINCT inspect_day FROM raw.kca_price)
              ORDER BY inspect_day DESC LIMIT 2),
p AS (
    SELECT pr.inspect_day, pr.entp_id, pr.good_id, pr.price, l1.code_name AS category
    FROM raw.kca_price pr JOIN days USING (inspect_day)
    JOIN raw.kca_product g ON g.good_id = pr.good_id
    LEFT JOIN raw.kca_code l3 ON l3.class_code = 'AL' AND l3.code = g.small_class_code
    LEFT JOIN raw.kca_code l2 ON l2.class_code = 'AL' AND l2.code = l3.high_code
    LEFT JOIN raw.kca_code l1 ON l1.class_code = 'AL' AND l1.code = l2.high_code
    WHERE pr.price > 0
),
nat AS (SELECT inspect_day, good_id, percentile_cont(0.5) WITHIN GROUP (ORDER BY price) AS med FROM p GROUP BY 1, 2),
rel AS (SELECT p.entp_id, p.category, ln(p.price / n.med) AS lr FROM p JOIN nat n USING (inspect_day, good_id))
SELECT entp_id, 'all'::text AS category, count(*) AS n_prices, exp(avg(lr)) AS store_index
FROM rel GROUP BY entp_id HAVING count(*) >= 30
UNION ALL
SELECT entp_id, category, count(*), exp(avg(lr))
FROM rel WHERE category IS NOT NULL GROUP BY entp_id, category HAVING count(*) >= 10;

DROP TABLE IF EXISTS mart.grocery_region;
CREATE TABLE mart.grocery_region AS
WITH store_region AS (   -- 판매점 → leaf (일반구 없는 시 단위 코드면 여러 leaf에 같은 값)
    SELECT s.entp_id, s.type_code, x.region_code, x.granularity
    FROM raw.kca_store s JOIN dim.region_xwalk x ON x.source_id = 'kca_store' AND x.source_key = s.area_detail_code
),
leaf_val AS (
    SELECT sr.region_code, i.category, count(DISTINCT i.entp_id) AS stores,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY i.store_index) * 100 AS idx,
           min(sr.granularity) AS granularity,
           string_agg(DISTINCT sr.type_code, ',') AS store_types
    FROM mart.grocery_store_index i JOIN store_region sr USING (entp_id)
    GROUP BY 1, 2
),
sido_val AS (
    SELECT r.sido_code, i.category, count(DISTINCT i.entp_id) AS stores,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY i.store_index) * 100 AS idx
    FROM mart.grocery_store_index i JOIN store_region sr USING (entp_id)
    JOIN dim.region r ON r.region_code = sr.region_code
    GROUP BY 1, 2
),
cats AS (SELECT DISTINCT category FROM mart.grocery_store_index)
SELECT r.region_code, c.category,
       coalesce(l.idx, s.idx)                                         AS price_index,
       CASE WHEN l.idx IS NOT NULL THEN l.granularity
            WHEN s.idx IS NOT NULL THEN 'sido' END                    AS granularity,
       coalesce(l.stores, 0)                                          AS stores_in_region,
       s.stores                                                       AS stores_in_sido,
       l.store_types
FROM dim.region r CROSS JOIN cats c
LEFT JOIN leaf_val l ON l.region_code = r.region_code AND l.category = c.category
LEFT JOIN sido_val s ON s.sido_code = r.sido_code AND s.category = c.category
WHERE r.is_leaf;
ALTER TABLE mart.grocery_region ADD PRIMARY KEY (region_code, category);
