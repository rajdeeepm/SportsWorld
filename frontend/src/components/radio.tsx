import { useEffect, useRef, useState } from 'react'
import { Headphones, Loader2, Radio as RadioIcon, Square } from 'lucide-react'
import { getJSON } from '../lib/api'
import { useBoard, useUpdates } from '../lib/data'
import { mergeLive, useLiveGames } from '../lib/live'

const BASE = (import.meta as any).env?.VITE_API_BASE ?? '/api'

interface Clip { text: string; audio: string | null; error?: string }

function playClip(src: string) {
  return new Promise<void>((res) => {
    const a = new Audio(`${BASE}${src}`)
    a.onended = () => res()
    a.onerror = () => res()
    a.play().catch(() => res())
  })
}

/** Spoken briefing: text written from the engine's numbers by a template, voiced by ElevenLabs. */
export function ListenButton({ league, team, label = 'Listen' }: { league: string; team?: string; label?: string }) {
  const [state, setState] = useState<'idle' | 'loading' | 'playing' | 'error'>('idle')
  const [text, setText] = useState<string>('')
  const audio = useRef<HTMLAudioElement | null>(null)
  useEffect(() => () => audio.current?.pause(), [])

  const play = async () => {
    if (state === 'playing') { audio.current?.pause(); setState('idle'); return }
    setState('loading')
    try {
      const b = await getJSON<Clip>(`/voice/briefing?league=${league}${team ? `&team=${team}` : ''}`)
      setText(b.text)
      if (!b.audio) { setState('error'); return }
      const a = new Audio(`${BASE}${b.audio}`)
      audio.current = a
      a.onended = () => setState('idle')
      await a.play()
      setState('playing')
    } catch {
      setState('error')
    }
  }

  return (
    <div className="listen">
      <button className={`btn ${state === 'playing' ? 'primary' : ''}`} onClick={play} aria-pressed={state === 'playing'}>
        {state === 'loading' ? <Loader2 size={14} className="spin" /> : state === 'playing' ? <Square size={13} /> : <Headphones size={14} />}
        {state === 'playing' ? 'Stop' : state === 'loading' ? 'Preparing…' : label}
      </button>
      {text && (state === 'playing' || state === 'error') && (
        <p className="listen-text">{state === 'error' ? 'Voice unavailable; transcript: ' : ''}{text}<small> Spoken from SportsWorld’s live numbers · voice by ElevenLabs</small></p>
      )}
    </div>
  )
}

const SWING = 0.1 // announce a live game when its win probability moves 10+ points since last announced
const MIN_LEVERAGE = 0.025 // ... and only games that matter to the season (Medium leverage or more)

/** Radio mode: says hello and the latest result at once, then every new final and every big live swing. */
export function RadioToggle({ league }: { league: string }) {
  const [on, setOn] = useState(false)
  const [now, setNow] = useState<string>('')
  const updates = useUpdates(league)
  const board = useBoard(league)
  const live = useLiveGames(league)
  const seen = useRef<number | null>(null)
  const lastP = useRef<Map<string, number>>(new Map())
  const queue = useRef<Promise<void>>(Promise.resolve())
  const n = updates.data?.length ?? 0

  const say = (path: string) => {
    queue.current = queue.current.then(async () => {
      try {
        const c = await getJSON<Clip>(path)
        setNow(c.text)
        if (c.audio) await playClip(c.audio)
      } catch { /* skip a clip that fails */ }
    })
  }

  useEffect(() => { setOn(false); seen.current = null; lastP.current.clear() }, [league])

  // switching on: speak immediately, then the latest final
  const toggle = () => {
    if (on) { setOn(false); setNow(''); return }
    setOn(true)
    seen.current = n
    say(`/voice/intro/${league}`)
    if (n > 0) say(`/voice/update/${league}/-1`)
    for (const g of mergeLive(board.data?.events ?? [], live.map)) if (g.state === 'in' && g.p_home != null) lastP.current.set(g.event_id, g.p_home)
  }

  // new finals / availability changes
  useEffect(() => {
    if (!on || seen.current == null) return
    for (let i = seen.current; i < n; i++) say(`/voice/update/${league}/${i}`)
    seen.current = n
  }, [n, on]) // eslint-disable-line react-hooks/exhaustive-deps

  // big swings in live games that matter (pushed by SpacetimeDB, or polled)
  useEffect(() => {
    if (!on) return
    for (const g of mergeLive(board.data?.events ?? [], live.map)) {
      if (g.state !== 'in' || g.p_home == null) continue
      const lev = Math.max(Math.abs(g.leverage_home ?? 0), Math.abs(g.leverage_away ?? 0))
      const prev = lastP.current.get(g.event_id)
      if (prev == null) { lastP.current.set(g.event_id, g.p_home); continue }
      if (lev >= MIN_LEVERAGE && Math.abs(g.p_home - prev) >= SWING) {
        lastP.current.set(g.event_id, g.p_home)
        say(`/voice/game/${league}/${g.event_id}`)
      }
    }
  }, [on, live.map, board.data]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="listen">
      <button className={`btn ${on ? 'primary' : 'ghost'}`} onClick={toggle} aria-pressed={on} title="Read every new final and every big live swing aloud (ElevenLabs)">
        <RadioIcon size={14} /> {on ? 'Radio on' : 'Radio'}
      </button>
      {on && <p className="listen-text">{now || 'On air…'}<small> Waiting for the next final or a 10-point swing in a game that matters · voice by ElevenLabs</small></p>}
    </div>
  )
}

