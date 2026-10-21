// 결과 공유 이미지 (1080×1350 PNG, 1위 카드 하나). 라이브러리 없이 canvas로 그린다.
// 카드 그림은 화면에 이미 있는 Scene SVG를 그대로 옮겨 그린다 (애니메이션은 멈춘 한 장면).
// 출처 표시: 공공데이터 원천을 한 줄로 밝힌다 (ATTRIBUTION.md — 오피넷은 출처 명시 필수).
import { GROUP_COLOR } from './format.js'

const W = 1080, H = 1350
const FONT = '"Pretendard", "Apple SD Gothic Neo", "Malgun Gothic", system-ui, sans-serif'
const INK = '#0b0b0b', MUTED = '#77766f', ACCENT = '#2a78d6', BG = '#f3f7fc'
const MEDALS = ['🥇 1위', '🥈 2위', '🥉 3위']
export const ATTRIBUTION_LINE = '자료: 국토교통부 실거래가·K-apt, 한국전력공사, 한국석유공사 오피넷, 한국소비자원, 행정안전부 등 공공데이터(가공) · 추정치'

const manwon = (v) => `${Math.round(v / 10_000).toLocaleString('ko-KR')}만 원`

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = reject
    img.src = src
  })
}

// 화면의 SVG 요소 → 이미지 (같은 출처 data URL이라 canvas가 오염되지 않는다)
function svgToImage(svg, w, h) {
  const clone = svg.cloneNode(true)
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  clone.setAttribute('width', w)
  clone.setAttribute('height', h)
  const text = new XMLSerializer().serializeToString(clone)
  return loadImage(`data:image/svg+xml;charset=utf-8,${encodeURIComponent(text)}`)
}

function wrap(ctx, text, maxWidth, maxLines) {
  const lines = []
  let line = ''
  for (const ch of text) {
    if (ctx.measureText(line + ch).width > maxWidth && line) {
      lines.push(line)
      line = ch
      if (lines.length === maxLines) break
    } else line += ch
  }
  if (lines.length < maxLines && line) lines.push(line)
  if (lines.length === maxLines && lines.join('').length < text.length) {
    lines[maxLines - 1] = lines[maxLines - 1].slice(0, -1) + '…'
  }
  return lines
}

/**
 * @param results 추천 결과 (/api/recommend results, card 포함) — 1위만 그린다
 * @param groups  spec.groups [{id, label}]
 * @param persona 페르소나 한 줄
 * @param sceneFor (region_code) → 화면의 Scene <svg> 요소 또는 null
 * @returns Promise<Blob> (image/png)
 */
