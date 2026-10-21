"""
K-apt(공동주택관리정보시스템) 자료실 일괄 파일 수집·적재  → raw.kapt_complex, raw.kapt_fee

  원천: https://www.k-apt.go.kr › 소통마당 › 자료실 (국토교통부, 운영 한국부동산원). 주 1회 게시.
    - 기본정보(scode 01): 관리비공개의무단지 목록 (단지코드, 주소, 법정동코드 …)
    - 관리비정보(scode 03): 단지 × 월 관리비 항목. 매주 「관리비정보(YYYY.MM.DD.)」 글을 새로 올린다
      (연도별 글 「관리비정보(YYYY년)」도 있다)
    - 면적정보(scode 04): 단지 관리비부과면적 등
  [출처 표시] meta.data_source 'kapt_fee'
  단지별 API(data.go.kr 15057937·15059469)는 단지 × 월 × 항목 호출이라 전국 수집에 쓰지 않는다.

  내려받기는 자료실 화면과 같은 경로를 쓴다 (포털이 바뀌면 깨질 수 있다):
    목록  POST /web/board/webReference/boardListAjax.do   (scode, boardType=03, _csrf)
    글    POST /web/board/webReference/boardView.do  (글 seq) — 이 세션이 '연 글'이 된다
    첨부  POST /web/board/webReference/fileListData.do?seq=BOARD_FILE  (JSON 본문, X-CSRF-TOKEN)
    파일  GET  /cmm/file/BOARD/fileDownload.do?key=<첨부 순번>&fileName=<이름>  — 방금 연 글의 첨부
    → 글마다 열고 곧바로 받아야 한다.

사용법:
    python kapt_fee.py download                     # 최신 기본정보·면적정보·관리비정보(주 1회 게시) → data/kapt/YYYYMMDD/
    python kapt_fee.py load data/kapt/20261016      # 받은 폴더 적재 (파일 구조는 머리글로 판단)
"""
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

import requests

BASE = "https://www.k-apt.go.kr"
HEADERS = {"User-Agent": "Mozilla/5.0 (eodi-salkka data pipeline)"}
CATEGORIES = {"basic": "01", "fee": "03", "area": "04"}


