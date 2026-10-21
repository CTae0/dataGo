# 공개 배포 — 내 PC를 임시 서버로 (Docker + ngrok) + Vercel 화면

## 지금 상태 (2026-10-22 적용)
- 화면: https://wherelive-phi.vercel.app (Vercel, Root Directory `web`, `web/.env.production`의 `VITE_API_BASE`)
- API: https://headset-fretted-pang.ngrok-free.dev → Docker `tunnel`(ngrok) → `api`(FastAPI) → `db`
- 두 컨테이너는 `restart: unless-stopped` → Docker Desktop이 켜지면 같이 켜진다. PC가 꺼지거나 잠들면 사이트 데이터가 멈추고 '서버가 쉬는 중' 안내가 나온다.

```bash
docker compose up -d --build api tunnel   # 켜기 (API 코드를 바꿨으면 --build로 다시 만든다)
docker compose stop tunnel                # 바깥 연결만 끄기
docker compose logs -f tunnel             # 터널 상태 (토큰은 찍히지 않음)
curl http://127.0.0.1:8001/api/health      # PC 안에서 API 확인
```

- 토큰: `.env`의 `NGROK_AUTHTOKEN` (커밋하지 않음). 도메인은 `NGROK_DOMAIN`(기본값 headset-fretted-pang.ngrok-free.dev).
- 무료 계정은 터널을 하나만 띄울 수 있다 → PC에서 따로 `ngrok`을 실행하지 말 것 (같은 도메인 충돌).
- 개발할 때는 지금처럼 `uvicorn --reload`(8000) + `npm run dev`(5173)를 쓴다. 공개 API(컨테이너, 8001)와 따로 돈다.
- 아직 하지 않은 것 (요청 시): 읽기 전용 DB 계정, 요청 수 제한, 응답 캐시.

---

아래는 처음 세운 계획이에요 (참고용).


작성 2026-10-22. 아직 실행 전이에요. 나중에 클라우드로 옮길 때의 계획은 맨 아래에 짧게 남겨 뒀어요.

## 구성

```
사용자 브라우저
  ├─ https://wherelive-phi.vercel.app          Vercel: web/ 빌드 결과 (정적 화면)
  └─ https://<고정 주소>.ngrok-free.app/api/*  ngrok 터널 ─┐
                                                          │ (내 PC 밖으로는 이 길 하나만 열림)
내 PC (Docker Compose)                                     ▼
  db (Postgres, 기존)  ←── api (FastAPI, 새 컨테이너, 읽기 전용 계정) ←── tunnel (ngrok, 새 컨테이너)
  airflow (기존, 수집·집계 그대로)
```

- **바깥으로는 API 하나만 열어요.** DB(5433)·Airflow(8080)·개발 서버는 열지 않아요. 공유기 포트포워딩도 하지 않아요.
- **터널을 쓰는 이유:** Vercel 화면은 `https`라서 `http`로 된 집 IP 주소는 브라우저가 막아요. 터널은 `https` 주소를 주고, 집 IP도 드러내지 않아요.
- **데이터:** 지금 DB를 그대로 써요. 밤마다 집계가 끝나면 사이트에 바로 반영돼요. 클라우드 복사가 필요 없어요.
- **한계:** PC가 꺼지거나 잠들면 사이트의 지도·퀴즈가 멈춰요. 화면은 Vercel이라 첫 페이지는 떠요.

## 터널 선택: ngrok 무료 고정 도메인 (추천)

| | ngrok (무료 계정) | Cloudflare 빠른 터널 |
|---|---|---|
| 가입 | 필요 (authtoken) | 필요 없음 |
| 주소 | **고정** 도메인 1개 무료 | 켤 때마다 바뀜 (`*.trycloudflare.com`) → 그때마다 Vercel 설정을 바꾸고 다시 배포해야 함 |
| 주의 | 무료는 브라우저 요청에 경고 페이지를 끼움 → 화면이 `ngrok-skip-browser-warning` 헤더를 붙여 부르면 됨 | 테스트용이라 안정성 보장 없음 |

주소가 바뀌지 않아야 Vercel을 한 번만 설정하면 돼서 ngrok을 추천해요. 나중에 도메인이 생기면 Cloudflare 이름 있는 터널로 바꿀 수 있어요.

## 할 일

### A. 코드 변경 (제가 해요)
1. **`api/Dockerfile` + `api/requirements.txt`:**
   - python:3.11-slim에 fastapi·uvicorn·psycopg2-binary(버전 고정)를 넣어요.
   - 개발용 `--reload` 없이 `uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2`로 실행해요.
2. **`api/main.py`:**
   - **DB 접속:** 수집 코드(`molit_rent.py`) 대신 `api/db.py`로 붙어요. API 컨테이너에는 `api/` 폴더만 들어가요.
   - **CORS:** `ALLOWED_ORIGINS` 환경변수 (`https://wherelive-phi.vercel.app`, 미리보기 `https://wherelive-*.vercel.app`, 로컬 `http://localhost:5173`).
   - **캐시:** 하루 한 번 바뀌는 응답(`/api/regions`·`questions`·`metrics`·`sources`)에 `Cache-Control: max-age=3600`을 붙여요.
   - **요청 제한:** 간단한 IP당 분당 요청 수 제한(예: 분당 120회)과 `/api/recommend` 본문 크기 제한을 둬요. 내 PC를 지키려는 거예요.
