from __future__ import annotations

'''Optional Fetch.ai/uAgents bridge.

Install sportsworld[fetch]. The canonical Observation contract remains in
SportsWorld; uAgents provides autonomous transport/orchestration.
'''
import os


def build_fetch_agent(engine,event_id:str):
    try:
        from uagents import Agent, Context, Model
    except ImportError as exc:
        raise RuntimeError('Install sportsworld[fetch] to enable Fetch.ai uAgents') from exc

    from sportsworld.schemas import Observation

    class ObservationMessage(Model):
        json_payload:str

    agent=Agent(name=f'sportsworld-{event_id}',seed=os.getenv('FETCH_AGENT_SEED','sportsworld-demo-seed'))

    @agent.on_message(model=ObservationMessage)
    async def handle(ctx:Context,sender:str,msg:ObservationMessage):
        obs=Observation.model_validate_json(msg.json_payload)
        if obs.event_id!=event_id:
            ctx.logger.warning('event id mismatch'); return
        engine.ingest(obs); ctx.logger.info(f'ingested {obs.kind} from {sender}')

    return agent,ObservationMessage
