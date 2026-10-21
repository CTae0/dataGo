"""
어디 살까? 수집 DAG 모음 (Airflow 3)

모든 태스크는 프로젝트 코드(/opt/eodi)의 CLI를 그대로 부른다. 수집기는
  - 받은 기록(fetch_log)을 보고 이어받고,
  - API별 하루 호출 예산(meta.api_usage, pipeline/quota.py)에 닿으면 정상 종료한다.
그래서 백필 DAG는 매일 같은 명령을 돌리기만 하면 며칠에 걸쳐 끝까지 받는다.

시간은 모두 KST. data.go.kr 일일 한도는 자정(KST)에 초기화된다.
"""
import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

TZ = pendulum.timezone("Asia/Seoul")
START = pendulum.datetime(2026, 10, 1, tz=TZ)
CD = "cd /opt/eodi && "
LAST_MONTH = '$(date -d "$(date +%Y-%m-01) -1 day" +%Y%m)'
DEFAULTS = {"owner": "eodi", "retries": 1, "retry_delay": pendulum.duration(minutes=10)}


def bash(task_id, cmd, **kw):
    return BashOperator(task_id=task_id, bash_command=CD + cmd, env={"PYTHONIOENCODING": "utf-8"},
                        append_env=True, **kw)


# ── 국토부 전월세 ──────────────────────────────────────────
with DAG("eodi_rent_backfill", schedule="0 1 * * *", start_date=START, catchup=False, max_active_runs=1,
         default_args=DEFAULTS, tags=["eodi", "rent", "backfill"],
         doc_md="전국 시군구 × 4유형 × 2023-01~지난달. 안 받은 묶음만, 하루 예산 안에서. 다 받으면 할 일 없이 끝난다."):
    bash("fetch_missing", f"python molit_rent.py fetch --from 202301 --to {LAST_MONTH} --recent-months 0 "
                          "--max-calls 40000", execution_timeout=pendulum.duration(hours=20))

with DAG("eodi_rent_monthly", schedule="0 3 5 * *", start_date=START, catchup=False, max_active_runs=1,
         default_args=DEFAULTS, tags=["eodi", "rent"],
         doc_md="매월 5일: 최근 3개월을 다시 받는다 (신고 기한 30일이라 늦게 들어오는 거래 반영)."):
    bash("refresh_recent", "python molit_rent.py fetch --months-back 3 --recent-months 4 --max-calls 15000",
         execution_timeout=pendulum.duration(hours=10))

# ── 소비자원 생필품 가격 ───────────────────────────────────
with DAG("eodi_kca_weekly", schedule="0 6 * * 6", start_date=START, catchup=False, max_active_runs=1,
         default_args=DEFAULTS, tags=["eodi", "grocery"],
         doc_md="토요일 06시: 판매점·상품 갱신 → 최근 6주 조사일 확인 → 최근 조사일 2개 가격 (격주 금요일 조사)."):
    meta = bash("meta", "python kca_price.py meta")
    days = bash("days", "python kca_price.py days --from $(date -d '-42 days' +%F)")
    prices = bash("prices", "python kca_price.py --max-calls 1800 prices --latest 2",
                  execution_timeout=pendulum.duration(hours=3))
    meta >> days >> prices

with DAG("eodi_kca_backfill", schedule="0 9 * * *", start_date=START, catchup=False, max_active_runs=1,
         default_args=DEFAULTS, tags=["eodi", "grocery", "backfill"],
         doc_md="매일 09시(주간 작업 뒤): 2018년부터 조사일 찾기 → 덜 받은 조사일을 최근 것부터. 하루 예산 안에서."):
    days = bash("days", "python kca_price.py days --from 2018-01-01")
    prices = bash("prices", "python kca_price.py --max-calls 1900 prices --pending",
                  execution_timeout=pendulum.duration(hours=4))
    days >> prices

# ── 기준·공공요금 (월간) ───────────────────────────────────
with DAG("eodi_reference_monthly", schedule="0 4 2 * *", start_date=START, catchup=False, max_active_runs=1,
         default_args=DEFAULTS, tags=["eodi", "utility"],
         doc_md="매월 2일: 상하수도·종량제봉투 표준데이터, 행안부 지방공공요금(3045228) → 합치기 → 적재 → 지역 매핑."):
    std = bash("std_fees", "python std_fees.py")
    fee_dl = bash("public_fee_download", "python datago_periodic.py 3045228 --out ./data/public_fee")
    fee_merge = bash("public_fee_merge", "python merge_public_fee.py --src ./data/public_fee")
    fee_load = bash("public_fee_load", "python -m pipeline.run_sql sql/load_public_fee.sql")
    xwalk = bash("region_xwalk", "python -m pipeline.region_xwalk")
    fee_dl >> fee_merge >> fee_load
    [std, fee_load] >> xwalk

