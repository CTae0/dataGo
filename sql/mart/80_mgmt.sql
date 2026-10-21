-- mart.mgmt_region: 시군구(leaf) 아파트 ㎡당 월 관리비 — 1행 = leaf
-- 원천: raw.kapt_complex, raw.kapt_fee  K-apt 관리비공개의무단지 기본·면적·관리비 정보 (주 1회) [출처: 'kapt_fee']
-- 방법
--   1) 단지 × 월 ㎡당 관리비 = (공용관리비 합계 + 장기수선충당금 월부과액) ÷ 관리비부과면적.
--      개별사용료(전기·수도·가스·난방 등)는 생활비의 다른 항목과 겹쳐 뺀다.
--      ㎡당 100원 미만·2만 원 초과는 입력 오류로 보고 버린다.
--   2) 단지 값 = 최근 12개월(받은 마지막 달 기준) 평균.
--   3) leaf 값 = 단지 값의 중위값. 단지가 MIN 5곳 미만인 leaf는 같은 시도 leaf들의 단지 전체 중위값 (mgmt_gran = 'sido').
-- 한계: 관리비 공개 의무단지(대체로 150세대 이상·승강기·중앙난방 등)만 있다. 작은 단지·빌라는 들어 있지 않다.
DROP TABLE IF EXISTS mart.mgmt_region;
CREATE TABLE mart.mgmt_region AS
WITH last AS (SELECT max(ym) AS ym FROM raw.kapt_fee),
m AS (
    SELECT f.kapt_code, f.ym, (f.common_total + coalesce(f.ltrm_repair, 0)) / c.mgmt_area AS per_m2
    FROM raw.kapt_fee f JOIN raw.kapt_complex c USING (kapt_code), last
    WHERE c.mgmt_area > 0 AND f.common_total > 0
      AND f.ym > to_char(to_date(last.ym, 'YYYYMM') - interval '12 months', 'YYYYMM')
),
cx AS (
    SELECT m.kapt_code, avg(m.per_m2) AS per_m2, count(*) AS months
    FROM m WHERE m.per_m2 BETWEEN 100 AND 20000 GROUP BY m.kapt_code
),
leaf AS (
    SELECT x.region_code, cx.per_m2
    FROM cx JOIN raw.kapt_complex c USING (kapt_code)
    JOIN dim.region_xwalk x ON x.source_id = 'kapt' AND x.source_key = c.sido || '|' || c.sigungu
),
by_leaf AS (
    SELECT region_code, count(*) AS n, percentile_cont(0.5) WITHIN GROUP (ORDER BY per_m2) AS med
    FROM leaf GROUP BY region_code
),
by_sido AS (
    SELECT r.sido_code, percentile_cont(0.5) WITHIN GROUP (ORDER BY l.per_m2) AS med
    FROM leaf l JOIN dim.region r USING (region_code) GROUP BY r.sido_code
)
SELECT r.region_code,
       (SELECT ym FROM last)                                       AS mgmt_to_ym,
       coalesce(b.n, 0)::int                                       AS mgmt_complexes,
       round((CASE WHEN b.n >= 5 THEN b.med ELSE s.med END)::numeric) AS mgmt_per_m2,   -- 원/㎡/월
       CASE WHEN b.n >= 5 THEN 'exact' ELSE 'sido' END             AS mgmt_gran
FROM dim.region r
LEFT JOIN by_leaf b USING (region_code)
LEFT JOIN by_sido s ON s.sido_code = r.sido_code
WHERE r.is_leaf;
ALTER TABLE mart.mgmt_region ADD PRIMARY KEY (region_code);
