import { useQuery } from '@tanstack/react-query'
import { getJSON } from './api'

export interface TeamMeta {
  team_id: string
  name: string
  short_name?: string
  location?: string
  nickname?: string
  abbreviation?: string
  color?: string | null
  alt_color?: string | null
  logo?: string | null
  logo_dark?: string | null
  record_summary?: string | null
  standing_summary?: string | null
  rank?: number | null
  venue?: string | null
  venue_city?: string | null
}

export interface SeasonPath {
  wins: number
  p: number
  champion: number | null
  [milestone: string]: number | null
}

export interface SeasonTeam {
  team_id: string
  name: string
  abbreviation?: string | null
  conference?: string | null
  division?: string | null
  rating: number
  rating_sd: number
  games: number
  expected_wins: number
  wins_sd: number
  wins_p05: number
  wins_p95: number
  win_hist: number[]
  expected_points?: number
  points_p05?: number
  points_p95?: number
  seed?: number
  seed_dist?: number[]
  season_paths?: { milestone: string; by_wins: SeasonPath[] }
  [k: string]: unknown
}

export interface SeasonRun {
  league: string
  season: number
  as_of: string
  mode: string
  draws: number
  seed: number
  simulator_version: string
  run_id: string
  global_state_version: number
  event_model_version?: string
  rating_params: Record<string, number>
  teams: SeasonTeam[]
  diagnostics: Record<string, any>
  availability_adjustments?: { team_id: string; delta_points: number; until: string | null }[]
  status?: string
  scenario?: string | null
}

export interface SeasonStatus {
  competition_id: string
  season: number | null
  global_state_version: number
  run_id: string | null
  as_of: string | null
  status: string
  diagnostics: Record<string, any> | null
  board_events: number
}

export interface BoardRow {
  event_id: string
  start_time: string
  week?: number | null
  state: 'pre' | 'in' | 'post'
  status?: string
  period?: number
  clock_seconds?: number
  home_id: string
  away_id: string
  home: string
  away: string
  home_abbr?: string | null
  away_abbr?: string | null
  home_score?: number
  away_score?: number
  home_rank?: number | null
  away_rank?: number | null
  home_record?: string | null
  away_record?: string | null
  venue?: string | null
  conference_game?: boolean
  neutral_site: boolean
  p_home: number | null
  p_home_pregame?: number | null
  live_p_home?: number | null
  interval_90: [number, number] | null
  leverage_home?: number | null
  leverage_away?: number | null
  leverage_milestone?: string | null
  model_version?: string | null
  global_state_version: number
  as_of: string
  freshness: string
}

export interface TeamRemaining extends BoardRow {
  is_home: boolean
  p_win: number | null
}

export interface TeamPage {
  team: SeasonTeam
  remaining: TeamRemaining[]
  recent_results: { event_id: string; date: string; home: string; away: string; home_score: number; away_score: number }[]
  rating_history: { date: string; rating: number; var: number }[]
  meta: TeamMeta
  season_run_id: string
  global_state_version: number
}

export interface StandingRow {
  team_id: string
  name: string
  abbreviation?: string | null
  conference?: string | null
  division?: string | null
  wins: number
  losses: number
  ties: number
  ot_losses: number
  games: number
  conf_record: string
  point_diff: number
  points?: number | null
}

export interface NewsSignal {
  article_id: string
  category: string
  team_id: string
  team: string
  player?: string | null
  status?: string | null
  evidence_span: string
  headline: string
  source_url: string
  published: string
  effect: string
}

export interface WorldUpdate {
  at: string
  global_state_version: number
  reason: string
  teams: string[]
  event_id?: string
  news?: NewsSignal
  rating_after?: Record<string, number>
  [k: string]: unknown
}

export interface Absence {
  player: string
  role: string
  status: string
  p_play: number
  beta: number
  delta_points: number
  reported_at?: string
  status_mapping: string
}

export interface AvailabilityTeam {
  team_id: string
  team: string
  delta_points: number
  absences: Absence[]
  window_days: number | null
  impact_model: string
}

export interface F1Driver {
  driver_id: string
  code: string
  name: string
  constructor_id: string
  points_now: number
  wins_now: number
  rating: number
  rating_sd: number
  reliability: number
  expected_points: number
  points_p05: number
  points_p95: number
  expected_wins: number
  expected_podiums_remaining: number
  title: number
  title_se: number
  rank_dist: number[]
}

