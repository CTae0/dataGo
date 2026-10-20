"""
SQL 파일을 실행한다 (Airflow 컨테이너에는 psql이 없어서 파이썬으로 돌린다).

사용법: python -m pipeline.run_sql sql/load_public_fee.sql [더 많은 파일 …]
- 파일 안의 COPY ... FROM '/data/...'는 DB 컨테이너 기준 경로다 (docker-compose에서 ./data → /data).
- 마지막 문장이 SELECT면 결과를 출력한다.
"""
import sys
from pathlib import Path

import molit_rent as common


def run(path, conn):
    sql = Path(path).read_text(encoding="utf-8")
    with conn, conn.cursor() as cur:
        cur.execute(sql)
        if cur.description:
            cols = [d[0] for d in cur.description]
            print(" | ".join(cols))
            for row in cur.fetchall():
                print(" | ".join("" if v is None else str(v) for v in row))
    for n in conn.notices:
        print(n.strip())
    conn.notices.clear()
    print(f"[완료] {path}")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    common.load_env()
    conn = common.connect()
    try:
        for p in sys.argv[1:]:
            run(p, conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