export async function makeShareImage({ results, groups, persona, sceneFor, host }) {
  const canvas = document.createElement('canvas')
  canvas.width = W
  canvas.height = H
  const ctx = canvas.getContext('2d')
  await document.fonts?.ready

  ctx.fillStyle = BG
  ctx.fillRect(0, 0, W, H)

  // 머리: 아이콘 + 이름 + 페르소나
  try { ctx.drawImage(await loadImage('/icon.svg'), 48, 52, 88, 88) } catch { /* 아이콘 없이 진행 */ }
  ctx.fillStyle = INK
  ctx.font = `800 54px ${FONT}`
  ctx.textBaseline = 'alphabetic'
  ctx.fillText('어디 살까?', 158, 112)
  ctx.fillStyle = MUTED
  ctx.font = `500 28px ${FONT}`
  ctx.fillText('내 생활비로 고른 1등 동네', 160, 150)
  ctx.fillStyle = INK
  ctx.font = `600 30px ${FONT}`
  wrap(ctx, `${persona} 님에게 어울리는 동네`, W - 96, 2).forEach((l, i) => ctx.fillText(l, 48, 214 + i * 42))

  // 1위 카드 하나 (큰 그림 + 지역 + 월 생활비 + 묶음 막대와 금액)
  const x = results[0]
  const cx = 40, cy = 290, cw = W - 80, ch = 935
  ctx.fillStyle = '#ffffff'
  ctx.beginPath(); ctx.roundRect(cx, cy, cw, ch, 32); ctx.fill()
  ctx.strokeStyle = '#e4e3df'; ctx.lineWidth = 2; ctx.stroke()

  const ix = cx + 24, iy = cy + 24, iw = cw - 48, ih = Math.round(iw * 9 / 16)
  const svg = sceneFor(x.region_code)
  ctx.save()
  ctx.beginPath(); ctx.roundRect(ix, iy, iw, ih, 22); ctx.clip()
  if (svg) {
    try { ctx.drawImage(await svgToImage(svg, iw, ih), ix, iy, iw, ih) } catch { /* 그림 없이 */ }
  } else { ctx.fillStyle = '#e8f3ff'; ctx.fillRect(ix, iy, iw, ih) }
  ctx.restore()

  let ty = iy + ih + 56
  ctx.fillStyle = ACCENT; ctx.font = `800 34px ${FONT}`
  const medal = MEDALS[0]
  ctx.fillText(medal, ix, ty)
  ctx.fillStyle = MUTED; ctx.font = `500 30px ${FONT}`
  const mw = ctx.measureText(medal).width
  ctx.fillText(wrap(ctx, x.card?.nickname || '', iw - mw - 20, 1)[0] || '', ix + mw + 20, ty)
  ty += 72
  ctx.fillStyle = INK; ctx.font = `800 64px ${FONT}`
  ctx.fillText(wrap(ctx, `${x.sido} ${x.sigungu}`, iw, 1)[0], ix, ty)
  ty += 70
  ctx.font = `800 50px ${FONT}`
  const total = `월 약 ${manwon(x.total)}`
  ctx.fillText(total, ix, ty)
  const totalW = ctx.measureText(total).width
  if (x.card?.level) {
    ctx.fillStyle = ACCENT; ctx.font = `600 28px ${FONT}`
    ctx.fillText(wrap(ctx, `${x.card.level.name} · 저렴한 순 상위 ${x.card.level.pct}%`, iw - totalW - 24, 1)[0] || '',
                 ix + totalW + 24, ty - 4)
  }
  // 묶음 4색 막대 + 묶음별 금액
  const g = x.card?.groups || {}
  const sum = Object.values(g).reduce((a, v) => a + v, 0) || 1
  ty += 30
  let bx = ix
  ctx.save()
  ctx.beginPath(); ctx.roundRect(ix, ty, iw, 26, 13); ctx.clip()
  for (const grp of groups) {
    const w = ((g[grp.id] || 0) / sum) * iw
    ctx.fillStyle = GROUP_COLOR[grp.id]; ctx.fillRect(bx, ty, w, 26)
    bx += w
  }
  ctx.restore()
  ty += 84
  ctx.font = `500 27px ${FONT}`
  groups.forEach((grp, i) => {   // 2×2: 묶음 이름 + 금액
    const lx = ix + (i % 2) * (iw / 2), ly = ty + Math.floor(i / 2) * 42
    ctx.fillStyle = GROUP_COLOR[grp.id]
    ctx.beginPath(); ctx.roundRect(lx, ly - 21, 22, 22, 5); ctx.fill()
    ctx.fillStyle = MUTED
    ctx.fillText(`${grp.label} ${manwon(g[grp.id] || 0)}`, lx + 32, ly)
  })

  // 권유 문구 + 출처
  ctx.fillStyle = ACCENT; ctx.font = `800 34px ${FONT}`
  ctx.fillText(`나에게 맞는 동네는?  ${host}`, 48, 1274)
  ctx.fillStyle = MUTED; ctx.font = `400 19px ${FONT}`
  wrap(ctx, ATTRIBUTION_LINE, W - 96, 2).forEach((l, i) => ctx.fillText(l, 48, 1308 + i * 26))

  return new Promise((resolve) => canvas.toBlob(resolve, 'image/png'))
}
