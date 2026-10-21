"""
어디 살까? 조회 API — mart.* 를 읽기만 한다.

실행 (프로젝트 루트에서):
    python -m uvicorn api.main:app --port 8000 --reload

엔드포인트
    GET /api/metrics            지도에 칠할 수 있는 지표 목록 (단위, 낮을수록 좋은지)
    GET /api/regions            시군구(leaf) 256곳 요약 — 지도 색칠용
    GET /api/regions/{code}     한 시군구 상세 (전월세·전기 추이, 공공요금 후보, 장바구니 분류, 외식비)
    GET /api/sources            출처 표시 문구 (meta.data_source) — 화면 하단·푸터에 반드시 표시

모든 값에는 *_gran(정밀도: exact/si/legacy/sido_part/sido)이 붙는다.
'sido'·'sido_part'는 시군구 값이 없어 시도 평균으로 채운 것 → 화면에서 구분해 보여 줄 것.
"""
import os
from contextlib import contextmanager

import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api import db as common   # load_env / connect (API 전용, api/db.py)
from api import cost_model, describe

common.load_env()
app = FastAPI(title="어디 살까? API", version="0.1.0")

# CORS: 다른 주소의 화면(Vercel)이 이 API를 부를 수 있게 허용할 출처.
#   ALLOWED_ORIGINS(쉼표로 구분)로 바꿀 수 있다. 이 팀의 Vercel 미리보기 주소(wherelive-*-ctae0s-projects.vercel.app)도 허용.
#   ngrok 경고 페이지를 건너뛰는 헤더(ngrok-skip-browser-warning) 때문에 브라우저가 사전 요청을 보내므로 그 헤더를 허용한다.
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get(
    "ALLOWED_ORIGINS", "https://wherelive-phi.vercel.app,http://localhost:5173,http://localhost:4173").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://wherelive-[a-z0-9-]+-ctae0s-projects\.vercel\.app",
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "ngrok-skip-browser-warning"],
    max_age=3600,
)

# 지표 목록. field는 /api/regions 응답의 키, gran은 정밀도 키, better는 'low'(낮을수록 좋음)
# sources: 이 지표를 칠할 때 화면에 표시할 출처 (시도 평균 대체에 쓰는 원천 포함)
METRICS = [
    {"id": "cost_s", "label": "1인 가구 월 주거비", "detail": "≤40㎡, 전·월세 환산 월세 중위값(최근 12개월)",
     "unit": "만원/월", "field": "cost_s", "gran": None, "better": "low", "group": "주거비", "source": "molit_rent", "sources": ["molit_rent"]},
    {"id": "cost_m", "label": "2인 가구 월 주거비", "detail": "40~60㎡, 환산 월세 중위값(최근 12개월)",
     "unit": "만원/월", "field": "cost_m", "gran": None, "better": "low", "group": "주거비", "source": "molit_rent", "sources": ["molit_rent"]},
    {"id": "cost_l", "label": "가족 가구 월 주거비", "detail": "60~85㎡, 환산 월세 중위값(최근 12개월)",
     "unit": "만원/월", "field": "cost_l", "gran": None, "better": "low", "group": "주거비", "source": "molit_rent", "sources": ["molit_rent"]},
    {"id": "jeonse_s", "label": "1인 가구 전세 보증금", "detail": "≤40㎡, 전세 보증금 중위값(최근 12개월)",
     "unit": "만원", "field": "jeonse_s", "gran": None, "better": "low", "group": "주거비", "source": "molit_rent", "sources": ["molit_rent"]},
    {"id": "jeonse_l", "label": "가족 가구 전세 보증금", "detail": "60~85㎡, 전세 보증금 중위값(최근 12개월)",
     "unit": "만원", "field": "jeonse_l", "gran": None, "better": "low", "group": "주거비", "source": "molit_rent", "sources": ["molit_rent"]},
    {"id": "water_sewer", "label": "상하수도 요금", "detail": "가정용 20㎥ 사용 기준 월 요금(기본요금 제외)",
     "unit": "원/월", "field": "water_sewer", "gran": "water_sewer_gran", "better": "low", "group": "공공요금",
     "source": "std_water_sewage_fee",
     "sources": ["std_water_sewage_fee", "mois_public_fee"]},
    {"id": "trash_20l", "label": "종량제봉투 20ℓ", "detail": "가정용 생활쓰레기 규격봉투",
     "unit": "원", "field": "trash_20l", "gran": "trash_gran", "better": "low", "group": "공공요금",
     "source": "std_trash_bag_price",
     "sources": ["std_trash_bag_price", "mois_public_fee"]},
    {"id": "grocery_index", "label": "장바구니 물가", "detail": "대형마트·SSM 상품 가격 지수 (전국 중위 = 100)",
     "unit": "지수", "field": "grocery_index", "gran": "grocery_gran", "better": "low", "group": "장바구니",
     "source": "kca_price", "sources": ["kca_price"]},
    {"id": "meal_index", "label": "외식비", "detail": "일상 한 끼 5종(냉면·비빔밥·김치찌개 백반·짜장면·칼국수) 평균, 16개 시도 평균 = 100 (시도 단위)",
     "unit": "지수", "field": "meal_index", "gran": "dining_gran", "better": "low", "group": "외식비",
     "source": "mois_dining", "sources": ["mois_dining"]},
    {"id": "power_bill", "label": "가구 평균 전기요금", "detail": "주택용 전기 쓰는 가구의 월평균 청구액 (최근 12개월, 한전)",
     "unit": "원/월", "field": "power_bill", "gran": "power_gran", "better": "low", "group": "에너지·관리비",
     "source": "kepco_house_power", "sources": ["kepco_house_power"]},
    {"id": "mgmt_per_m2", "label": "아파트 ㎡당 관리비", "detail": "공용관리비+장기수선충당금 ÷ 관리비부과면적, 의무단지 중위값 (최근 12개월, K-apt)",
     "unit": "원/㎡·월", "field": "mgmt_per_m2", "gran": "mgmt_gran", "better": "low", "group": "에너지·관리비",
     "source": "kapt_fee", "sources": ["kapt_fee"]},
]
GRAN_RANK = {"exact": 0, "si": 1, "legacy": 2, "sido_part": 3, "sido": 4}


