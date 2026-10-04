import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ExternalLink, Newspaper, Quote } from 'lucide-react'
import { getJSON } from '../lib/api'
import { useMeta } from '../lib/data'
import type { LeagueConfig } from '../lib/leagues'
import { ago } from '../lib/format'
import { Empty, ErrorNote, Loading, Panel, TeamLogo } from '../components/ui'

interface Signal { category: string; team_id: string; team: string; player?: string | null; status?: string | null; evidence_span: string; disagreement?: { official_status?: string } | null }
interface Article { article_id: string; type?: string; headline: string; description: string; published?: string; url?: string; image?: string; team_ids: string[]; premium: boolean; signals: Signal[] }

const KIND: Record<string, string> = { Recap: 'Recap', Media: 'Video', HeadlineNews: 'News', Story: 'Story', Preview: 'Preview' }

export function News({ lg }: { lg: LeagueConfig }) {
  const q = useQuery({ queryKey: ['news-feed', lg.id], queryFn: () => getJSON<{ articles: Article[] }>(`/competitions/${lg.id}/news-feed`), refetchInterval: 120_000 })
  const meta = useMeta(lg.id).data ?? {}
  const [only, setOnly] = useState<'all' | 'model'>('all')
  const arts = useMemo(() => (q.data?.articles ?? []).map((a) => ({ ...a, signals: dedupe(a.signals.filter((s) => s.player && s.status && ['availability', 'return_from_injury', 'suspension'].includes(s.category))) })), [q.data])
  const shown = only === 'model' ? arts.filter((a) => a.signals.length) : arts
  return (
    <>
      <div className="hero"><div>
        <p className="hero-kicker">Know what matters before you watch.</p>
        <h1>{lg.name}: <em>News</em></h1>
        <p>The latest from ESPN, tagged to the teams ESPN names. Where an article reports a player's availability, SportsWorld quotes the line it read; the official injury report, not a headline, is what moves a forecast.</p>
      </div></div>
      <Panel title="Latest" icon={Newspaper} flush
        action={<div className="seg"><button className={only === 'all' ? 'on' : ''} onClick={() => setOnly('all')}>All</button><button className={only === 'model' ? 'on' : ''} onClick={() => setOnly('model')}>Read by the model</button></div>}
        foot="Source: ESPN news API, refreshed every 2 minutes. Player notes are extracted by self-hosted Llama and kept only when the quoted line appears verbatim in the article.">
        {q.isLoading ? <div style={{ padding: 14 }}><Loading rows={6} /></div> : q.error ? <ErrorNote error={q.error} what="the news feed" /> : !shown.length ? <Empty title="Nothing here yet" /> : (
          <ul className="news-list">
            {shown.map((a) => (
              <li key={a.article_id} className="news-item">
                {a.image && <img src={a.image} alt="" loading="lazy" />}
                <div className="news-body">
                  <div className="news-meta">
                    <span className="tag">{KIND[a.type ?? ''] ?? a.type ?? 'News'}</span>
                    {a.published && <span className="muted">{ago(a.published)}</span>}
                    {a.team_ids.filter((t) => meta[t]).slice(0, 3).map((t) => (
                      <Link key={t} to={`/${lg.id}/team/${t}`} className="news-team"><TeamLogo meta={meta[t]} size={16} />{meta[t].short_name}</Link>
                    ))}
                  </div>
                  <a href={a.url} target="_blank" rel="noreferrer" className="news-head">{a.headline}{a.premium ? ' (ESPN+)' : ''} <ExternalLink size={13} aria-hidden /></a>
                  {a.description && <p>{a.description}</p>}
                  {a.signals.map((s, i) => (
                    <div key={i} className="news-signal">
                      <Quote size={13} aria-hidden />
                      <span><b>{s.player}</b>{s.status ? `: ${s.status}` : ''} ({s.team}). “{s.evidence_span}”
                        {s.disagreement?.official_status ? <em> The official injury report says {s.disagreement.official_status}; the report is what the model uses.</em> : null}</span>
                    </div>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </>
  )
}

function dedupe(s: Signal[]) {
  const seen = new Set<string>()
  return s.filter((x) => { const k = `${x.player}|${x.status}`; if (seen.has(k)) return false; seen.add(k); return true })
}
