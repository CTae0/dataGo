"""
공공데이터포털(data.go.kr) '주기성 파일데이터' 자동 수집기

사용법:
    python datago_periodic.py 3045228 --out ./data/public_fee
    python datago_periodic.py 3045228 --out ./data/public_fee --latest-only

동작:
  1. 데이터셋 상세 페이지에서 현재 파일의 키(uddi)를 찾는다.
  2. '주기성 과거 데이터' 목록을 불러와 과거 파일들의 키를 모은다.
  3. 포털 화면의 다운로드 버튼과 같은 순서(selectFileDataDownload → check-limit → fileDownload)로 받는다.
  4. 이미 받은 파일은 건너뛴다(멱등). manifest.csv에 기록을 남긴다.

주의:
  - 포털 내부 경로를 쓰는 방식이라 포털이 개편되면 깨질 수 있다.
  - 다운로드 제한에 걸리면(needCaptcha=true) 중단한다. 요청 사이에 간격을 둔다.
"""
import argparse
import csv
import re
import sys
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://www.data.go.kr"
HEADERS = {"User-Agent": "Mozilla/5.0 (eodi-salkka data pipeline)"}


def make_session():
    """연결이 끊기거나 5xx가 나면 간격을 늘려 가며 다시 시도하는 세션"""
    s = requests.Session()
    s.headers.update(HEADERS)
    retry = Retry(total=6, connect=6, read=6, backoff_factor=2,
                  status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=["GET", "POST"])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def get_current_key(s, pk):
    html = s.get(f"{BASE}/data/{pk}/fileData.do", timeout=30).text
    m = re.search(r"fn_fileDataDown\('(\d+)',\s*'([^']+)'", html)
    if not m:
        raise RuntimeError("현재 파일 키를 찾지 못했습니다.")
    title = re.search(r"<title>(.*?)\s*\|", html)
    return m.group(2), (title.group(1).strip() if title else "")


def get_history(s, pk, detail_pk):
    html = s.post(f"{BASE}/tcs/dss/selectHistAndCsvData.do",
                  data={"publicDataPk": pk, "publicDataDetailPk": detail_pk}, timeout=30).text
    items = re.findall(
        r'data-public-pk="([^"]+)"\s+data-public-detail-sn="(\d+)">\s*(.*?)\s*</a>\s*</td>\s*<td>([\d-]+)</td>',
        html, re.S)
    return [{"detail_pk": k, "sn": sn, "name": re.sub(r"\s+", " ", n), "reg_date": d}
            for k, sn, n, d in items]


class LimitReached(RuntimeError):
    """보안문자 요구 — 이후 파일도 모두 막히므로 전체를 멈춰야 한다"""


def _file_info(s, pk, detail_pk, sn):
    r = s.post(f"{BASE}/tcs/dss/selectFileDataDownload.do",
               data={"publicDataPk": pk, "publicDataDetailPk": detail_pk, "fileDetailSn": sn,
                     "publicDataTyCode": "PR0051", "atchFileId": ""}, timeout=30)
    j = r.json()
    if not j.get("status"):
        raise RuntimeError(f"다운로드 정보 조회 실패: {j.get('error')}")
    return j.get("atchFileId"), j.get("fileDetailSn")


def _fetch(s, fid, fsn):
    lim_r = s.post(f"{BASE}/cmm/cmm/check-limit.json", data={"atchFileId": fid, "fileDetailSn": fsn}, timeout=30)
    lim = lim_r.json() if "json" in lim_r.headers.get("content-type", "") else {}
    if lim.get("needCaptcha"):
        raise LimitReached("다운로드 제한(보안문자 요구)에 걸렸습니다. 시간을 두고 다시 실행하세요.")
    f = s.get(f"{BASE}/cmm/cmm/fileDownload.do",
              params={"atchFileId": fid, "fileDetailSn": fsn, "dataNm": "file"}, timeout=60)
    f.raise_for_status()
    return f


