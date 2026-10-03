"""Create the Agentverse mailbox for SportsWorld Analyst without the browser inspector.

Needs AGENTVERSE_API_KEY (agentverse.ai -> Profile -> API Keys) and SPORTSWORLD_AGENT_SEED in .env.
Proves ownership of the agent address with a signed challenge, then registers it as a mailbox agent.

    python agents/sportsworld_analyst/connect_mailbox.py
"""
from __future__ import annotations

import asyncio

from uagents.crypto import Identity
from uagents.mailbox import register_in_agentverse
from uagents_core.config import AgentverseConfig
from uagents_core.contrib.protocols.chat import chat_protocol_spec
from uagents_core.registration import AgentverseConnectRequest, RegistrationRequest
from uagents_core.types import AgentEndpoint
from uagents import Protocol

from agent_env import env


async def main() -> None:
    key, seed = env("AGENTVERSE_API_KEY"), env("SPORTSWORLD_AGENT_SEED")
    if not key or not seed:
        raise SystemExit("AGENTVERSE_API_KEY and SPORTSWORLD_AGENT_SEED must be set in .env")
    identity = Identity.from_seed(seed, 0)
    av = AgentverseConfig()
    proto = Protocol(spec=chat_protocol_spec).digest
    details = RegistrationRequest(
        address=identity.address, name="sportsworld-analyst", agent_type="mailbox",
        endpoints=[AgentEndpoint(url=av.mailbox_endpoint, weight=1)], protocols=[proto],
    )
    res = await register_in_agentverse(AgentverseConnectRequest(user_token=key, agent_type="mailbox"), identity, "agent", av, details)
    print("address:", identity.address)
    print("registered:", res.success, res.detail or "")


if __name__ == "__main__":
    asyncio.run(main())