@contextmanager
def cursor():
    conn = common.connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
    finally:
        conn.close()


def table_exists(cur, name):
    cur.execute("SELECT to_regclass(%s) IS NOT NULL AS ok", (name,))
    return cur.fetchone()["ok"]


def num(v):
    return float(v) if v is not None else None


def worse(a, b):
    """두 정밀도 중 덜 정밀한 쪽"""
    if a is None or b is None:
        return a or b
    return a if GRAN_RANK.get(a, 9) >= GRAN_RANK.get(b, 9) else b


FEATURE_COLS = ("sigungu_type", "coast_km", "is_coastal", "is_island", "is_capital", "is_metro_area",
                "is_metro_core", "airport_name", "airport_km", "archetype")


def region_rows(cur, code=None):
    dining = table_exists(cur, "mart.dining_region")
    features = table_exists(cur, "mart.region_features")   # 바다·공항·광역시권 등 (sql/mart/50_region_features.sql)
    cur.execute(f"""
        SELECT s.*, {"d.meal_index, d.meal_avg, d.dining_gran, d.dining_ym" if dining
                     else "NULL::numeric AS meal_index, NULL::numeric AS meal_avg, NULL::text AS dining_gran, NULL AS dining_ym"}
               {", " + ", ".join("f." + c for c in FEATURE_COLS) if features else ""}
        FROM mart.region_summary s
        {"LEFT JOIN mart.dining_region d USING (region_code)" if dining else ""}
        {"LEFT JOIN mart.region_features f USING (region_code)" if features else ""}
        {"WHERE s.region_code = %s" if code else ""}
        ORDER BY s.region_code""", (code,) if code else None)
    out = []
    for r in cur.fetchall():
        r = {k: (num(v) if not isinstance(v, bool) and (isinstance(v, (int, float)) or type(v).__name__ == "Decimal") else v)
             for k, v in r.items()}
        ws = (r["water_20m3"] or 0) + (r["sewer_20m3"] or 0) if r["water_20m3"] or r["sewer_20m3"] else None
        r["water_sewer"] = ws
        r["water_sewer_gran"] = worse(r["water_gran"], r["sewer_gran"])
        if dining and r.get("dining_gran") is None and r.get("meal_index") is not None:
            r["dining_gran"] = "sido"
        r["built_at"] = r["built_at"].isoformat() if r.get("built_at") else None
        out.append(r)
    return out


@app.get("/api/health")
def health():
    with cursor() as cur:
        cur.execute("SELECT count(*) AS n, max(built_at) AS built_at FROM mart.region_summary")
        r = cur.fetchone()
    return {"ok": True, "regions": r["n"], "built_at": r["built_at"]}


@app.get("/api/metrics")
def metrics():
    with cursor() as cur:
        dining = table_exists(cur, "mart.dining_region")
    return [m for m in METRICS if dining or m["id"] != "meal_index"]


