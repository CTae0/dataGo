-- Airflow 메타데이터용 DB (같은 Postgres 인스턴스, 별도 DB·계정). 로컬 개발용 비밀번호.
-- 이미 만든 볼륨에는 직접 실행: docker compose exec -T db psql -U eodi -d eodi -f /docker-entrypoint-initdb.d/00_airflow_db.sql
SELECT 'CREATE ROLE airflow LOGIN PASSWORD ''airflow'''
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'airflow')\gexec
SELECT 'CREATE DATABASE airflow OWNER airflow'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'airflow')\gexec