# ── 외식비 (월간) ───────────────────────────────────────────
with DAG("eodi_dining_monthly", schedule="0 5 15 * *", start_date=START, catchup=False, max_active_runs=1,
         default_args=DEFAULTS, tags=["eodi", "dining"],
         doc_md="매월 15일: 행안부 지방물가정보 외식비(시도, 최근 12개월 다시 받고 참가격과 대조) → "
                "착한가격업소 최신 스냅샷(분기 파일) → 지역 매핑 갱신. 집계는 eodi_build_mart가 한다. "
                "조사 근거: docs/research/dining_sources.md"):
    dining = bash("mois_dining", "python mois_dining.py", execution_timeout=pendulum.duration(minutes=30))
    good = bash("good_price", "python good_price.py --latest-only", execution_timeout=pendulum.duration(minutes=30))
    xwalk = bash("region_xwalk", "python -m pipeline.region_xwalk")
    [dining, good] >> xwalk

# ── 한전 가구 전력 (월간) ──────────────────────────────────
with DAG("eodi_power_monthly", schedule="0 6 20 * *", start_date=START, catchup=False, max_active_runs=1,
         default_args=DEFAULTS, tags=["eodi", "utility", "power"],
         doc_md="매월 20일: 한전 전력데이터개방포털 가구평균 전력사용량(시군구 × 월, 보통 2달 늦게 올라옴). "
                "안 받은 달 + 최근 3개월 다시 확인 → 지역 매핑 갱신. 집계는 eodi_build_mart가 한다."):
    power = bash("kepco_power", "python kepco_power.py", execution_timeout=pendulum.duration(hours=2))
    xwalk = bash("region_xwalk", "python -m pipeline.region_xwalk")
    power >> xwalk

# ── 오피넷 유가 (매일) ─────────────────────────────────────
with DAG("eodi_fuel_daily", schedule="30 10 * * *", start_date=START, catchup=False, max_active_runs=1,
         default_args=DEFAULTS, tags=["eodi", "fuel"],
         doc_md="매일 10:30 (오피넷 9시 갱신 뒤): 시군구별 주유소 평균가격 '현재' 값을 하루 스냅샷으로 쌓는다 "
                "(호출 17번 남짓, 한도 300회/일). 새 시군코드가 생길 수 있어 지역 매핑도 갱신."):
    fuel = bash("opinet_price", "python opinet_price.py", execution_timeout=pendulum.duration(minutes=20))
    xwalk = bash("region_xwalk", "python -m pipeline.region_xwalk")
    fuel >> xwalk

# ── 지도용 집계 (매일 밤) ──────────────────────────────────
with DAG("eodi_build_mart", schedule="30 23 * * *", start_date=START, catchup=False, max_active_runs=1,
         default_args=DEFAULTS, tags=["eodi", "mart"],
         doc_md="매일 23:30: sql/mart/*.sql을 다시 만든다 (전월세·공공요금·장바구니·외식비·전기·유가 → 요약). "
                "외식비(mart.dining_region)는 API가 요약 표와 함께 읽는다."):
    rent = bash("rent", "python -m pipeline.run_sql sql/mart/10_rent.sql")
    utility = bash("utility", "python -m pipeline.run_sql sql/mart/20_utility.sql")
    grocery = bash("grocery", "python -m pipeline.run_sql sql/mart/30_grocery.sql")
    dining = bash("dining", "python -m pipeline.run_sql sql/mart/40_dining.sql")
    # 바다·공항·광역시권·그림 유형 (경계는 연 1회 바뀌지만 2분 남짓이라 매일 다시 만든다)
    features = bash("region_features", "python -m pipeline.run_sql sql/mart/50_region_features.sql")
    power = bash("power", "python -m pipeline.run_sql sql/mart/60_power.sql")
    fuel = bash("fuel", "python -m pipeline.run_sql sql/mart/70_fuel.sql")
    summary = bash("region_summary", "python -m pipeline.run_sql sql/mart/90_region_summary.sql")
    [rent, utility, grocery, dining, features, power, fuel] >> summary

# ── 지역 기준 (연간) ───────────────────────────────────────
with DAG("eodi_dim_region_yearly", schedule="0 3 20 7 *", start_date=START, catchup=False, max_active_runs=1,
         default_args=DEFAULTS, tags=["eodi", "dim"],
         doc_md="7월 20일: 국토교통부_전국 법정동(매년 7월 갱신)을 받아 dim.region을 다시 만들고 매핑을 갱신한다."):
    region = bash("dim_region", "python -m pipeline.dim_region --download")
    xwalk = bash("region_xwalk", "python -m pipeline.region_xwalk")
    region >> xwalk