class Board:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update(HEADERS)
        self.refresh()

    def refresh(self):
        """목록 페이지를 다시 열어 CSRF 토큰을 새로 받는다 (파일을 받고 나면 토큰이 바뀐다)"""
        html = self.s.get(f"{BASE}/web/board/webReference/boardList.do?boardType=03", timeout=60).text
        m = re.search(r'name="_csrf"\s+value="([^"]+)"', html)
        meta = re.search(r'<meta name="_csrf" content="([^"]+)"', html)
        head = re.search(r'<meta name="_csrf_header" content="([^"]+)"', html)
        if not m:
            raise RuntimeError("자료실 페이지에서 CSRF 토큰을 못 찾았습니다.")
        self.token = m.group(1)
        self.meta_token = meta.group(1) if meta else self.token
        self.header = head.group(1) if head else "X-CSRF-TOKEN"

    def posts(self, scode):
        """[(글 seq, 제목)] 최신 글부터"""
        html = self.s.post(f"{BASE}/web/board/webReference/boardListAjax.do", timeout=60,
                           data={"scode": scode, "boardType": "03", "pageNo": "1", "stype": "", "keyword": "",
                                 "_csrf": self.token}).text
        return [(int(seq), re.sub(r"<[^>]+>|\s+", " ", t).strip())
                for seq, t in re.findall(r'goCheck\((\d+),\s*\d+\);">\s*(.*?)</a>', html, re.S)]

    def files(self, seq, scode):
        # 글을 먼저 연 세션에서만 첨부 목록이 온다. 화면의 KAPT.submit과 같이 JSON 본문 + CSRF 헤더.
        self.refresh()
        form = {"boardType": "03", "pageNo": "1", "stype": "", "keyword": "", "seq": str(seq),
                "scode": scode, "boardPwd": "", "_csrf": self.token}
        self.s.post(f"{BASE}/web/board/webReference/boardView.do", data=form, timeout=60).raise_for_status()
        r = self.s.post(f"{BASE}/web/board/webReference/fileListData.do?seq=BOARD_FILE", json=form, timeout=60,
                        headers={self.header: self.meta_token, "X-Requested-With": "XMLHttpRequest",
                                 "Accept": "application/json"})
        r.raise_for_status()
        if "xml" in r.headers.get("content-type", ""):   # Accept를 무시하면 XML로 온다
            return re.findall(r"<data>.*?<seq>(\d+)</seq><fileName>([^<]+)</fileName>", r.text, re.S)
        data = r.json().get("data", [])
        data = data if isinstance(data, list) else [data]
        return [(str(f["seq"]), f["fileName"]) for f in data if f.get("fileName")]

    def download(self, key, name, out):
        url = f"{BASE}/cmm/file/BOARD/fileDownload.do?key={key}&fileName={quote(name)}"
        with self.s.get(url, stream=True, timeout=600, headers={self.header: self.meta_token}) as r:
            r.raise_for_status()
            if "html" in r.headers.get("content-type", ""):
                raise RuntimeError(f"{name}: 파일 대신 HTML이 왔습니다 (세션·토큰 확인).")
            path = out / name
            with open(path, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        return path


def pick(posts, want):
    for seq, title in posts:
        if want(title):
            return seq, title
    return None


def cmd_download(a):
    b = Board()
    chosen = []
    basic = b.posts(CATEGORIES["basic"])
    area = b.posts(CATEGORIES["area"])
    fee = b.posts(CATEGORIES["fee"])
    for scode, got in [(CATEGORIES["basic"], pick(basic, lambda t: "기본정보" in t)),
                       (CATEGORIES["area"], pick(area, lambda t: "면적정보" in t)),
                       (CATEGORIES["fee"], pick(fee, lambda t: re.search(r"관리비정보\(\d{4}\.\d{2}\.\d{2}", t)))]:
        if not got:
            sys.exit(f"자료실 분류 {scode}에서 대상 글을 못 찾았습니다.")
        chosen.append((scode, *got))
    stamp = re.search(r"\((\d{4})\.(\d{2})\.(\d{2})\.?\)", chosen[0][2])
    out = Path(a.out) / ("".join(stamp.groups()) if stamp else "latest")
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for scode, seq, title in chosen:
        for key, name in b.files(seq, scode):
            path = b.download(key, name, out)
            size = path.stat().st_size
            print(f"[받음] {title} → {path} ({size / 1e6:.1f} MB)")
            manifest.append({"scode": scode, "post_seq": seq, "title": title, "file": name, "bytes": size})
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"완료: {len(manifest)}개 파일 → {out}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("download")
    d.add_argument("--out", default="./data/kapt")
    d.add_argument("--list-only", action="store_true")
    l = sub.add_parser("load")
    l.add_argument("folder")
    a = ap.parse_args()
    if a.cmd == "download" and a.list_only:
        b = Board()
        for name, sc in CATEGORIES.items():
            for seq, title in b.posts(sc)[:3]:
                print(name, seq, title, b.files(seq, sc))
        return
    if a.cmd == "download":
        cmd_download(a)
    else:
        cmd_load(a)


def xlsx_rows(path):
    """xlsx 첫 시트를 행(list) 단위로 흘려 읽는다. 표준 라이브러리만 쓴다 (Airflow 이미지에 openpyxl이 없다).
    K-apt 파일은 시트 차원 정보가 틀려 있어(A1만 표시) 셀 참조로 칸 위치를 정한다."""
    import zipfile
    import xml.etree.ElementTree as ET
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for _, el in ET.iterparse(z.open("xl/sharedStrings.xml")):
            if el.tag == ns + "si":
                shared.append("".join(t.text or "" for t in el.iter(ns + "t")))
                el.clear()
    sheet = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))[0]

    def col(ref):
        n = 0
        for ch in ref:
            if not ch.isalpha():
                break
            n = n * 26 + ord(ch.upper()) - 64
        return n - 1

    for _, el in ET.iterparse(z.open(sheet)):
        if el.tag != ns + "row":
            continue
        cells = {}
        for c in el.iter(ns + "c"):
            t, v = c.get("t"), c.find(ns + "v")
            if t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter(ns + "t"))
            elif v is None:
                continue
            elif t == "s":
                val = shared[int(v.text)]
            else:
                val = v.text
            cells[col(c.get("r"))] = val
        el.clear()
        yield [cells.get(i) for i in range(max(cells) + 1)] if cells else []


