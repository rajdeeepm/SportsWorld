export type LeagueId = 'f1' | 'nfl' | 'college-football' | 'nba' | 'mens-college-basketball' | 'nhl' | 'mens-college-hockey'

export interface Milestone {
  key: string
  label: string
  short: string
}

export interface LeagueConfig {
  id: LeagueId
  tab: string
  name: string
  sport: 'football' | 'basketball' | 'hockey' | 'f1'
  seasonLabel: string
  unit: string
  /** milestones in ascending order of difficulty; the last one is the title */
  milestones: Milestone[]
  /** headline milestone used for "playoff" style outlooks and leverage */
  qualify: string
  titleName: string
  conferenceWord: string
  college: boolean
  logo?: string
}

const L = (x: LeagueConfig) => x

export const LEAGUES: LeagueConfig[] = [
  L({
    id: 'f1', tab: 'F1', name: 'Formula 1', sport: 'f1', seasonLabel: '2026', unit: 'pts',
    milestones: [], qualify: 'title', titleName: 'World Championship', conferenceWord: '', college: false,
  }),
  L({
    id: 'nfl', tab: 'NFL', name: 'NFL', sport: 'football', seasonLabel: '2026', unit: 'pts',
    milestones: [
      { key: 'playoffs', label: 'Make playoffs', short: 'Playoffs' },
      { key: 'division_title', label: 'Win division', short: 'Division' },
      { key: 'first_round_bye', label: 'First-round bye', short: 'Bye' },
      { key: 'conference_title', label: 'Win conference', short: 'Conf.' },
      { key: 'champion', label: 'Win Super Bowl', short: 'Super Bowl' },
    ],
    qualify: 'playoffs', titleName: 'Super Bowl', conferenceWord: 'Conference', college: false,
    logo: 'https://a.espncdn.com/i/teamlogos/leagues/500/nfl.png',
  }),
  L({
    id: 'college-football', tab: 'CFB', name: 'College Football', sport: 'football', seasonLabel: '2026', unit: 'pts',
    milestones: [
      { key: 'conference_title_game', label: 'Reach conference title game', short: 'Conf. game' },
      { key: 'conference_champion', label: 'Win conference', short: 'Conf. champ' },
      { key: 'playoffs', label: 'Make College Football Playoff', short: 'CFP' },
      { key: 'first_round_bye', label: 'CFP first-round bye', short: 'Bye' },
      { key: 'semifinal', label: 'Reach CFP semifinal', short: 'Semis' },
      { key: 'champion', label: 'Win national title', short: 'Title' },
    ],
    qualify: 'playoffs', titleName: 'National Title', conferenceWord: 'Conference', college: true,
  }),
  L({
    id: 'nba', tab: 'NBA', name: 'NBA', sport: 'basketball', seasonLabel: '2026–27', unit: 'pts',
    milestones: [
      { key: 'play_in', label: 'Reach play-in or better', short: 'Play-in' },
      { key: 'playoffs', label: 'Make playoffs', short: 'Playoffs' },
      { key: 'conference_title', label: 'Win conference', short: 'Conf.' },
      { key: 'champion', label: 'Win NBA title', short: 'Title' },
    ],
    qualify: 'playoffs', titleName: 'NBA Title', conferenceWord: 'Conference', college: false,
    logo: 'https://a.espncdn.com/i/teamlogos/leagues/500/nba.png',
  }),
  L({
    id: 'mens-college-basketball', tab: 'CBB', name: 'College Basketball', sport: 'basketball', seasonLabel: '2026–27', unit: 'pts',
    milestones: [
      { key: 'tournament', label: 'Make NCAA tournament', short: 'NCAA' },
      { key: 'sweet_16', label: 'Reach Sweet 16', short: 'Sweet 16' },
      { key: 'final_four', label: 'Reach Final Four', short: 'Final Four' },
      { key: 'champion', label: 'Win national title', short: 'Title' },
    ],
    qualify: 'tournament', titleName: 'National Title', conferenceWord: 'Conference', college: true,
  }),
  L({
    id: 'nhl', tab: 'NHL', name: 'NHL', sport: 'hockey', seasonLabel: '2026–27', unit: 'goals',
    milestones: [
      { key: 'playoffs', label: 'Make playoffs', short: 'Playoffs' },
      { key: 'division_title', label: 'Top-3 in division', short: 'Div. top 3' },
      { key: 'conference_title', label: 'Win conference', short: 'Conf.' },
      { key: 'champion', label: 'Win Stanley Cup', short: 'Cup' },
    ],
    qualify: 'playoffs', titleName: 'Stanley Cup', conferenceWord: 'Conference', college: false,
    logo: 'https://a.espncdn.com/i/teamlogos/leagues/500/nhl.png',
  }),
  L({
    id: 'mens-college-hockey', tab: 'College Hockey', name: 'College Hockey', sport: 'hockey', seasonLabel: '2026–27', unit: 'goals',
    milestones: [
      { key: 'tournament', label: 'Make NCAA tournament', short: 'NCAA' },
      { key: 'champion', label: 'Win national title', short: 'Title' },
    ],
    qualify: 'tournament', titleName: 'National Title', conferenceWord: 'Conference', college: true,
  }),
]

export const LEAGUE_BY_ID = Object.fromEntries(LEAGUES.map((l) => [l.id, l])) as Record<LeagueId, LeagueConfig>

export function league(id: string | undefined): LeagueConfig {
  return LEAGUE_BY_ID[(id ?? 'college-football') as LeagueId] ?? LEAGUE_BY_ID['college-football']
}

export function title(l: LeagueConfig): Milestone {
  return l.milestones[l.milestones.length - 1] ?? { key: 'champion', label: 'Win title', short: 'Title' }
}

export function qualify(l: LeagueConfig): Milestone {
  return l.milestones.find((m) => m.key === l.qualify) ?? l.milestones[0]
}
