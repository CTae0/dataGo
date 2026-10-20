// 숫자·정밀도 표시 도우미

// 순차 색(파랑, 밝음 → 어두움 = 싸다 → 비싸다). dataviz 기본 팔레트의 sequential blue 단계
export const RAMP = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#104281']
export const NO_DATA = '#e4e3df'
// 전월세 추이 3계열: categorical 1~3 (파랑·주황·청록)
export const SERIES = { s: '#2a78d6', m: '#eb6834', l: '#1baf7a' }
export const SIZE_LABEL = { s: '1인 (≤40㎡)', m: '2인 (40~60㎡)', l: '가족 (60~85㎡)' }

export const GRAN_LABEL = {
  exact: '시군구 값',
  si: '시 단위 값',
  legacy: '옛 행정구역 값',
  sido_part: '통합 전 시도 평균',
  sido: '시도 평균',
}
export const isFallback = (g) => g === 'sido' || g === 'sido_part'

const nf0 = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 })
const nf1 = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 1 })

export function formatValue(v, unit) {
  if (v === null || v === undefined || Number.isNaN(v)) return '자료 없음'
  if (unit === '만원') {
    // 보증금: 1억 이상은 억 단위
    return v >= 10000 ? `${nf1.format(v / 10000)}억 원` : `${nf0.format(v)}만 원`
  }
  if (unit === '만원/월') return `월 ${nf1.format(v)}만 원`
  if (unit === '원/월') return `월 ${nf0.format(v)}원`
  if (unit === '원') return `${nf0.format(v)}원`
  if (unit === '지수') return nf1.format(v)
  return `${nf1.format(v)} ${unit}`
}

// 분위수 경계 (6구간). values는 null 제외
export function quantileBreaks(values, k = RAMP.length) {
  const xs = values.filter((v) => v !== null && v !== undefined && !Number.isNaN(v)).sort((a, b) => a - b)
  if (!xs.length) return []
  const breaks = []
  for (let i = 1; i < k; i++) {
    const pos = (xs.length - 1) * (i / k)
    const lo = Math.floor(pos)
    const hi = Math.ceil(pos)
    breaks.push(xs[lo] + (xs[hi] - xs[lo]) * (pos - lo))
  }
  return breaks
}

export function classOf(v, breaks) {
  if (v === null || v === undefined || Number.isNaN(v)) return -1
  let c = 0
  while (c < breaks.length && v > breaks[c]) c++
  return c
}

export function ymLabel(ym) {
  return ym ? `${ym.slice(0, 4)}.${ym.slice(4, 6)}` : ''
}