def rows_of(path):
    """엑셀 → (머리글, 행 생성기). 첫 행은 안내문, 둘째 행이 머리글."""
    it = xlsx_rows(path)
    for row in it:
        if row and row[0] == "시도":
            header = [str(c).strip() if c is not None else "" for c in row]
            break
    else:
        raise RuntimeError(f"{path}: 머리글('시도'로 시작하는 행)을 못 찾았습니다.")

    def gen():
        for row in it:
            if row and row[0]:
                yield {h: (str(v).strip() if v is not None else None) for h, v in zip(header, row) if h}
    return header, gen()


def num(v):
    try:
        return float(v) if v not in (None, "", "-") else None
    except ValueError:
        return None


def find(folder, word):
    hit = sorted(folder.glob(f"*_{word}*.xlsx"))
    if not hit:
        raise RuntimeError(f"{folder}에 '{word}' 파일이 없습니다.")
    return hit[-1]


def cmd_load(a):
    import psycopg2.extras
    from datetime import date

    import molit_rent as common
    folder = Path(a.folder)
    stamp = re.match(r"(\d{8})", find(folder, "기본정보").name).group(1)
    snapshot = date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:]))

    # 면적정보: 단지마다 전용면적 세부 행이 여러 개 → 단지 합계 값은 같은 칸이 반복된다
    area = {}
    _, rows = rows_of(find(folder, "면적정보"))
    for r in rows:
        area.setdefault(r["단지코드"], (num(r.get("관리비부과면적")), num(r.get("주거전용면적(단지합계)"))))

    complexes = []
    _, rows = rows_of(find(folder, "기본정보"))
    for r in rows:
        code = r["단지코드"]
        ma, pa = area.get(code, (None, None))
        hh = num(r.get("세대수"))
        complexes.append((code, snapshot, r["시도"], r["시군구"] or "", r.get("읍면"), r.get("동리"), r.get("단지명"),
                          r.get("단지분류"), int(hh) if hh is not None else None, r.get("난방방식"), ma, pa,
                          json.dumps(r, ensure_ascii=False)))

    fees = []
    _, rows = rows_of(find(folder, "관리비정보"))
    for r in rows:
        ym = (r.get("발생년월(YYYYMM)") or "")[:6]
        if not re.fullmatch(r"\d{6}", ym):
            continue
        fees.append((r["단지코드"], ym, snapshot, num(r.get("공용관리비(합계)")), num(r.get("장충금 월부과액")),
                     num(r.get("개별사용료계")), json.dumps(r, ensure_ascii=False)))

    common.load_env()
    conn = common.connect()
    with conn, conn.cursor() as cur:
        # 의무단지 목록은 매주 통째로 바뀐다 (해제된 단지는 빠진다) → 단지 표는 갈아 끼우고, 관리비는 덮어쓴다
        cur.execute("TRUNCATE raw.kapt_complex")
        psycopg2.extras.execute_values(cur, """INSERT INTO raw.kapt_complex
            (kapt_code, snapshot, sido, sigungu, eupmyeon, dongri, kapt_name, kapt_kind, households, heat_type,
             mgmt_area, private_area, payload) VALUES %s ON CONFLICT (kapt_code) DO NOTHING""", complexes, page_size=2000)
        psycopg2.extras.execute_values(cur, """INSERT INTO raw.kapt_fee
            (kapt_code, ym, snapshot, common_total, ltrm_repair, indiv_total, payload) VALUES %s
            ON CONFLICT (kapt_code, ym) DO UPDATE SET snapshot = EXCLUDED.snapshot, common_total = EXCLUDED.common_total,
                ltrm_repair = EXCLUDED.ltrm_repair, indiv_total = EXCLUDED.indiv_total, payload = EXCLUDED.payload""",
                                       fees, page_size=2000)
    conn.close()
    with_area = sum(1 for c in complexes if c[10])
    print(f"{snapshot}: 단지 {len(complexes)}곳 (부과면적 있음 {with_area}), 관리비 {len(fees)}행 "
          f"({min(f[1] for f in fees)}~{max(f[1] for f in fees)})")


if __name__ == "__main__":
    main()