@app.get("/api/regions")
def regions():
    with cursor() as cur:
        return region_rows(cur)


@app.get("/api/regions/{code}")
def region_detail(code: str):
    with cursor() as cur:
        rows = region_rows(cur, code)
        if not rows:
            raise HTTPException(404, f"시군구 코드 {code}가 없습니다")
        # 전월세 추이: 면적대별 월 환산 주거비 (주택유형 합산은 거래 수 가중 평균)
        cur.execute("""
            SELECT deal_ym, size_band, sum(deals) AS deals,
                   sum(monthly_cost_median * deals) / nullif(sum(deals), 0) AS monthly_cost,
                   sum(deposit_median * deals) FILTER (WHERE rent_kind = 'jeonse')
                     / nullif(sum(deals) FILTER (WHERE rent_kind = 'jeonse'), 0) AS jeonse_deposit
            FROM mart.rent_monthly WHERE region_code = %s AND size_band IN ('s', 'm', 'l')
            GROUP BY 1, 2 ORDER BY 1, 2""", (code,))
        trend = [{k: num(v) if k not in ("deal_ym", "size_band") else v for k, v in r.items()} for r in cur.fetchall()]
        cur.execute("""SELECT item, value, granularity, source_id, ref_date FROM mart.utility_candidates
                       WHERE region_code = %s ORDER BY item, granularity""", (code,))
        utility = [{**r, "value": num(r["value"]), "ref_date": r["ref_date"].isoformat() if r["ref_date"] else None}
                   for r in cur.fetchall()]
        cur.execute("""SELECT category, price_index, granularity, stores_in_region, stores_in_sido, store_types
                       FROM mart.grocery_region WHERE region_code = %s ORDER BY category""", (code,))
        grocery = [{**r, "price_index": num(r["price_index"])} for r in cur.fetchall()]
        dining = None
        if table_exists(cur, "mart.dining_region"):
            cur.execute("SELECT * FROM mart.dining_region WHERE region_code = %s", (code,))
            d = cur.fetchone()
            if d:
                dining = {k: (num(v) if type(v).__name__ == "Decimal" else v) for k, v in d.items()
                          if k not in ("built_at",)}
                for k, v in list(dining.items()):
                    if hasattr(v, "isoformat"):
                        dining[k] = v.isoformat()
        power_trend = []
        if table_exists(cur, "mart.power_monthly"):   # 한전 가구 평균 사용량·청구액, 최근 24개월
            cur.execute("""SELECT ym, power_kwh, bill FROM mart.power_monthly WHERE region_code = %s
                           ORDER BY ym DESC LIMIT 24""", (code,))
            power_trend = [{"ym": r["ym"], "power_kwh": num(r["power_kwh"]), "bill": num(r["bill"])}
                           for r in reversed(cur.fetchall())]
    return {"summary": rows[0], "rent_trend": trend, "power_trend": power_trend, "utility": utility,
            "grocery": grocery, "dining": dining}


@app.get("/api/questions")
def questions():
    """질문지 정의 (문구·작은 글씨 기준·기본값). 문구는 api/cost_model.py의 QUESTIONS에서 고친다."""
    return {"questions": cost_model.QUESTIONS, "defaults": cost_model.DEFAULTS,
            "items": [{"id": k, "label": cost_model.ITEM_LABEL[k], "source": cost_model.ITEM_SOURCE[k],
                       "group": cost_model.ITEM_GROUP[k]} for k in cost_model.ITEMS],
            "groups": cost_model.GROUPS}


@app.post("/api/recommend")
def recommend(answers: dict):
    """답변 → 조건에 맞는 시군구 전체를 예상 월 생활비 오름차순으로 (항목별 금액·정밀도·출처, 계산 가정 포함)"""
    with cursor() as cur:
        rows = region_rows(cur)
    try:
        results, normalized, assumptions = cost_model.recommend(rows, answers)
    except ValueError as e:
        raise HTTPException(422, str(e))
    by_code = {r["region_code"]: r for r in rows}
    for x in results[:3]:   # 카드 3장: 그림 유형·별명·설명·생활비 수준
        x["card"] = describe.card(x, by_code.get(x["region_code"]))
    return {"answers": normalized, "count": len(results), "results": results, "assumptions": assumptions}


@app.get("/api/sources")
def sources():
    with cursor() as cur:
        cur.execute("""SELECT source_id, title, provider, portal_url, license, attribution_required, attribution_text
                       FROM meta.data_source ORDER BY source_id""")
        return cur.fetchall()
