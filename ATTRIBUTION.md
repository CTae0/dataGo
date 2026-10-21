# 데이터 출처 표시 (저작자 표시)

이 서비스가 쓰는 공공데이터 중 **저작자 표시가 필요한 데이터**가 있습니다.
프론트엔드에서 해당 데이터를 보여 주는 화면(지도, 지역 상세, 비교표, 추천 결과)과 사이트 푸터에 **반드시 출처를 표시**해야 합니다.

- 화면용 문구의 기준은 DB `meta.data_source` 테이블입니다 (`sql/init/03_std_fees_and_sources.sql`).
  문구를 고칠 때는 SQL과 이 문서를 같이 고치세요.
- 프론트엔드 규칙
  1. 데이터를 화면에 그릴 때 그 데이터의 `source_id`를 함께 넘기고, 화면 하단(또는 차트·지도 아래)에 `attribution_text`를 보여 준다.
  2. 사이트 푸터 또는 '데이터 출처' 페이지에 `attribution_required = true`인 출처를 모두 나열하고 `portal_url`로 링크한다.
  3. 값을 가공했다면(평균, 20㎥ 환산 등) 문구 뒤에 "(가공)"처럼 가공 사실을 밝힌다.

## 출처 목록

| source_id | 데이터 | 제공 | 이용조건 | 화면 문구 |
|---|---|---|---|---|
| `std_water_sewage_fee` | [전국상하수도요금표준데이터](https://www.data.go.kr/data/15139217/standard.do) | 각 지방자치단체 (소관: 기후에너지환경부) | **저작자표시** | 출처: 공공데이터포털(data.go.kr) 「전국상하수도요금표준데이터」, 각 지방자치단체 제공 |
| `std_trash_bag_price` | [전국종량제봉투가격표준데이터](https://www.data.go.kr/data/15025538/standard.do) | 각 지방자치단체 (소관: 기후에너지환경부) | **저작자표시** | 출처: 공공데이터포털(data.go.kr) 「전국종량제봉투가격표준데이터」, 각 지방자치단체 제공 |
| `kca_price` | [한국소비자원_생필품 가격 정보_GW](https://www.data.go.kr/data/15158701/openapi.do) | 한국소비자원 (참가격) | **공공누리 제1유형(출처표시)** | 출처: 한국소비자원 참가격(www.price.go.kr) / 공공데이터포털(data.go.kr) 「한국소비자원_생필품 가격 정보」 |
| `mois_public_fee` | [행정안전부_지방공공요금 현황](https://www.data.go.kr/data/3045228/fileData.do) | 행정안전부 | 미확인 (확인 전까지 표시) | 출처: 공공데이터포털(data.go.kr) 「행정안전부_지방공공요금 현황」 |
| `molit_rent` | [국토교통부 전월세 실거래가 (4종)](https://www.data.go.kr/data/15126474/openapi.do) | 국토교통부 | 미확인 (확인 전까지 표시) | 출처: 국토교통부 실거래가 공개시스템 / 공공데이터포털(data.go.kr) |
| `mois_dining` | [행정안전부 지방물가정보 — 개인서비스(외식비) 가격 현황](https://www.mois.go.kr/frt/sub/a02/lpid020101/screen.do) | 행정안전부 (원자료: 국가데이터처 소비자물가조사) | 미확인 (확인 전까지 표시) | 출처: 행정안전부 지방물가정보 「개인서비스(외식비) 가격 현황」 (원자료: 국가데이터처) |
| `good_price` | [행정안전부_착한가격업소 현황](https://www.data.go.kr/data/3045247/fileData.do) | 행정안전부 | 이용허락범위 제한 없음 (표시 의무 없음, 표시 권장) | 출처: 공공데이터포털(data.go.kr) 「행정안전부_착한가격업소 현황」 |

- 두 표준데이터의 이용조건(저작자표시)은 2026-10-21 활용신청 때 확인한 내용입니다. 데이터셋 페이지에는 따로 표기돼 있지 않습니다.
- 나머지 두 출처도 공개 전에 포털에서 이용조건을 확인하고 위 표와 `meta.data_source.license`를 채우세요.
- `mois_dining`은 행안부 누리집(하모니) 자료라 공공누리 유형이 따로 표기돼 있지 않습니다. 공개 전에 행안부 저작권정책을 확인하세요.
  값 일부는 같은 자료를 옮긴 한국소비자원 참가격 화면으로 바로잡았습니다(`price_src = 'tprice'`). 화면 문구는 행안부 출처 하나로 둡니다.
- 외식비 원천 조사와 선택 이유: `docs/research/dining_sources.md`

## 확인용 SQL

```sql
SELECT source_id, attribution_text, portal_url
FROM meta.data_source
WHERE attribution_required
ORDER BY source_id;
```
