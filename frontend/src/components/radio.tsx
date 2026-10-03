import { useEffect, useRef, useState } from 'react'
import { Headphones, Loader2, Radio as RadioIcon, Square } from 'lucide-react'
import { getJSON } from '../lib/api'
import { useUpdates } from '../lib/data'

const BASE = (import.meta as any).env?.VITE_API_BASE ?? '/api'

interface Briefing { text: string; audio: string | null; error?: string; voice?: string | null }

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
      const b = await getJSON<Briefing>(`/voice/briefing?league=${league}${team ? `&team=${team}` : ''}`)
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

/** Radio mode: every new world update for this league is read aloud as it lands. */
export function RadioToggle({ league }: { league: string }) {
  const [on, setOn] = useState(false)
  const updates = useUpdates(league)
  const seen = useRef<number | null>(null)
  const queue = useRef<Promise<void>>(Promise.resolve())
  const n = updates.data?.length ?? 0

  useEffect(() => { seen.current = null }, [league])
  useEffect(() => {
    if (!updates.data) return
    if (seen.current == null || !on) { seen.current = n; return }
    for (let i = seen.current; i < n; i++) {
      const idx = i
      queue.current = queue.current.then(async () => {
        try {
          const r = await getJSON<{ audio: string | null }>(`/voice/update/${league}/${idx}`)
          if (r.audio) await new Promise<void>((res) => { const a = new Audio(`${BASE}${r.audio}`); a.onended = () => res(); a.onerror = () => res(); a.play().catch(() => res()) })
        } catch { /* skip */ }
      })
    }
    seen.current = n
  }, [n, on, league, updates.data])

  return (
    <button className={`btn ${on ? 'primary' : 'ghost'}`} onClick={() => setOn((x) => !x)} aria-pressed={on} title="Read every new world update aloud (ElevenLabs)">
      <RadioIcon size={14} /> {on ? 'Radio on' : 'Radio'}
    </button>
  )
}
