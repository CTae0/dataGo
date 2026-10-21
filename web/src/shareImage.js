// 결과 공유 이미지 (1080×1350 PNG). 라이브러리 없이 canvas로 그린다.
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
 * @param results 추천 결과 위 3개 (/api/recommend results[0..2], card 포함)
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
  ctx.fillText('내 생활비로 고른 동네 TOP 3', 160, 150)
  ctx.fillStyle = INK
  ctx.font = `600 30px ${FONT}`
  wrap(ctx, `${persona} 님에게 어울리는 동네`, W - 96, 2).forEach((l, i) => ctx.fillText(l, 48, 214 + i * 42))

  // 카드 3장
  for (const [i, x] of results.slice(0, 3).entries()) {
    const y = 290 + i * 300
    ctx.fillStyle = '#ffffff'
    ctx.beginPath(); ctx.roundRect(40, y, W - 80, 272, 28); ctx.fill()
    ctx.strokeStyle = '#e4e3df'; ctx.lineWidth = 2; ctx.stroke()

    const svg = sceneFor(x.region_code)
    ctx.save()
    ctx.beginPath(); ctx.roundRect(64, y + 24, 400, 225, 18); ctx.clip()
    if (svg) {
      try { ctx.drawImage(await svgToImage(svg, 400, 225), 64, y + 24, 400, 225) } catch { /* 그림 없이 */ }
    } else { ctx.fillStyle = '#e8f3ff'; ctx.fillRect(64, y + 24, 400, 225) }
    ctx.restore()

    const tx = 496, maxW = W - 80 - (tx - 40) - 32
    ctx.fillStyle = ACCENT; ctx.font = `800 30px ${FONT}`
    ctx.fillText(MEDALS[i], tx, y + 62)
    ctx.fillStyle = MUTED; ctx.font = `500 24px ${FONT}`
    ctx.fillText(wrap(ctx, x.card?.nickname || '', maxW, 1)[0] || '', tx, y + 100)
    ctx.fillStyle = INK; ctx.font = `800 42px ${FONT}`
    ctx.fillText(wrap(ctx, `${x.sido} ${x.sigungu}`, maxW, 1)[0], tx, y + 152)
    ctx.font = `800 36px ${FONT}`
    const total = `월 약 ${manwon(x.total)}`
    ctx.fillText(total, tx, y + 202)
    const totalW = ctx.measureText(total).width
    if (x.card?.level) {
      ctx.fillStyle = ACCENT; ctx.font = `600 22px ${FONT}`
      ctx.fillText(wrap(ctx, `${x.card.level.name} · 상위 ${x.card.level.pct}%`, maxW - totalW - 18, 1)[0] || '',
                   tx + totalW + 18, y + 200)
    }
    // 묶음 4색 막대
    const g = x.card?.groups || {}
    const sum = Object.values(g).reduce((a, v) => a + v, 0) || 1
    let bx = tx
    const bw = maxW
    ctx.save()
    ctx.beginPath(); ctx.roundRect(tx, y + 222, bw, 18, 9); ctx.clip()
    for (const grp of groups) {
      const w = ((g[grp.id] || 0) / sum) * bw
      ctx.fillStyle = GROUP_COLOR[grp.id]; ctx.fillRect(bx, y + 222, w, 18)
      bx += w
    }
    ctx.restore()
  }

  // 범례 + 권유 문구 + 출처
  let lx = 48
  ctx.font = `500 24px ${FONT}`
  for (const grp of groups) {
    ctx.fillStyle = GROUP_COLOR[grp.id]
    ctx.beginPath(); ctx.roundRect(lx, 1206, 22, 22, 5); ctx.fill()
    ctx.fillStyle = MUTED
    ctx.fillText(grp.label, lx + 32, 1226)
    lx += 32 + ctx.measureText(grp.label).width + 36
  }
  ctx.fillStyle = ACCENT; ctx.font = `800 34px ${FONT}`
  ctx.fillText(`나에게 맞는 동네는?  ${host}`, 48, 1276)
  ctx.fillStyle = MUTED; ctx.font = `400 19px ${FONT}`
  wrap(ctx, ATTRIBUTION_LINE, W - 96, 2).forEach((l, i) => ctx.fillText(l, 48, 1310 + i * 26))

  return new Promise((resolve) => canvas.toBlob(resolve, 'image/png'))
}