export interface F1Constructor {
  constructor_id: string
  name: string
  points_now: number
  car_rating: number
  reliability: number
  expected_points: number
  points_p05: number
  points_p95: number
  title: number
  title_se: number
  rank_dist?: number[]
}

export interface F1Run {
  run_id: string
  season: number
  standings_round: number
  draws: number
  seed: number
  drivers: F1Driver[]
  constructors: F1Constructor[]
  remaining_races: { round: number; name: string; sprint: boolean; start: string; win_probabilities: Record<string, number> }[]
  entry_list: { round: number; drivers: number; note: string }
  diagnostics: Record<string, any>
  global_state_version: number
  rating_params: Record<string, number>
  status?: string
}

const season = (cid: string) => `/competitions/${cid}/seasons/current`

/** right after an API restart a league's season is still being built: keep retrying instead of failing */
const warming = (msg: string) => /no season run yet|not in season run|503/.test(msg)
const warmRetry = { retry: (n: number, e: Error) => (warming(e.message) ? n < 40 : n < 1), retryDelay: (n: number) => Math.min(1500 + n * 500, 4000) }

export const useStatus = (cid: string) =>
  useQuery({ queryKey: ['status', cid], queryFn: () => getJSON<SeasonStatus>(season(cid)), refetchInterval: 20_000 })

export const useSeason = (cid: string, enabled = true) =>
  useQuery({ queryKey: ['season', cid], queryFn: () => getJSON<SeasonRun>(`${season(cid)}/season-forecast`), refetchInterval: 30_000, enabled, ...warmRetry })

export const useFastSeason = (cid: string) =>
  useQuery({ queryKey: ['season-fast', cid], queryFn: () => getJSON<SeasonRun>(`${season(cid)}/season-forecast?mode=fast`), retry: 1 })

export const useF1 = () =>
  useQuery({ queryKey: ['season', 'f1'], queryFn: () => getJSON<F1Run>(`${season('f1')}/season-forecast`), refetchInterval: 60_000, ...warmRetry })

export const useBoard = (cid: string, team?: string) =>
  useQuery({
    queryKey: ['board', cid, team ?? ''],
    queryFn: () => getJSON<{ events: BoardRow[]; count: number; global_state_version: number }>(`${season(cid)}/forecast-board${team ? `?team=${team}` : ''}`),
    refetchInterval: 20_000,
  })

export const useStandings = (cid: string) =>
  useQuery({ queryKey: ['standings', cid], queryFn: () => getJSON<{ rows: StandingRow[]; as_of: string }>(`${season(cid)}/standings`), refetchInterval: 30_000 })

export const useUpdates = (cid: string) =>
  useQuery({ queryKey: ['updates', cid], queryFn: () => getJSON<WorldUpdate[]>(`${season(cid)}/updates`), refetchInterval: 20_000 })

export const useMeta = (cid: string) =>
  useQuery({ queryKey: ['meta', cid], queryFn: () => getJSON<Record<string, TeamMeta>>(`/competitions/${cid}/teams/meta`), staleTime: Infinity, enabled: cid !== 'f1' })

export const useTeam = (cid: string, teamId: string) =>
  useQuery({ queryKey: ['team', cid, teamId], queryFn: () => getJSON<TeamPage>(`/entities/team/${cid}/${teamId}`), refetchInterval: 20_000, ...warmRetry })

export const useAvailability = (cid: string) =>
  useQuery({
    queryKey: ['availability', cid],
    queryFn: () => getJSON<{ teams: AvailabilityTeam[]; fetched_at: string; impact: Record<string, any> }>(`/availability?league=${cid}`),
    refetchInterval: 120_000, retry: 0,
  })

export const useNews = (cid: string) =>
  useQuery({ queryKey: ['news', cid], queryFn: () => getJSON<NewsSignal[]>(`/news?league=${cid}`), refetchInterval: 120_000, retry: 0 })

export const useSeasonSummary = () =>
  useQuery({ queryKey: ['research', 'season-summary'], queryFn: () => getJSON<{ summary: any[] }>('/research/season-summary'), staleTime: Infinity, retry: 0 })

export const useRolling = () =>
  useQuery({ queryKey: ['research', 'rolling'], queryFn: () => getJSON<any[]>('/research/rolling'), staleTime: Infinity, retry: 0 })

export const usePlayerImpact = () =>
  useQuery({ queryKey: ['research', 'player-impact'], queryFn: () => getJSON<any[]>('/research/player-impact'), staleTime: Infinity, retry: 0 })
