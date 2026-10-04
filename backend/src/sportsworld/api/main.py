from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sportsworld import __version__
from sportsworld.config import get_settings
from sportsworld.data.sources import DEFAULT_SOURCES
from sportsworld.demo.seed import seed_demo_events
from sportsworld.ingest.leagues import LEAGUES
from sportsworld.ingest.tracker import TrackerService
from sportsworld.season.f1_season import fetch_f1_season_state
from sportsworld.season.rules import POSTSEASON
from sportsworld.season.service import SeasonService
from datetime import datetime, timezone
from . import season_routes
from sportsworld.llm.explanation import deterministic_explanation
from sportsworld.schemas import ContextSignal, CounterfactualRequest, EntityMetric, EntityProfile, EventCreate, Observation, ScenarioParseRequest, Sport
from .context import build_context
from .security import FixedWindowRateLimiter

settings=get_settings(); ctx=build_context(settings); expensive_limiter=FixedWindowRateLimiter(limit=20,window_seconds=60)

tracker:TrackerService|None=None
season_service:SeasonService|None=None

def _real_data_root()->Path:
    root=Path(settings.real_data_dir)
    return root if root.is_absolute() else Path(__file__).resolve().parents[4]/'data'/'real'

@asynccontextmanager
async def lifespan(app:FastAPI):
    global tracker
    ctx.hub.bind_loop()
    if settings.is_demo:
        try: seed_demo_events(ctx)
        except Exception as exc: print('demo seed warning:',exc)
    global season_service
    leagues=[x.strip() for x in settings.tracker_leagues.split(',') if x.strip()] or None
    if settings.tracker_enabled:
        tracker=TrackerService(ctx,_real_data_root(),leagues,schedule_interval=settings.tracker_schedule_interval,live_interval=settings.tracker_live_interval,publish=ctx.hub.publish_sync,openf1_token=settings.openf1_token)
        tracker.start()
    if settings.season_engine:
        replay_at=datetime.fromisoformat(settings.season_as_of.replace('Z','+00:00')) if settings.season_as_of else None
        season_service=SeasonService(_real_data_root(),ctx.registry,trackers=tracker.trackers if tracker else {},publish=ctx.hub.publish_sync,draws=settings.season_sim_draws,as_of=replay_at)
        season_routes.bind(season_service,expensive_limiter.dependency)
        if tracker:
            for t in tracker.trackers.values():
                t.on_final=season_service.invalidate
                if hasattr(t,'on_live'): t.on_live=season_service.on_live
        season_leagues=[l for l in (leagues or list(LEAGUES)) if l in POSTSEASON or l in ('f1','wnba')]
        if 'f1' in season_leagues:
            try: await fetch_f1_season_state(datetime.now(timezone.utc).year,_real_data_root())
            except Exception as exc: print('f1 season state fetch failed (using cache):',exc)
        from sportsworld.ingest.availability import AvailabilityService
        avail=AvailabilityService(season_leagues,on_change=season_service.on_availability)
        season_service.availability=avail
        if tracker:
            for lid,t in tracker.trackers.items():
                if lid in avail.books: t.availability=avail.books[lid]
        async def _avail_loop():
            while True:
                try: await avail.refresh_all()
                except Exception as exc: print('availability refresh failed:',exc)
                await asyncio.sleep(600)
        app.state.avail_task=asyncio.create_task(_avail_loop())
        from sportsworld.ingest.news import NewsService
        from sportsworld.llm.client import LLMClient
        def _teams(lg):
            run=season_service.state(lg).run or {}
            return [{"team_id":t["team_id"],"name":t["name"],"abbreviation":t.get("abbreviation")} for t in run.get("teams",[])]
        def _report(lg):
            b=avail.books.get(lg); return b.report if b else None
        def _on_signal(lg,recs):
            st=season_service.state(lg)
            b=avail.books.get(lg)
            if b and any([b.add_news(r) for r in recs]):  # grounded statuses (e.g. conference availability reports) feed the report
                changed=b.recompute()
                if changed: season_service.on_availability(lg,changed)
            for r in recs:
                flag=' · SOURCE DISAGREEMENT with official report' if r.get('disagreement') else ''
                st.feed.appendleft({"at":r["known_to_model_time"],"global_state_version":st.global_state_version,
                                    "reason":f"News ({r['category'].replace('_',' ')}): {r.get('player') or r.get('team')}: \"{r['evidence_span'][:120]}\"{flag} [state-only evidence]",
                                    "teams":[r["team_id"]] if r.get("team_id") else [],"news":r})
        news=NewsService(season_leagues,_real_data_root(),LLMClient(settings),_teams,_report,_on_signal)
        app.state.news=news
        for lg,nb in news.books.items():  # statuses already extracted survive a restart
            b=avail.books.get(lg)
            if b and any([b.add_news(r) for r in nb.signals]):
                b.recompute()
        async def _news_loop():
            await asyncio.sleep(30)
            while True:
                try: await news.refresh()
                except Exception as exc: print('news refresh failed:',exc)
                await asyncio.sleep(300)
        app.state.news_task=asyncio.create_task(_news_loop())
        season_service.start(season_leagues)
        if settings.spacetimedb_url and settings.spacetimedb_token:
            from sportsworld.live.spacetime_publisher import SpacetimePublisher
            pub=SpacetimePublisher(settings.spacetimedb_url,settings.spacetimedb_database,settings.spacetimedb_token,season_service)
            app.state.spacetime=pub
            app.state.spacetime_task=asyncio.create_task(pub.run())
        if settings.database_url:
            from sportsworld.live.neon_archive import NeonArchive
            arch=NeonArchive(settings.database_url,season_service)
            app.state.neon=arch
            season_routes.bind_archive(arch)
            app.state.neon_task=asyncio.create_task(arch.run())
    yield
    if season_service: await season_service.stop()
    if tracker: await tracker.stop()

