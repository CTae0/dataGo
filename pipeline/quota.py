"""
API별 하루 호출 예산. 여러 수집 작업(Airflow 태스크, 수동 실행)이 같은 한도를 나눠 쓰도록 DB에 센다.

data.go.kr 일일 한도는 서비스(API)마다 따로이고 자정(KST)에 초기화된다.
  - 국토부 전월세 4종: 각각 10,000회 (개발계정)
  - 소비자원 생필품 가격: 2,000회 (개발계정)
운영계정으로 늘면 LIMITS만 바꾸면 된다 (또는 환경변수 QUOTA_<API>=숫자).
"""
import os
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
LIMITS = {
    "molit_apt_rent": 10000, "molit_offi_rent": 10000, "molit_sh_rent": 10000, "molit_rh_rent": 10000,
    "kca_price": 2000,
    "opinet": 300,       # 오피넷 일반 API (2026-09부터 300회/일)
    "kepco": 10000,      # 한전 전력데이터개방포털 (한도 공개 안 됨, 넉넉히 둠)
    "nmc_hospital": 1000, "nmc_pharmacy": 1000, "nmc_emergency": 1000,   # 국립중앙의료원 (개발계정)
    "airkorea_stats": 500,   # 에어코리아 대기오염통계 (개발계정)
}
RESERVE = 100   # 수동 확인용으로 남겨 두는 호출 수


class QuotaExceeded(RuntimeError):
    pass


class Quota:
    def __init__(self, conn):
        self.conn = conn

    @staticmethod
    def today():
        return datetime.now(KST).date()

    def limit(self, api):
        return int(os.environ.get(f"QUOTA_{api.upper()}", LIMITS.get(api, 1000)))

    def used(self, api):
        with self.conn.cursor() as cur:
            cur.execute("SELECT calls FROM meta.api_usage WHERE api = %s AND day = %s", (api, self.today()))
            row = cur.fetchone()
        return row[0] if row else 0

    def remaining(self, api):
        return max(0, self.limit(api) - RESERVE - self.used(api))

    def use(self, api):
        """호출 1회를 기록한다. 예산이 없으면 QuotaExceeded."""
        with self.conn, self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO meta.api_usage (api, day, calls) VALUES (%s, %s, 1)
                ON CONFLICT (api, day) DO UPDATE SET calls = meta.api_usage.calls + 1, updated_at = now()
                RETURNING calls""", (api, self.today()))
            calls = cur.fetchone()[0]
        if calls > self.limit(api) - RESERVE:
            raise QuotaExceeded(f"{api} 오늘 호출 예산을 다 썼습니다 ({calls}/{self.limit(api)}, 예비 {RESERVE}). "
                                "내일(자정 KST 이후) 다시 실행하면 이어서 받습니다.")