3. **DB 읽기 전용 계정 `eodi_api`:** `sql/init/12_api_role.sql` + 마이그레이션을 추가해요.
   - `mart`·`meta` 스키마는 SELECT만 돼요. `raw`는 안 보여요.
   - 비밀번호는 `.env`의 `API_DB_PASSWORD`에 둬요.
4. **`docker-compose.yml`:**
   - **api 서비스:** DB와 같은 네트워크. 포트는 `127.0.0.1:8001`로만 열어서 PC 안에서만 확인할 수 있게 해요.
   - **tunnel 서비스:** `ngrok/ngrok` 이미지로 `http api:8000 --url=${NGROK_DOMAIN}`을 실행해요. 토큰은 `.env`의 `NGROK_AUTHTOKEN`에 둬요.
   - 둘 다 `restart: unless-stopped`로 두고, `profiles: [public]`로 묶어요. `docker compose --profile public up -d`로 켜고 끄기 쉽게 하려는 거예요.
5. **화면 `web/src/api.js`:**
   - `apiUrl()`이 `VITE_API_BASE`를 앞에 붙이고, ngrok 주소면 `ngrok-skip-browser-warning` 헤더를 같이 보내요.
   - 고칠 곳: `App.jsx`, `Home.jsx`, `DetailPanel.jsx`. 비어 있으면 지금처럼 `/api`라서 로컬 개발은 그대로예요.
6. **서버가 꺼져 있을 때 안내:** API에 닿지 않으면 "지금 서버가 쉬는 중이에요. 잠시 뒤 다시 시도해 주세요"를 보여 줘요 (지금은 빨간 오류 문구예요).
7. **문서:** HANDOFF.md에 켜고 끄는 명령과 주소를 적어요.

### B. 사용자가 할 일 (계정이라 제가 대신할 수 없어요)
1. **ngrok:** ngrok.com에 가입해 대시보드에서 두 가지를 받아요.
   - **Your Authtoken:** `.env`의 `NGROK_AUTHTOKEN`에 넣어요.
   - **Domains → 무료 고정 도메인 1개:** `.env`의 `NGROK_DOMAIN`에 넣어요.
2. **Vercel:** 설정을 바꾸고 Redeploy 해요.
   - Settings → Build and Deployment: Root Directory `web`, Framework Vite.
   - Settings → Environment Variables: `VITE_API_BASE=https://<NGROK_DOMAIN>`.
3. **이 PC 설정:**
   - 전원 옵션에서 '절전 모드 안 함'으로 바꿔요.
   - Docker Desktop을 '로그인 시 자동 시작'으로 둬요.

### C. 공개 전 확인
- 이용조건 미확인 원천 확인: `molit_rent`, `mois_public_fee`, `mois_dining`, `kepco_house_power`, `kapt_fee`.
- `opinet_price`: 출처 명시 필수, 수익 목적이면 사전 협의, 링크하면 석유공사에 통지.

## 확인 방법
1. `docker compose --profile public up -d` 뒤에 확인해요.
   - `curl http://127.0.0.1:8001/api/health`가 256곳을 돌려줘야 해요.
   - 읽기 전용 계정으로 `INSERT`가 거부되는지 확인해요.
2. **외부 주소:** 휴대폰 LTE(집 와이파이 끄고)에서 `https://<NGROK_DOMAIN>/api/health`가 열려야 해요.
3. **Vercel:**
   - `https://wherelive-phi.vercel.app/`에서 첫 화면 → 퀴즈 → 카드 3장 → 지도 → 지역 상세까지 확인해요.
   - `/HANDOFF.md`가 404여야 해요.
   - 브라우저 콘솔에 CORS·경고 페이지 오류가 없어야 해요.
4. **끄고 켜기:** `docker compose stop tunnel` 뒤 사이트가 '서버가 쉬는 중' 안내를 보여 줘야 해요. 다시 켜면 같은 주소로 돌아와야 해요.
5. **다음 날:** 23:30 집계 뒤 `/api/health`의 `built_at`이 바뀌어 있어야 해요.

## 나중에: 클라우드로 옮길 때
PC를 계속 켜 두기 어렵다면 이렇게 옮겨요.
- API는 Render 무료 웹 서비스(15분 쉬면 잠들고, 깨는 데 약 1분)로 옮겨요.
- DB는 Neon 무료(저장 0.5GB)로 옮겨요. 원자료(`raw`, 6GB)는 PC에 두고, API가 읽는 `mart`(41MB)와 `meta`만 밤마다 복사해요.
- 위 A단계의 Dockerfile·읽기 전용 계정·`VITE_API_BASE`는 그대로 다시 쓸 수 있어요.