interface CommentaryResponse { lines: { id: string; text: string; key?: boolean }[]; last_id: string | null; audio: string | null; final?: boolean; error?: string }

/** Live play-by-play call for one game: new plays every few seconds, each voiced with SportsWorld's probability. */
export function CommentaryToggle({ league, eventId, live }: { league: string; eventId: string; live: boolean }) {
  const [on, setOn] = useState(false)
  const [lines, setLines] = useState<{ id: string; text: string; key?: boolean }[]>([])
  const [busy, setBusy] = useState(false)
  const last = useRef<string | null>(null)
  const playing = useRef(false)
  const pending = useRef<string[]>([])

  useEffect(() => { setOn(false); setLines([]); last.current = null }, [eventId])

  const drain = async () => {
    if (playing.current) return
    playing.current = true
    while (pending.current.length) {
      const next = pending.current.length > 2 ? pending.current.splice(0, pending.current.length - 1).pop()! : pending.current.shift()! // stay current: drop backlog
      await playClip(next)
    }
    playing.current = false
  }

  useEffect(() => {
    if (!on) return
    let stop = false
    const tick = async () => {
      if (stop) return
      setBusy(true)
      try {
        const r = await getJSON<CommentaryResponse>(`/voice/commentary/${league}/${eventId}${last.current ? `?after=${encodeURIComponent(last.current)}` : ''}`)
        if (r.last_id) last.current = r.last_id
        if (r.lines.length) setLines((xs) => [...r.lines.slice().reverse(), ...xs].slice(0, 8))
        if (r.audio) { pending.current.push(r.audio); drain() }
        if (r.final) { setLines((xs) => [{ id: 'final', text: 'Final. Commentary ended.' }, ...xs]); setOn(false) }
      } catch { /* keep trying */ }
      setBusy(false)
    }
    tick()
    const id = setInterval(tick, 8000)
    return () => { stop = true; clearInterval(id) }
  }, [on, league, eventId]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="commentary">
      <button className={`btn ${on ? 'primary' : ''}`} onClick={() => setOn((x) => !x)} aria-pressed={on} disabled={!live && !on}
        title={live ? 'Voice every new play with SportsWorld’s live win probability (ElevenLabs)' : 'Commentary is available while the game is live'}>
        {busy && on ? <Loader2 size={14} className="spin" /> : <RadioIcon size={14} />} {on ? 'Commentary on' : live ? 'Live commentary' : 'Commentary (live games)'}
      </button>
      {on && (
        <ol className="call-sheet" aria-live="polite">
          {lines.length === 0 && <li className="muted">Listening for the next play…</li>}
          {lines.map((l, i) => <li key={`${l.id}-${i}`} className={l.key ? 'key' : ''}>{l.text}</li>)}
        </ol>
      )}
    </div>
  )
}
