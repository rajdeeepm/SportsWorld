"""SportsWorld Analyst: a Fetch.ai uAgent (Agent Chat Protocol) on Agentverse, discoverable through ASI:One.

Runs next to the SportsWorld engine with an Agentverse mailbox, so ASI:One conversations reach it without a
public endpoint. Each message is routed to an action on the live engine (see analyst.py).

    python agents/sportsworld_analyst/agent.py
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)

from agent_env import env
from analyst import Engine, answer

HERE = Path(__file__).resolve().parent
SEED = env("SPORTSWORLD_AGENT_SEED")
if not SEED:
    raise SystemExit("SPORTSWORLD_AGENT_SEED is not set (.env)")

# Python 3.12+ no longer creates a default event loop; uAgents expects one
_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)

agent = Agent(
    name="sportsworld-analyst",
    loop=_loop,
    seed=SEED,
    port=8020,
    mailbox=True,
    readme_path=str(HERE / "README.md"),
    description=("Live sports world model for every NFL, college football, NBA, NHL, college basketball and F1 season: "
                 "playoff and title odds, what-if simulations, games that matter, live win probabilities."),
    publish_agent_details=True,
)
engine = Engine()
chat = Protocol(spec=chat_protocol_spec)


def _reply(text: str) -> ChatMessage:
    return ChatMessage(timestamp=datetime.now(timezone.utc), msg_id=uuid4(), content=[TextContent(type="text", text=text)])


@chat.on_message(ChatMessage)
async def handle(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.now(timezone.utc), acknowledged_msg_id=msg.msg_id))
    text = " ".join(c.text for c in msg.content if isinstance(c, TextContent)).strip()
    if any(isinstance(c, StartSessionContent) for c in msg.content) and not text:
        text = "help"
    if not text:
        return
    ctx.logger.info(f"question from {sender[:16]}…: {text!r}")
    try:
        out = await asyncio.get_running_loop().run_in_executor(None, answer, text, engine)
    except Exception as exc:  # never leave a conversation hanging
        out = f"Something went wrong while running the SportsWorld engine ({exc.__class__.__name__}). Please try again."
    await ctx.send(sender, _reply(out))
    if any(isinstance(c, EndSessionContent) for c in msg.content):
        ctx.logger.info("session ended")


@chat.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


agent.include(chat, publish_manifest=True)

if __name__ == "__main__":
    agent.run()
