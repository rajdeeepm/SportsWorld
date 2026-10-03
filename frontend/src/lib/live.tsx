import { useMemo, type ReactNode } from 'react'
import { SpacetimeDBProvider, useSpacetimeDB, useTable } from 'spacetimedb/react'
import { DbConnection, tables } from '../stdb'
import type { BoardRow } from './data'

/*
 * Live world state over SpacetimeDB. The engine publishes; every browser subscribes and receives the same
 * versioned state the moment it changes. When SpacetimeDB is unreachable the hooks return nothing and pages
 * keep working on the REST API alone.
 */

const URI = (import.meta as any).env?.VITE_SPACETIME_URI ?? 'ws://127.0.0.1:3010'
const DB = (import.meta as any).env?.VITE_SPACETIME_DB ?? 'sportsworld'

const builder = DbConnection.builder().withUri(URI).withDatabaseName(DB)

export function LiveProvider({ children }: { children: ReactNode }) {
  return <SpacetimeDBProvider connectionBuilder={builder}>{children}</SpacetimeDBProvider>
}

export function useLiveStatus() {
  const s = useSpacetimeDB()
  const [viewers] = useTable(tables.viewer)
  return { connected: s.isActive, error: s.connectionError?.message, viewers: viewers.length }
}

export interface LiveGame {
  eventId: string
  state: string
  homeScore: number
  awayScore: number
  period: number
  clockSeconds: number
  pHome: number
  leverageHome: number
  leverageAway: number
  stateVersion: bigint
}

export function useLiveGames(league: string) {
  const [rows, ready] = useTable(tables.game.where((r) => r.league.eq(league)))
  return useMemo(() => {
    const m = new Map<string, LiveGame>()
    for (const r of rows) m.set(r.eventId, r as LiveGame)
    return { map: m, ready }
  }, [rows, ready])
}

/** overlay SpacetimeDB's pushed state onto REST rows: scores, clock and probability arrive the instant they change */
export function mergeLive(rows: BoardRow[], live: Map<string, LiveGame>): BoardRow[] {
  if (!live.size) return rows
  return rows.map((r) => {
    const l = live.get(r.event_id)
    if (!l) return r
    return {
      ...r, state: l.state as BoardRow['state'], home_score: l.homeScore, away_score: l.awayScore, period: l.period,
      clock_seconds: l.clockSeconds, p_home: l.pHome, leverage_home: l.leverageHome, leverage_away: l.leverageAway,
    }
  })
}

export function useLiveCompetition(league: string) {
  const [rows] = useTable(tables.competition.where((r) => r.league.eq(league)))
  return rows[0]
}

export function useWinProbHistory(eventId: string) {
  const [rows] = useTable(tables.winProb.where((r) => r.eventId.eq(eventId)))
  return useMemo(() => rows.map((r) => ({ at: r.at, p_home: r.pHome })).sort((a, b) => a.at.localeCompare(b.at)), [rows])
}

export function useLiveUpdates(league: string) {
  const [rows] = useTable(tables.worldUpdate.where((r) => r.league.eq(league)))
  return useMemo(() => rows.slice().sort((a, b) => Number(b.id - a.id)), [rows])
}
