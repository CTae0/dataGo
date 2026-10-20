-- 이미 만들어진 DB에 적용: raw.molit_rent를 item_seq 기준으로 바꾼다.
-- 아직 수집 전이라 테이블을 다시 만든다 (데이터가 있으면 지워지므로 주의).
-- 실행: docker compose exec -T db psql -U eodi -d eodi -f /sql/migrations/001_molit_rent_item_seq.sql
BEGIN;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM raw.molit_rent LIMIT 1) THEN
        RAISE EXCEPTION 'raw.molit_rent에 데이터가 있습니다. 직접 옮긴 뒤 실행하세요.';
    END IF;
END $$;
DROP TABLE raw.molit_rent;
CREATE TABLE raw.molit_rent (
    house_type      text        NOT NULL CHECK (house_type IN ('apt', 'officetel', 'detached', 'row_house')),
    lawd_cd         char(5)     NOT NULL,
    deal_ym         char(6)     NOT NULL,
    item_seq        integer     NOT NULL,
    payload         jsonb       NOT NULL,
    deposit         bigint,
    monthly_rent    bigint,
    area_m2         numeric,
    fetched_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (house_type, lawd_cd, deal_ym, item_seq)
);
COMMIT;
