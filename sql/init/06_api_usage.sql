-- API별 하루 호출 수 (data.go.kr 일일 한도는 API(서비스)마다 따로, 자정 KST에 초기화)
-- 수집기(molit_rent.py, kca_price.py)가 호출할 때마다 +1 하고, 한도에 닿으면 멈춘다. → pipeline/quota.py
CREATE TABLE IF NOT EXISTS meta.api_usage (
    api    text NOT NULL,      -- molit_apt_rent, molit_offi_rent, molit_sh_rent, molit_rh_rent, kca_price …
    day    date NOT NULL,      -- KST 기준 날짜
    calls  integer NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (api, day)
);
