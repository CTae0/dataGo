"""
추천 카드 문구 (지역 특징 + 예상 생활비로 만든다. 순수 함수)

카드 1장 = 그림 유형(archetype) + 별명 + 설명 2~3문장 + 생활비 수준 배지.
말투: 재미있게, 하지만 지역을 깎아내리지 않는다 (인구 감소·낙후 같은 표현 금지).
"""

# 그림 유형 → (별명, 한 줄 소개). 그림은 web/src/scenes/의 같은 이름
ARCHETYPE = {
    "metropolis":       ("불 꺼지지 않는 도시", "지하철·병원·맛집이 다 걸어서 닿는 대도시 생활"),
    "commuter_town":    ("출퇴근 가능 생활권", "큰 도시 일자리는 가깝고, 집값은 한숨 덜 나오는 곳"),
    "small_city":       ("적당히 편한 중소도시", "있을 건 다 있고 붐비지는 않는 딱 좋은 크기"),
    "harbor_city":      ("갈매기 알람 항구도시", "도시 편의시설에 바다 산책이 덤으로 붙어 오는 곳"),
    "seaside_village":  ("파도 소리 ASMR 바닷가 마을", "창문만 열면 바다, 퇴근길이 곧 바닷가 드라이브"),
    "mountain_village": ("공기 맛집 산골", "산 능선이 병풍처럼 둘러싼 조용한 동네"),
    "farmland":         ("황금 들녘 시골", "넓은 들판과 느긋한 하루, 텃밭 로망이 이뤄지는 곳"),
    "island":           ("섬 라이프", "배 시간표가 곧 생활 리듬, 바다 한가운데 내 집"),
}

# 생활비 수준: 전국 시군구 중 몇 % 위치인지 (낮을수록 쌈)
LEVELS = [  # (상한 %, 이름, 설명)
    (20, "통장 수비 만렙", "전국에서 가장 싼 편"),
    (40, "알뜰 살림꾼", "전국 평균보다 싼 편"),
    (60, "딱 평균", "전국 중간쯤"),
    (80, "조금 플렉스", "전국 평균보다 비싼 편"),
    (101, "지갑 주의보", "전국에서 비싼 편"),
]


def josa(word, with_final, without_final):
    """받침 있으면 with_final(예: '은'), 없으면 without_final(예: '는')"""
    ch = word[-1] if word else ""
    if "가" <= ch <= "힣":
        return with_final if (ord(ch) - 0xAC00) % 28 else without_final
    return with_final


def level(pct):
    for limit, name, desc in LEVELS:
        if pct <= limit:
            return {"name": name, "desc": desc, "pct": pct}
    return {"name": LEVELS[-1][1], "desc": LEVELS[-1][2], "pct": pct}


def _won_short(v):
    return f"{v / 10_000:,.0f}만 원" if v >= 10_000 else f"{v:,.0f}원"


def card(result, features):
    """result: recommend() 결과 1개, features: mart.region_features 행 → 카드 내용"""
    f = features or {}
    arch = f.get("archetype") or "small_city"
    nick, intro = ARCHETYPE.get(arch, ARCHETYPE["small_city"])
    if arch == "commuter_town" and not f.get("is_capital"):
        nick = "광역시 옆 생활권"
    facts = []
    if f.get("is_capital"):
        facts.append("수도권")
    elif f.get("is_metro_area"):
        facts.append("광역시 생활권")
    if f.get("is_coastal"):
        facts.append(f"해안선 {f['coast_km']:.0f}km")
    if f.get("airport_name") and f.get("airport_km") is not None:
        facts.append(f"{f['airport_name']}까지 약 {f['airport_km']:.0f}km")
    # 생활편의 시설 (sql/mart/85_amenities.sql, 소수는 주소가 시 단위인 시설을 인구 비율로 나눈 값 → 반올림)
    for key, label in (("elem", "초등학교"), ("library", "도서관"), ("museum", "박물관·미술관")):
        if f.get(key):
            facts.append(f"{label} {round(f[key]):,}곳")
    items = result["items"]
    biggest = max(items, key=lambda k: items[k]["value"])
    lv = level(result["national_pct"])
    name = result["sigungu"]
    rank = result["national_rank"]
    where = "전국 시군구 중 가장 저렴해요" if rank == 1 else f"전국 시군구 중 {rank}번째로 저렴해요"
    text = (f"{result['sido']} {name}{josa(name, '은', '는')} {intro}. "
            f"예상 생활비는 월 약 {_won_short(result['total'])}으로 {where}. "
            f"가장 큰 몫은 {items[biggest]['label']}(월 {_won_short(items[biggest]['value'])})입니다.")
    energy = sum(v["value"] for v in items.values() if v.get("group") == "energy")
    if energy:
        with_mgmt = items.get("mgmt", {}).get("value", 0) > 0
        what = "전기·가스·물" + ("·관리비" if with_mgmt else "")
        text += f" {what}{josa(what, '은', '는')} 합쳐서 월 약 {_won_short(energy)}이에요."
    edu_st, cul_st = f.get("edu_stars"), f.get("culture_stars")
    if cul_st == 4:
        text += " 도서관·박물관·공원이 넉넉해서 주말이 심심할 틈이 없어요."
    elif edu_st == 4:
        text += " 학교·유치원·학원이 넉넉한 동네예요."
    groups = {}
    for v in items.values():
        if v.get("group"):
            groups[v["group"]] = groups.get(v["group"], 0) + v["value"]
    return {"archetype": arch, "nickname": nick, "intro": intro, "facts": facts, "text": text, "level": lv,
            "groups": groups, "stars": {"edu": edu_st, "culture": cul_st}}