app=FastAPI(title='SportsWorld API',version=__version__,description='Point-in-time-valid cross-sport probabilistic forecasting engine',lifespan=lifespan)


@app.middleware("http")
async def _house_style(request, call_next):
    """Every JSON response leaves without em dashes (live ESPN / news / LLM text included)."""
    from starlette.responses import Response
    from sportsworld.text_style import no_em_dash_bytes
    resp = await call_next(request)
    if "application/json" not in resp.headers.get("content-type", ""):
        return resp
    body = b"".join([chunk async for chunk in resp.body_iterator])
    headers = {k: v for k, v in resp.headers.items() if k.lower() != "content-length"}
    return Response(no_em_dash_bytes(body), status_code=resp.status_code, headers=headers, media_type="application/json")

app.include_router(season_routes.router)
app.add_middleware(CORSMiddleware,allow_origins=[settings.frontend_origin,'http://127.0.0.1:5173'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])


def require_admin(authorization:str|None=Header(default=None)):
    if not settings.admin_api_token: return True
    token=(authorization or '').removeprefix('Bearer ').strip()
    if token!=settings.admin_api_token: raise HTTPException(401,'admin token required')
    return True

@app.get('/news')
def news_signals(league:str|None=None,limit:int=100):
    news=getattr(app.state,'news',None)
    if not news: raise HTTPException(503,'news service not running')
    if not league: return news.status()
    b=news.books.get(league)
    if not b: raise HTTPException(404,'no news for league')
    return [s for s in reversed(b.signals) if s.get('category')!='none'][:limit]

_FEED: dict = {}

