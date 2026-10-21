-- mart.dining_region: 시군구(leaf) 외식비 — 1행 = leaf
-- 원천
--   raw.mois_dining_price  행안부 지방물가정보 외식비 (시도 × 9품목 × 월) [출처: meta.data_source 'mois_dining']
--   raw.good_price_store   행안부 착한가격업소 (업소, 분기)                [출처: 'good_price']
-- 조사·선택 이유: docs/research/dining_sources.md
--
-- 방법
--   1) 품목 가격 = 가장 최근 달의 시도 값을 그 시도의 모든 leaf에 그대로 쓴다 (dining_gran = 'sido' / 'sido_part').
--      세종은 충남 값 (기관 주석: 세종 가격은 충남에 포함). 시군구 고유 값이 아니므로 화면에 '시도 평균'으로 표시할 것.
--   2) meal_avg = 일상 한 끼 5종(냉면·비빔밥·김치찌개 백반·짜장면·칼국수) 단순 평균.
--      meal_index = meal_avg / 16개 시도 meal_avg 평균 × 100
--      meal_yoy_pct = 12개월 전 같은 방식 meal_avg 대비 증감률(%)
--   3) 착한가격업소 수 = 최신 스냅샷 외식업 업소 수. 착한가격업소는 싼 가게만 모은 표본이라 '가격 수준'이 아니라
--      '가성비 식당이 얼마나 있나' 지표로만 쓴다. 원천이 시 단위(예: 수원시)면 일반구 leaf마다 시 전체 수가 들어간다
--      (good_price_gran = 'si').
-- 한계: 기관 주석 — 시도 간 조사 대상처·품질이 같지 않아 시도 간 가격 비교가 적절하지 않을 수 있음.

DROP TABLE IF EXISTS mart.dining_sido;
CREATE TABLE mart.dining_sido AS
WITH latest AS (SELECT max(ym) AS ym FROM raw.mois_dining_price),
prev AS (SELECT to_char(to_date(ym, 'YYYYMM') - interval '12 months', 'YYYYMM') AS ym FROM latest),
p AS (
    SELECT d.ym, d.sido, d.item_cd, d.price
    FROM raw.mois_dining_price d
    WHERE d.ym IN (SELECT ym FROM latest UNION ALL SELECT ym FROM prev)
),
meal AS (   -- 일상 한 끼 5종: BA 냉면, BB 비빔밥, BC 김치찌개 백반, BF 짜장면, BH 칼국수
    SELECT ym, sido, avg(price) AS meal_avg, count(*) AS n_items
    FROM p WHERE item_cd IN ('BA', 'BB', 'BC', 'BF', 'BH') GROUP BY 1, 2
)
SELECT (SELECT ym FROM latest) AS ym, p.sido,
       max(p.price) FILTER (WHERE p.item_cd = 'BA') AS naengmyeon,
       max(p.price) FILTER (WHERE p.item_cd = 'BB') AS bibimbap,
       max(p.price) FILTER (WHERE p.item_cd = 'BC') AS kimchi_jjigae,
       max(p.price) FILTER (WHERE p.item_cd = 'BE') AS samgyeopsal_200g,   -- 삼겹살 환산 후(200g)
       max(p.price) FILTER (WHERE p.item_cd = 'BF') AS jajangmyeon,
       max(p.price) FILTER (WHERE p.item_cd = 'BG') AS samgyetang,
       max(p.price) FILTER (WHERE p.item_cd = 'BH') AS kalguksu,
       max(p.price) FILTER (WHERE p.item_cd = 'BI') AS gimbap,            -- 1줄
       round(m.meal_avg)                                                   AS meal_avg,
       round(m.meal_avg / avg(m.meal_avg) OVER () * 100, 1)                AS meal_index,
       round((m.meal_avg / m0.meal_avg - 1) * 100, 1)                      AS meal_yoy_pct
FROM p
JOIN meal m ON m.ym = p.ym AND m.sido = p.sido AND m.n_items = 5
LEFT JOIN meal m0 ON m0.sido = p.sido AND m0.ym = (SELECT ym FROM prev) AND m0.n_items = 5
WHERE p.ym = (SELECT ym FROM latest)
GROUP BY p.sido, m.meal_avg, m0.meal_avg;
ALTER TABLE mart.dining_sido ADD PRIMARY KEY (sido);

DROP TABLE IF EXISTS mart.dining_region;
CREATE TABLE mart.dining_region AS
WITH price AS (
    SELECT x.region_code, x.granularity AS dining_gran, s.*
    FROM mart.dining_sido s
    JOIN dim.region_xwalk x ON x.source_id = 'mois_dining' AND x.source_key = s.sido
),
gp_snap AS (SELECT max(snapshot) AS snapshot FROM raw.good_price_store),
gp AS (     -- 원천 키(시도|시군)별 외식업 업소 수 → leaf
    SELECT x.region_code, sum(k.n) AS stores, min(x.granularity) AS gran
    FROM (SELECT sido_nm || '|' || coalesce(sigungu_nm, '') AS source_key, count(*) AS n
          FROM raw.good_price_store
          WHERE snapshot = (SELECT snapshot FROM gp_snap) AND is_dining
          GROUP BY 1) k
    JOIN dim.region_xwalk x ON x.source_id = 'good_price' AND x.source_key = k.source_key
    GROUP BY 1
)
SELECT r.region_code, r.sido, r.sigungu,
       price.ym AS dining_ym, price.dining_gran,
       price.naengmyeon, price.bibimbap, price.kimchi_jjigae, price.samgyeopsal_200g,
       price.jajangmyeon, price.samgyetang, price.kalguksu, price.gimbap,
       price.meal_avg, price.meal_index, price.meal_yoy_pct,
       (SELECT snapshot FROM gp_snap)  AS good_price_snapshot,
       coalesce(gp.stores, 0)          AS good_price_dining_stores,
       gp.gran                         AS good_price_gran,
       ARRAY['mois_dining', 'good_price'] AS sources,
       now() AS built_at
FROM dim.region r
LEFT JOIN price USING (region_code)
LEFT JOIN gp USING (region_code)
WHERE r.is_leaf;
ALTER TABLE mart.dining_region ADD PRIMARY KEY (region_code);

SELECT dining_gran, count(*) AS leaves, count(meal_avg) AS with_price,
       min(meal_avg) AS min_meal, max(meal_avg) AS max_meal,
       count(*) FILTER (WHERE good_price_dining_stores > 0) AS with_good_price,
       sum(good_price_dining_stores) FILTER (WHERE good_price_gran IS DISTINCT FROM 'si') AS gp_stores_non_si
FROM mart.dining_region GROUP BY 1 ORDER BY 1;
