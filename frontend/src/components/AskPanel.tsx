import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bot, Loader2, MessageSquare, Send, X } from 'lucide-react'
import { getJSON, postJSON } from '../lib/api'
import { league as leagueOf } from '../lib/leagues'

interface Msg { role: 'you' | 'agent'; text: string; prose?: string | null; pending?: boolean; showExact?: boolean }

const SUGGEST: Record<string, string[]> = {
  'college-football': ['How are Michigan doing?', 'What if Michigan beats Ohio State?', 'Which games matter tonight?', 'Should I watch BYU or Texas Tech?'],
  nfl: ['Who will win the Super Bowl?', 'How are the Detroit Lions doing?', 'What if the Bills starting quarterback misses 3 games?'],
  nba: ['Who will win the NBA title?', 'How are the Celtics doing?'],
  nhl: ['Who will win the Stanley Cup?', 'How are the Detroit Red Wings doing?'],
  'mens-college-basketball': ['Who will win the national title in college basketball?', 'How is umich doing in college basketball?'],
  f1: ['F1 title odds', 'Who will win the constructors championship?'],
}

/** tiny, safe markdown: **bold**, *italic*, `code`, links, "- " / "1. " lists; SportsWorld links stay in the app */
function Md({ text, go }: { text: string; go: (path: string) => void }) {
  const inline = (s: string, key: string): ReactNode[] => {
    const parts: ReactNode[] = []
    const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|https?:\/\/[^\s)]+)/g
    let last = 0
    let m: RegExpExecArray | null
    let i = 0
    while ((m = re.exec(s))) {
      if (m.index > last) parts.push(s.slice(last, m.index))
      const t = m[0]
      if (t.startsWith('**')) parts.push(<strong key={`${key}-${i++}`}>{t.slice(2, -2)}</strong>)
      else if (t.startsWith('`')) parts.push(<code key={`${key}-${i++}`}>{t.slice(1, -1)}</code>)
      else if (t.startsWith('*')) parts.push(<em key={`${key}-${i++}`}>{t.slice(1, -1)}</em>)
      else {
        const internal = t.replace(/^https?:\/\/(www\.)?sportsworld\.tech/, '')
        parts.push(internal !== t
          ? <a key={`${key}-${i++}`} href={internal || '/'} onClick={(e) => { e.preventDefault(); go(internal || '/') }}>{internal || '/'}</a>
          : <a key={`${key}-${i++}`} href={t} target="_blank" rel="noreferrer">{t}</a>)
      }
      last = m.index + t.length
    }
    if (last < s.length) parts.push(s.slice(last))
    return parts
  }
  const lines = text.split('\n')
  return (
    <>
      {lines.map((l, i) => {
        const li = l.match(/^\s*(?:- |\d+\. )(.*)$/)
        if (li) return <div key={i} className="md-li">{inline(li[1], `l${i}`)}</div>
        if (!l.trim()) return <div key={i} className="md-gap" />
        return <Fragment key={i}><p className="md-p">{inline(l, `p${i}`)}</p></Fragment>
      })}
    </>
  )
}

export function AskPanel({ leagueId }: { leagueId: string }) {
  const lg = leagueOf(leagueId)
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const end = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }) }, [msgs, busy])
  useEffect(() => { if (open) input.current?.focus() }, [open])

  const ask = async (text: string) => {
    const t = text.trim()
    if (!t || busy) return
    setMsgs((m) => [...m, { role: 'you', text: t }])
    setQ('')
    setBusy(true)
    try {
      const r = await postJSON<{ answer: string; answer_id: string }>('/agent/ask', { text: lg.id === 'college-football' || /college|cfb|nfl|nba|nhl|f1|super bowl|stanley/i.test(t) ? t : `${t} (${lg.name})` })
      let idx = -1
      setMsgs((m) => { idx = m.length; return [...m, { role: 'agent', text: r.answer, pending: true }] })
      // conversational version arrives a few seconds later; numbers are verified server-side
      getJSON<{ prose: string | null }>(`/agent/rephrase/${r.answer_id}`)
        .then((p) => setMsgs((m) => m.map((x, i) => (i === idx ? { ...x, prose: p.prose, pending: false } : x))))
        .catch(() => setMsgs((m) => m.map((x, i) => (i === idx ? { ...x, pending: false } : x))))
    } catch (e) {
      setMsgs((m) => [...m, { role: 'agent', text: `The engine couldn't answer right now. ${(e as Error).message.slice(0, 120)}` }])
    }
    setBusy(false)
  }

  return (
    <>
      <button className="ask-fab" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-controls="ask-panel">
        {open ? <X size={18} /> : <MessageSquare size={18} />} {open ? 'Close' : 'Ask SportsWorld'}
      </button>
      {open && (
        <aside id="ask-panel" className="ask-panel" aria-label="Ask SportsWorld">
          <header>
            <Bot size={18} aria-hidden />
            <div><b>Ask SportsWorld</b><span>Runs the live engine: odds, what-ifs, games to watch. Same agent as on ASI:One (Fetch.ai).</span></div>
          </header>
          <div className="ask-log">
            {msgs.length === 0 && (
              <div className="ask-suggest">
                {(SUGGEST[lg.id] ?? SUGGEST['college-football']).map((s) => <button key={s} onClick={() => ask(s)}>{s}</button>)}
              </div>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={`ask-msg ${m.role}`}>
                {m.role === 'you' ? m.text : m.prose ? (
                  <>
                    <p className="md-p">{m.prose}</p>
                    <button className="ask-exact" onClick={() => setMsgs((xs) => xs.map((x, j) => (j === i ? { ...x, showExact: !x.showExact } : x)))}>
                      {m.showExact ? 'Hide exact numbers' : 'Show exact numbers'}
                    </button>
                    {m.showExact && <div className="ask-exact-body"><Md text={m.text} go={(p) => navigate(p)} /></div>}
                    <small className="ask-note">Written by self-hosted Llama from the engine’s answer · every number checked</small>
                  </>
                ) : (
                  <>
                    <Md text={m.text} go={(p) => navigate(p)} />
                    {m.pending && <small className="ask-note"><Loader2 size={11} className="spin" /> writing a conversational version…</small>}
                  </>
                )}
              </div>
            ))}
            {busy && <div className="ask-msg agent"><Loader2 size={14} className="spin" /> Running the engine…</div>}
            <div ref={end} />
          </div>
          <form className="ask-input" onSubmit={(e) => { e.preventDefault(); ask(q) }}>
            <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} placeholder="How are Michigan doing? What if…" aria-label="Ask a question" maxLength={500} />
            <button className="btn primary" type="submit" disabled={busy || !q.trim()} aria-label="Send"><Send size={14} /></button>
          </form>
        </aside>
      )}
    </>
  )
}