def download(s, pk, detail_pk, sn, dest_stem):
    """받은 파일 경로를 돌려준다. 확장자는 포털이 알려 준 파일명(csv/xlsx/json 등)을 따른다.

    과거 목록의 sn은 '이력 번호'라서 파일 번호와 다르다. 파일 번호는 대부분 1이고,
    sn으로 요청하면 첨부파일이 없거나(None) 0바이트가 오는 경우가 있다 → 1을 먼저 시도.
    """
    for try_sn in dict.fromkeys(["1", sn]):
        fid, fsn = _file_info(s, pk, detail_pk, try_sn)
        if not fid:
            continue
        f = _fetch(s, fid, fsn)
        if not f.content:
            continue
        m = re.search(r'filename="?[^";]*\.(\w+)"?', f.headers.get("content-disposition", ""))
        ext = m.group(1).lower() if m else "bin"
        if ext == "csv" and f.content[:2] == b"PK":   # 이름만 csv인 엑셀
            ext = "xlsx"
        dest = dest_stem.with_suffix("." + ext)
        dest.write_bytes(f.content)
        return dest
    raise RuntimeError("포털에서 파일을 받지 못했습니다(첨부파일 없음 또는 빈 응답).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pk", help="데이터셋 번호 (URL의 /data/<번호>/fileData.do)")
    ap.add_argument("--out", default="./data")
    ap.add_argument("--latest-only", action="store_true")
    ap.add_argument("--sleep", type=float, default=1.5)
    a = ap.parse_args()

    out = Path(a.out); (out / "raw").mkdir(parents=True, exist_ok=True)
    s = make_session()

    cur_key, title = get_current_key(s, a.pk)
    targets = [{"detail_pk": cur_key, "sn": "1", "name": title or "current", "reg_date": "current"}]
    if not a.latest_only:
        targets += [h for h in get_history(s, a.pk, cur_key) if h["detail_pk"] != cur_key]

    manifest = out / "manifest.csv"
    fields = ["detail_pk", "sn", "name", "reg_date", "file"]
    rows = {}
    if manifest.exists():
        with manifest.open(encoding="utf-8") as fh:
            rows = {r["detail_pk"]: r for r in csv.DictReader(fh)}

    def is_done(key):
        # 기록이 있어도 파일이 없거나 0바이트면 다시 받는다
        r = rows.get(key)
        return bool(r) and (out / "raw" / r["file"]).is_file() and (out / "raw" / r["file"]).stat().st_size > 0

    def save_manifest():
        tmp = manifest.with_suffix(".tmp")
        with tmp.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows({k: r.get(k, "") for k in fields} for r in rows.values())
        tmp.replace(manifest)

    new = failed = 0
    for t in targets:
        # 현재 파일은 매달 내용이 바뀌므로 등록일과 상관없이 다시 받는다
        if t["reg_date"] != "current" and is_done(t["detail_pk"]):
            continue
        stem = out / "raw" / re.sub(r"[^\w가-힣.-]+", "_", t["detail_pk"])
        try:
            dest = download(s, a.pk, t["detail_pk"], t["sn"], stem)
        except LimitReached as e:
            print(f"[중단] {t['name']}: {e}", file=sys.stderr)
            break
        except Exception as e:
            print(f"[건너뜀] {t['reg_date']}  {t['name']}: {e}", file=sys.stderr)
            failed += 1
            continue
        old = rows.get(t["detail_pk"])
        if old and old["file"] != dest.name:
            (out / "raw" / old["file"]).unlink(missing_ok=True)   # 확장자가 바뀐 옛 파일 정리
        rows[t["detail_pk"]] = {**t, "file": dest.name}
        save_manifest()
        new += 1
        print(f"[받음] {t['reg_date']}  {t['name']}  → {dest.name}")
        time.sleep(a.sleep)
    print(f"완료: {new}개 파일 → {out / 'raw'}" + (f" (실패 {failed}개, 다시 실행하면 재시도)" if failed else ""))


if __name__ == "__main__":
    main()
