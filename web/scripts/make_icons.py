"""
아이콘 PNG와 링크 미리보기 이미지(og.png)를 만든다 (web/public/icon.svg와 같은 그림을 Pillow로 다시 그림).

    python web/scripts/make_icons.py

만드는 파일 (web/public/)
  apple-touch-icon.png  180×180   아이폰 홈 화면
  icon-192.png, icon-512.png       안드로이드·PWA
  og.png                1200×630  카카오톡·슬랙 등 링크 미리보기 (index.html og:image)
글꼴: Windows 맑은 고딕(래스터 이미지로만 씀). 다른 OS면 FONT_* 경로를 바꾼다.
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "public"
BLUE, WHITE, SUN = (42, 120, 214), (255, 255, 255), (255, 214, 107)
INK, MUTED, BG = (11, 11, 11), (82, 81, 78), (238, 245, 255)
FONT_BOLD = "C:/Windows/Fonts/malgunbd.ttf"
FONT_REG = "C:/Windows/Fonts/malgun.ttf"
SS = 8   # 크게 그린 뒤 줄여서 가장자리를 매끄럽게


def icon(size):
    """64 단위 좌표의 아이콘을 size×size로"""
    k = size * SS / 64
    im = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    P = lambda x, y: (x * k, y * k)
    d.rounded_rectangle([P(0, 0), P(64, 64)], radius=15 * k, fill=BLUE)
    # 지도 핀: 원(중심 32,27 반지름 16) + 끝점(32,55)까지의 접선 삼각형
    cx, cy, r, tip = 32, 27, 16, (32, 55)
    th = math.acos(r / (tip[1] - cy))
    pts = [P(cx + r * math.cos(math.pi / 2 + s * th), cy + r * math.sin(math.pi / 2 + s * th)) for s in (-1, 1)]
    d.ellipse([P(cx - r, cy - r), P(cx + r, cy + r)], fill=WHITE)
    d.polygon([pts[0], P(*tip), pts[1]], fill=WHITE)
    # 집: 지붕(둥근 끝 선) + 몸통 + 문
    w = 3.2 * k
    roof = [P(22.5, 28.5), P(32, 20), P(41.5, 28.5)]
    d.line(roof, fill=BLUE, width=round(w), joint="curve")
    for x, y in roof:
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=BLUE)
    d.rectangle([P(25.5, 27), P(38.5, 36.5)], fill=BLUE)
    d.rounded_rectangle([P(30, 30.5), P(34, 36.5)], radius=1 * k, fill=WHITE)
    d.ellipse([P(40.5, 10), P(50.5, 20)], fill=SUN)
    return im.resize((size, size), Image.LANCZOS)


def og():
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    im.paste(icon(260), (110, 185), icon(260))
    f = lambda path, s: ImageFont.truetype(path, s)
    d.text((430, 150), "어디 살까?", font=f(FONT_BOLD, 92), fill=INK)
    d.text((432, 285), "질문 몇 개면, 내 생활비로", font=f(FONT_BOLD, 44), fill=INK)
    d.text((432, 345), "살기 좋은 동네 3곳", font=f(FONT_BOLD, 44), fill=BLUE)
    d.text((432, 430), "전국 256개 시군구 · 공공데이터로 계산한 월 생활비",
           font=f(FONT_REG, 28), fill=MUTED)
    d.text((432, 500), "wherelive-phi.vercel.app", font=f(FONT_BOLD, 28), fill=BLUE)
    return im


if __name__ == "__main__":
    for s, name in ((180, "apple-touch-icon.png"), (192, "icon-192.png"), (512, "icon-512.png")):
        icon(s).save(OUT / name)
    og().save(OUT / "og.png", optimize=True)
    print("저장:", ", ".join(p.name for p in sorted(OUT.glob("*.png"))))