@app.get('/competitions/{cid}/news-feed')
def news_feed(cid: str, limit: int = 60):
    """ESPN's latest articles for a league with ESPN's own team tags, plus any model signal grounded in the article
    whose team ESPN itself tagged (signals are display-only state; they never move a forecast on their own)."""
    import time as _t
    import httpx as _h
    from sportsworld.ingest.espn import BASE
    from sportsworld.ingest.leagues import LEAGUES as _L
    if cid not in _L or not _L[cid].espn_path: raise HTTPException(404, 'unknown league')
    hit = _FEED.get(cid)
    if not hit or _t.time() - hit[0] > 120:
        r = _h.get(f"{BASE}/{_L[cid].espn_path}/news", params={'limit': 50}, timeout=20, headers={'User-Agent': 'SportsWorld/1.3'})
        r.raise_for_status()
        arts = []
        for a in r.json().get('articles', []):
            cats = a.get('categories', [])
            tids = sorted({str(c.get('teamId') or (c.get('team') or {}).get('id')) for c in cats if c.get('type') == 'team'} - {'None'})
            arts.append({'article_id': str(a.get('id') or a.get('dataSourceIdentifier') or a.get('headline')), 'type': a.get('type'),
                         'headline': a.get('headline') or '', 'description': a.get('description') or '', 'published': a.get('published'),
                         'url': ((a.get('links') or {}).get('web') or {}).get('href'), 'image': ((a.get('images') or [{}])[0] or {}).get('url'),
                         'team_ids': tids, 'premium': bool(a.get('premium'))})
        hit = _FEED[cid] = (_t.time(), arts)
    news = getattr(app.state, 'news', None)
    sigs = {}
    if news and news.books.get(cid):
        for sg in news.books[cid].signals:
            sigs.setdefault(sg['article_id'], []).append(sg)
    # other outlets (Yahoo Sports, CBS Sports, On3 league and team feeds), kept fresh by the news service
    others = [{k: v for k, v in a.items() if k != 'body'} for a in (news.hub.latest(cid, 120) if news else [])]
    seen_urls = {a['url'] for a in hit[1]}
    merged = [{**a, 'source': 'ESPN'} for a in hit[1]] + [a for a in others if a['url'] not in seen_urls]
    merged.sort(key=lambda a: a.get('published') or '', reverse=True)
    _seen_h = set(); _dedup = []
    for a in merged:  # the same story arrives from several feeds (On3 league + team feeds, Google News copies)
        k = ' '.join(''.join(ch for ch in a['headline'].lower() if ch.isalnum() or ch == ' ').split())
        if k in _seen_h: continue
        _seen_h.add(k); _dedup.append(a)
    merged = _dedup
    out = []
    for a in merged[:limit]:
        espn_tagged = a['source'] == 'ESPN' and a['team_ids']
        good = [{'category': sg['category'], 'team_id': sg['team_id'], 'team': sg['team'], 'player': sg.get('player'), 'status': sg.get('status'),
                 'evidence_span': sg['evidence_span'], 'disagreement': sg.get('disagreement'), 'known_to_model_time': sg.get('known_to_model_time')}
                for sg in sigs.get(a['article_id'], []) if sg.get('category') != 'none' and sg.get('team_id') and (not espn_tagged or sg['team_id'] in a['team_ids'])]
        out.append({**a, 'signals': good})
    from collections import Counter as _C
    return {'league': cid, 'articles': out, 'sources': dict(_C(a['source'] for a in merged)), 'fetched_at': hit[0]}

@app.get('/competitions/{cid}/injury-report')
def injury_report(cid: str):
    """Every listed player, every team: official injury report plus grounded reports from other outlets."""
    if not season_service or not season_service.availability: raise HTTPException(503,'availability service not running')
    av=season_service.availability
    if cid not in av.books: raise HTTPException(404,'no availability model for league')
    names={t['team_id']:t['name'] for t in ((season_service.state(cid).run or {}).get('teams') or [])}
    b=av.books[cid]
    teams=av.full_report(cid,names)
    return {'league':cid,'teams':teams,'players':sum(len(t['players']) for t in teams),'fetched_at':b.fetched_at.isoformat() if b.fetched_at else None,
            'impact':{k:{'points':v.get('points'),'se':v.get('se'),'significant':v.get('significant')} for k,v in b.impact.get('by_position',{}).items()},
            'sources':'ESPN injury report; grounded availability from On3, Yahoo Sports and CBS Sports articles (verbatim quote required)'}

@app.get('/llm/health')
def llm_health():
    from sportsworld.llm.client import LLMClient
    return LLMClient(settings).health()

@app.get('/availability')
def availability(league:str|None=None):
    if not season_service or not season_service.availability: raise HTTPException(503,'availability service not running')
    av=season_service.availability
    if league:
        b=av.books.get(league)
        if not b: raise HTTPException(404,'no availability model for league')
        names={t['team_id']:t['name'] for t in ((season_service.state(league).run or {}).get('teams') or [])}
        teams=[{**d,'team':names.get(d['team_id'],d['team_id'])} for d in b.deltas.values() if d['absences']]
        return {'league':league,'impact':{k:b.impact.get(k) for k in ('model_version','by_position','n_games','definition')},'fetched_at':b.fetched_at,
                'teams':sorted(teams,key=lambda d:d['delta_points'])}
    return av.status()

