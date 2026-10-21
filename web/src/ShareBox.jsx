import { useEffect, useState } from 'react'
import { makeShareImage } from './shareImage.js'

// 결과 공유: ① 결과 이미지(PNG) 저장·공유 ② 내 결과 링크(?a=답) ③ 친구에게 권하기(첫 화면 링크 + 문구)
// 휴대폰은 시스템 공유(카톡 등)로 이미지까지 보내고, 안 되는 브라우저는 저장 + 링크 복사로 대신한다.
export default function ShareBox({ spec, data, persona }) {
  const [img, setImg] = useState(null)        // { url, blob }
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  useEffect(() => () => { if (img) URL.revokeObjectURL(img.url) }, [img])

  const top = data.results.slice(0, 3)
  const top1 = top[0] ? `${top[0].sido} ${top[0].sigungu}` : ''
  const resultUrl = location.href
  const inviteUrl = `${location.origin}/`
  const inviteText = `내 생활비로 골라 보니 살기 좋은 동네 1위는 ${top1}래! 너는 어디 살까? 질문 몇 개면 돼 👉 ${inviteUrl}`
  const canShare = typeof navigator !== 'undefined' && !!navigator.share

  const make = async () => {
    setBusy(true); setMsg('')
    try {
      const blob = await makeShareImage({
        results: top, groups: spec.groups, persona, host: location.host,
        sceneFor: (code) => document.querySelector(`.pcard[data-code="${code}"] .pcard-art svg`),
      })
      setImg({ url: URL.createObjectURL(blob), blob })
    } catch (e) {
      setMsg(`이미지를 만들지 못했어요 (${e?.message || e})`)
    } finally { setBusy(false) }
  }

  // 클립보드 API가 없거나 막힌 브라우저(일부 메신저 내장 브라우저)는 예전 방식(execCommand)으로 한 번 더 시도
  const legacyCopy = (text) => {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'; ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    ta.remove()
    return ok
  }
  const copy = async (text, what) => {
    let ok = false
    try { await navigator.clipboard.writeText(text); ok = true } catch { ok = legacyCopy(text) }
    setMsg(ok ? `${what} 복사했어요. 메신저에 붙여 넣어 보세요.` : '복사하지 못했어요. 아래 주소를 길게 눌러 복사해 주세요.')
  }

  const share = async () => {
    try {
      const file = img && new File([img.blob], 'eodi-salkka.png', { type: 'image/png' })
      if (file && navigator.canShare?.({ files: [file] })) {
        await navigator.share({ files: [file], title: '어디 살까?', text: inviteText })
      } else {
        await navigator.share({ title: '어디 살까?', text: inviteText, url: inviteUrl })
      }
    } catch (e) {
      if (e?.name !== 'AbortError') setMsg('공유하지 못했어요. 이미지 저장이나 링크 복사를 써 주세요.')
    }
  }

  return (
    <section className="sharebox" aria-label="결과 공유">
      <div className="share-head">
        <strong>결과 공유하기</strong>
        <span className="muted small">카드 이미지와 링크로 친구에게도 권해 보세요</span>
      </div>
      <div className="share-actions">
        {!img && <button type="button" className="primary" onClick={make} disabled={busy}>{busy ? '그리는 중…' : '결과 이미지 만들기'}</button>}
        {img && <a className="primary" href={img.url} download="eodi-salkka.png">이미지 저장</a>}
        {img && canShare && <button type="button" className="primary" onClick={share}>공유하기</button>}
        <button type="button" className="secondary" onClick={() => copy(resultUrl, '내 결과 링크를')}>내 결과 링크 복사</button>
        <button type="button" className="secondary" onClick={() => copy(inviteText, '권유 문구와 링크를')}>친구에게 권하기</button>
      </div>
      {img && <img className="share-preview" src={img.url} alt={`공유 이미지: ${top.map((x) => `${x.sido} ${x.sigungu}`).join(', ')}`} />}
      <label className="share-url small">
        <span className="muted">친구에게 보낼 주소</span>
        <input readOnly value={inviteUrl} onFocus={(e) => e.target.select()} />
      </label>
      <p className="muted small" role="status" aria-live="polite">{msg}</p>
    </section>
  )
}
