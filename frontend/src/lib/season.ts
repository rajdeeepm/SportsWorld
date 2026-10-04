export interface SeasonTeam{team_id:string;name:string;abbreviation?:string|null;conference?:string|null;division?:string|null;rating:number;rating_sd:number;games:number;expected_wins:number;wins_sd:number;wins_p05:number;wins_p95:number;win_hist:number[];expected_points?:number;seed_dist?:number[];[k:string]:any}
export interface SeasonRun{run_id:string;league:string;season:number;as_of:string;mode:string;draws:number;seed:number;simulator_version:string;global_state_version:number;event_model_version?:string;teams:SeasonTeam[];diagnostics:Record<string,any>;status?:string}
export interface F1Driver{driver_id:string;code:string;name:string;constructor_id:string;points_now:number;wins_now:number;rating:number;rating_sd:number;reliability:number;expected_points:number;points_p05:number;points_p95:number;expected_wins:number;title:number;title_se:number;rank_dist:number[]}
export interface F1Constructor{constructor_id:string;name:string;points_now:number;car_rating:number;reliability:number;expected_points:number;points_p05:number;points_p95:number;title:number;title_se:number}
export interface F1Run{run_id:string;season:number;standings_round:number;mode:string;draws:number;drivers:F1Driver[];constructors:F1Constructor[];remaining_races:{round:number;name:string;sprint:boolean;start:string;win_probabilities:Record<string,number>}[];diagnostics:Record<string,any>;global_state_version:number;status?:string}
export interface BoardRow{event_id:string;start_time:string;week?:number|null;state:string;home_id:string;away_id:string;home:string;away:string;home_abbr?:string|null;away_abbr?:string|null;neutral_site:boolean;p_home:number|null;interval_90:[number,number]|null;model_version?:string|null;global_state_version:number;as_of:string;freshness:string;p_home_season_sim?:number|null}
export interface StandingRow{team_id:string;name:string;abbreviation?:string|null;conference?:string|null;division?:string|null;wins:number;losses:number;ties:number;ot_losses:number;games:number;conf_record:string;point_diff:number;points?:number|null;official_matches?:boolean|null}
export interface WorldUpdate{at:string;global_state_version:number;reason:string;teams:string[];event_id?:string;rating_after?:Record<string,number>}
export const MILESTONES:Record<string,[string,string][]>={
 nfl:[['playoffs','Playoffs'],['division_title','Division'],['first_round_bye','Bye'],['conference_title','Conf. title'],['champion','Super Bowl']],
 nba:[['playoffs','Playoffs'],['play_in','Play-in'],['conference_title','Conf. title'],['champion','Title']],
 nhl:[['playoffs','Playoffs'],['division_title','Top-3 div'],['conference_title','Conf. title'],['champion','Cup']],
 'college-football':[['conference_title_game','Conf. game'],['conference_champion','Conf. champ'],['playoffs','CFP'],['first_round_bye','CFP bye'],['semifinal','Semis'],['champion','Title']],
 'mens-college-basketball':[['tournament','NCAA field'],['sweet_16','Sweet 16'],['final_four','Final Four'],['champion','Title']],
 'womens-college-basketball':[['tournament','NCAA field'],['sweet_16','Sweet 16'],['final_four','Final Four'],['champion','Title']],
 wnba:[]};
export const pct=(p?:number|null,d=1)=>p==null?'-':`${(p*100).toFixed(d)}%`;