@app.get('/health')
def health():
    season={lg:{'global_state_version':st.global_state_version,'run':(st.run or {}).get('run_id'),'status':'recomputing' if st.computing else ('stale' if st.dirty else 'fresh'),'board_events':len(st.board),'last_error':st.last_error} for lg,st in season_service.states.items()} if season_service else None
    news=getattr(app.state,'news',None)
    return {'status':'ok','version':__version__,'environment':settings.sportsworld_env,'store':settings.store_backend,
            'replay_as_of':settings.season_as_of,'season_engine':season,
            'availability':season_service.availability.status() if season_service and season_service.availability else None,
            'news':news.status() if news else None,
            'spacetime':app.state.spacetime.status() if getattr(app.state,'spacetime',None) else None,
            'neon':app.state.neon.status() if getattr(app.state,'neon',None) else None,
            'tracker':{lid:t.status() for lid,t in tracker.trackers.items()} if tracker else None,'dependencies':{'llm':bool(settings.llm_api_key),'elevenlabs':ctx.voice.enabled,'spacetimedb':bool(settings.spacetimedb_url),'postgres':bool(settings.database_url)}}

@app.get('/sports')
def sports():
    return [{'sport':s.value,'schema_version':ctx.engine.adapters[s].schema_version,'observation_kinds':sorted(ctx.engine.adapters[s].supported_observation_kinds() | ctx.context_engine.SHARED_OBSERVATION_KINDS),'context_layer':'historical_memory+latent_state+matchup+public_context'} for s in Sport]

@app.get('/sources')
def sources(): return [x.__dict__ for x in DEFAULT_SOURCES]

@app.get('/events')
def list_events(sport:Sport|None=None,status:str|None=None,competition:str|None=None):
    events=ctx.store.list_events()
    if sport: events=[e for e in events if e.sport==sport]
    if status: events=[e for e in events if e.status==status]
    if competition: events=[e for e in events if e.competition==competition]
    return events

# ---------------------------------------------------------------------------
# Leagues: every team, every game
# ---------------------------------------------------------------------------
def _league(league_id:str):
    if league_id not in LEAGUES: raise HTTPException(404,'unknown league')
    return LEAGUES[league_id]

@app.get('/leagues')
def leagues():
    out=[]
    for lid,spec in LEAGUES.items():
        card=ctx.registry.league_card(lid)
        out.append({'league':lid,'name':spec.display_name,'sport':spec.sport.value,'tracked':bool(tracker and lid in tracker.trackers),
                    'status':tracker.trackers[lid].status() if tracker and lid in tracker.trackers else None,
                    'model':{'model_version':card.model_version,'data_mode':card.data_mode,'metrics':card.metrics} if card else None})
    return out

@app.get('/leagues/{league_id}/board')
def league_board(league_id:str,status:str|None=None):
    _league(league_id)
    if tracker and league_id in tracker.trackers: rows=tracker.trackers[league_id].board()
    else:
        rows=[]
        for e in ctx.store.list_events():
            if e.competition!=league_id: continue
            st=ctx.store.get_state(e.event_id).features; f=ctx.engine.latest_forecast(e.event_id); names=e.metadata.get('display_outcomes',{})
            rows.append({'event_id':e.event_id,'league':league_id,'status':e.status,'start_time':e.start_time.isoformat(),'home':{'name':names.get('home'),'score':st.get('home_score',0)},'away':{'name':names.get('away'),'score':st.get('away_score',0)},'probabilities':f.probabilities,'uncertainty':f.uncertainty.total,'model_version':f.model_version})
    if status: rows=[r for r in rows if r['status']==status]
    return rows

@app.get('/leagues/{league_id}/teams')
def league_teams(league_id:str):
    _league(league_id)
    if not tracker or league_id not in tracker.trackers: raise HTTPException(503,'league tracker not running (set TRACKER_ENABLED=true)')
    return tracker.trackers[league_id].book.table()

@app.get('/leagues/{league_id}/backtest')
def league_backtest(league_id:str):
    _league(league_id)
    path=Path(__file__).resolve().parents[4]/'data'/'fixtures'/'backtests'/f'{league_id}_real.json'
    if not path.exists(): raise HTTPException(404,'no real-data backtest for this league; run scripts/train_real.py')
    return json.loads(path.read_text())

@app.get('/leagues/{league_id}/model')
def league_model(league_id:str):
    _league(league_id); card=ctx.registry.league_card(league_id)
    if not card: raise HTTPException(404,'no league model registered')
    return card

