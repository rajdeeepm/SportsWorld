import asyncio
from datetime import datetime,timezone
from sportsworld.schemas import EventCreate

def test_replay_reset_and_step(ctx,tmp_path):
    # existing fixture can be loaded only for its matching event, so this test
    # exercises reset semantics on a synthetic in-memory event.
    original=ctx.store.get_state('test-game',0).model_dump()
    from sportsworld.schemas import Observation
    o=Observation(event_id='test-game',sport='football',kind='weather',payload={'severity':.5},source_id='r',source_type='replay',known_to_model_time=datetime(2026,1,1,0,2,tzinfo=timezone.utc),sequence_no=1)
    path=tmp_path/'test-game.jsonl';path.write_text(o.model_dump_json()+'\n');ctx.replay.replay_dir=tmp_path;ctx.replay.load('test-game')
    asyncio.run(ctx.replay.step('test-game'));assert ctx.store.get_state('test-game').state_version==1
    ctx.replay.reset('test-game');assert ctx.store.get_state('test-game').model_dump()==original
