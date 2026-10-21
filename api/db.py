"""
API 전용 DB 접속 (수집 코드 molit_rent.py에 기대지 않는다 → API 컨테이너에는 api/ 폴더만 들어간다)

- 로컬 실행: 프로젝트 루트 .env를 읽는다 (POSTGRES_HOST 기본 localhost, POSTGRES_PORT 기본 5433)
- 컨테이너(docker-compose의 api 서비스): compose가 POSTGRES_HOST=db, POSTGRES_PORT=5432를 넣어 준다
"""
import os
from pathlib import Path

import psycopg2

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_env(path=ENV_FILE):
    """이미 있는 환경변수는 덮어쓰지 않는다 (컨테이너 설정이 우선)"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def connect():
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", 5433)),
        dbname=os.environ.get("POSTGRES_DB", "eodi"),
        user=os.environ.get("POSTGRES_USER", "eodi"),
        password=os.environ.get("POSTGRES_PASSWORD", "eodi_local"),
        connect_timeout=5,
    )