@app.post('/leagues/sync',dependencies=[Depends(require_admin)])
async def league_sync():
    if not tracker: raise HTTPException(503,'league tracker not running (set TRACKER_ENABLED=true)')
    await tracker.sync_all(); return [t.status() for t in tracker.trackers.values()]

@app.post('/events',dependencies=[Depends(require_admin)])
def create_event(req:EventCreate):
    try: return ctx.engine.create_event(req,status='replay' if settings.is_demo else 'upcoming')
    except ValueError as exc: raise HTTPException(409,str(exc))

@app.get('/events/{event_id}')
def get_event(event_id:str):
    try:
        event=ctx.store.get_event(event_id); state=ctx.store.get_state(event_id); return {'event':event,'state':state,'forecast':ctx.engine.latest_forecast(event_id)}
    except KeyError: raise HTTPException(404,'event not found')

@app.post('/events/{event_id}/observations',dependencies=[Depends(require_admin)])
def ingest(event_id:str,obs:Observation,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key')):
    if event_id!=obs.event_id: raise HTTPException(400,'event path/id mismatch')
    if idempotency_key:
        obs=obs.model_copy(update={'dedupe_key':f'api:{idempotency_key}'})
    try:return ctx.engine.ingest(obs)
    except KeyError:raise HTTPException(404,'event not found')
    except ValueError as exc:raise HTTPException(409,str(exc))

@app.post('/events/{event_id}/observations/batch',dependencies=[Depends(require_admin)])
def ingest_batch(event_id:str,observations:list[Observation]):
    results=[]
    for obs in observations:
        if obs.event_id!=event_id: raise HTTPException(400,'event path/id mismatch')
        results.append(ctx.engine.ingest(obs))
    return {'count':len(results),'forecast':results[-1] if results else ctx.engine.latest_forecast(event_id)}

@app.get('/events/{event_id}/observations')
def observations(event_id:str):
    try:return ctx.store.list_observations(event_id)
    except KeyError:raise HTTPException(404,'event not found')

@app.get('/events/{event_id}/context')
def event_context(event_id:str, state_version:int|None=None):
    try:
        if state_version is not None:
            return ctx.store.get_context_snapshot(event_id,state_version)
        try:
            return ctx.store.get_context_snapshot(event_id)
        except KeyError:
            state=ctx.store.get_state(event_id); _,snapshot=ctx.context_engine.enrich_state(state,persist_snapshot=True); return snapshot
    except KeyError:
        raise HTTPException(404,'event/context not found')

@app.get('/events/{event_id}/context/history')
def event_context_history(event_id:str):
    try:
        ctx.store.get_event(event_id)
        return ctx.store.list_context_snapshots(event_id)
    except KeyError:
        raise HTTPException(404,'event not found')

@app.get('/entities')
def entities(sport:Sport|None=None,team_id:str|None=None):
    return ctx.store.list_entity_profiles(sport=sport,team_id=team_id)

@app.get('/entities/{entity_id}')
def entity_detail(entity_id:str,as_of:str|None=None):
    from datetime import datetime, timezone
    try:
        profile=ctx.store.get_entity_profile(entity_id)
        cutoff=datetime.fromisoformat(as_of.replace('Z','+00:00')) if as_of else datetime.now(timezone.utc)
        if cutoff.tzinfo is None: cutoff=cutoff.replace(tzinfo=timezone.utc)
        metrics=ctx.store.list_entity_metrics(entity_id,cutoff)
        latent=ctx.context_engine.estimate_entity_state(profile,cutoff)
        return {'profile':profile,'latent_state':latent,'metrics':metrics}
    except KeyError:
        raise HTTPException(404,'entity not found')

@app.post('/entities',dependencies=[Depends(require_admin)])
def upsert_entity(profile:EntityProfile):
    ctx.store.upsert_entity_profile(profile); return profile

@app.post('/entities/{entity_id}/metrics',dependencies=[Depends(require_admin)])
def append_entity_metric(entity_id:str,metric:EntityMetric):
    if entity_id!=metric.entity_id: raise HTTPException(400,'entity path/id mismatch')
    inserted=ctx.store.append_entity_metric(metric); return {'inserted':inserted,'metric':metric}

@app.get('/events/{event_id}/context/signals')
def context_signals(event_id:str):
    return ctx.store.list_context_signals(event_id)

@app.get('/events/{event_id}/forecast')
def forecast(event_id:str):
    try:return ctx.engine.latest_forecast(event_id)
    except KeyError:raise HTTPException(404,'event not found')

@app.get('/events/{event_id}/forecasts')
def forecast_history(event_id:str): return ctx.store.list_forecasts(event_id)

@app.post('/events/{event_id}/counterfactuals',dependencies=[Depends(expensive_limiter.dependency)])
def counterfactual(event_id:str,req:CounterfactualRequest):
    if event_id!=req.base_event_id: raise HTTPException(400,'event path/id mismatch')
    try:base=ctx.store.get_state(event_id,req.base_state_version); result=ctx.simulator.run(base,req,settings.replay_seed); ctx.store.save_counterfactual(result); return result
    except KeyError:raise HTTPException(404,'event/state version not found')
    except ValueError as exc:raise HTTPException(422,str(exc))

@app.post('/events/{event_id}/scenario/parse',dependencies=[Depends(expensive_limiter.dependency)])
def parse_scenario(event_id:str,req:ScenarioParseRequest):
    try:return ctx.scenario_parser.parse(req.text,ctx.store.get_state(event_id))
    except KeyError:raise HTTPException(404,'event not found')

@app.get('/events/{event_id}/explanation')
def explanation(event_id:str):
    state=ctx.store.get_state(event_id); forecast=ctx.engine.latest_forecast(event_id); return {'text':deterministic_explanation(state,forecast)}

@app.post('/voice/narrate',dependencies=[Depends(expensive_limiter.dependency)])
def narrate(payload:dict[str,str]):
    text=payload.get('text','')[:2000]
    try:return Response(content=ctx.voice.synthesize(text),media_type='audio/mpeg')
    except RuntimeError as exc:raise HTTPException(503,str(exc))

@app.get('/models/{sport}/active')
def model_card(sport:Sport):
    card=ctx.registry.card(sport)
    if card:return card
    return {'model_version':f'{sport.value}_adapter_baseline_v1','sport':sport,'algorithm':'adapter_baseline','feature_schema_version':ctx.engine.adapters[sport].schema_version,'calibration_version':'identity-v1','notes':['No learned artifact registered for this sport in the demo bundle.']}

@app.get('/backtests/{sport}')
def backtest_latest(sport:Sport):
    repo=Path(__file__).resolve().parents[4]; path=repo/'data'/'fixtures'/'backtests'/f'{sport.value}_demo.json'
    if not path.exists(): raise HTTPException(404,'no bundled backtest for this sport')
    return json.loads(path.read_text())

@app.get('/backtests/{sport}/{run_id}')
def backtest_run(sport:Sport,run_id:str):
    data=backtest_latest(sport)
    if data.get('run_id')!=run_id:raise HTTPException(404,'run not found')
    return data

@app.post('/demo/{event_id}/replay',dependencies=[Depends(require_admin)])
async def replay_control(event_id:str,payload:dict[str,Any]):
    try:
        if event_id not in ctx.replay.sessions:ctx.replay.load(event_id)
        action=payload.get('action','status')
        if action=='step':return await ctx.replay.step(event_id,int(payload.get('count',1)))
        if action=='play':ctx.replay.play(event_id,float(payload.get('speed',5)));return ctx.replay.status(event_id)
        if action=='pause':ctx.replay.pause(event_id);return ctx.replay.status(event_id)
        if action=='reset':return ctx.replay.reset(event_id)
        if action=='seek':
            target=max(0,int(payload.get('cursor',0)));ctx.replay.reset(event_id);return await ctx.replay.step(event_id,target)
        return ctx.replay.status(event_id)
    except (KeyError,FileNotFoundError):raise HTTPException(404,'replay/event not found')

@app.websocket('/ws/events/{event_id}')
async def ws_event(ws:WebSocket,event_id:str,last_seen_sequence:int=Query(default=0)):
    await ctx.hub.connect(event_id,ws,last_seen_sequence)
    try:
        while True:
            data=await ws.receive_text()
            if data=='ping':await ws.send_json({'type':'pong'})
    except WebSocketDisconnect:ctx.hub.disconnect(event_id,ws)


def run():
    import uvicorn
    uvicorn.run('sportsworld.api.main:app',host='0.0.0.0',port=8000,reload=False)
