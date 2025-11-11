"""A2A messaging functionality for sending messages to agents."""

import json
import httpx
from typing import Optional
import logging
from uuid import uuid4

from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (
    AgentCard,
    SendMessageRequest,
    SendStreamingMessageRequest,
    MessageSendParams,
)
from . import discovery


logger = logging.getLogger(__name__)


EXTENDED_AGENT_CARD_PATH = "/.well-known/agent.json"


def _get_crd_url_for_agent(agent_url: str) -> Optional[str]:
    """
    Get the authoritative URL for an agent from the AgentCard CRD.
    This is necessary because agent developers don't always think about cluster
    dns assignment when they create their agent cards. The CRD on the other hand
    ensures that the actual in-cluster URL is added to the agent card. This makes
    it a better source of truth for connecting to agents in-cluster.

    Args:
        agent_url: The URL to match against AgentCard resources

    Returns:
        The URL from the CRD if found, None otherwise
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Get all agent cards
        agents, _ = discovery.get_agents_data(all_namespaces=True)
        logger.info(f"Looking for CRD URL for agent: {agent_url}")
        logger.info(f"Found {len(agents)} agent(s) in CRD")

        # Find the agent with matching URL
        for agent in agents:
            crd_url = agent.get("url")
            logger.info(f"Checking agent: {agent.get('agent_name')} with CRD URL: {crd_url}")
            if crd_url == agent_url:
                logger.info(f"Found matching agent in CRD: {agent.get('agent_name')}")
                return crd_url

        logger.warning(f"No matching agent found in CRD for URL: {agent_url}")
        return None
    except Exception as e:
        logger.error(f"Error looking up agent URL in CRD: {e}")
        return None


async def send_message_to_agent(
    agent_url: str,
    message: str,
    auth_token: Optional[str] = None,
    use_extended_card: bool = False,
) -> str:
    """
    Send a message to an A2A agent and get the response.

    Args:
        agent_url: The base URL of the agent (from AgentCard status.card.url)
        message: The message text to send
        auth_token: Optional OAuth token for authenticated requests
        use_extended_card: Whether to attempt fetching the extended agent card

    Returns:
        JSON response from the agent
    """
    async with httpx.AsyncClient(verify=False, timeout=120) as httpx_client:
        # Fetch agent card from HTTP endpoint
        resolver = A2ACardResolver(
            httpx_client=httpx_client,
            base_url=agent_url,
        )

        final_agent_card_to_use: AgentCard | None = None

        try:
            # Get the public agent card from HTTP
            public_card = await resolver.get_agent_card()
            final_agent_card_to_use = public_card

            # Check if we need to override the URL with the CRD's authoritative URL
            crd_url = _get_crd_url_for_agent(agent_url)
            if crd_url and public_card.url != crd_url:
                logger.info(f"Overriding agent card URL from '{public_card.url}' to '{crd_url}' (from CRD)")
                # Create a new card with the corrected URL
                card_dict = public_card.model_dump()
                card_dict["url"] = crd_url
                final_agent_card_to_use = AgentCard(**card_dict)
        except Exception as e:
            raise Exception(f"Failed to fetch agent card from {agent_url}: {e}")

        # If auth token provided and extended card requested, try to get it from HTTP
        if (
            auth_token
            and use_extended_card
            and final_agent_card_to_use
            and final_agent_card_to_use.supports_authenticated_extended_card
        ):
            try:
                auth_headers_dict = {"Authorization": f"Bearer {auth_token}"}
                extended_card = await resolver.get_agent_card(
                    relative_card_path=EXTENDED_AGENT_CARD_PATH,
                    http_kwargs={"headers": auth_headers_dict},
                )
                # Also override URL for extended card
                crd_url = _get_crd_url_for_agent(agent_url)
                if crd_url and extended_card.url != crd_url:
                    logger.info(f"Overriding extended card URL from '{extended_card.url}' to '{crd_url}' (from CRD)")
                    card_dict = extended_card.model_dump()
                    card_dict["url"] = crd_url
                    final_agent_card_to_use = AgentCard(**card_dict)
                else:
                    final_agent_card_to_use = extended_card
            except Exception:
                # Fall back to public card if extended card fails
                pass

        # Initialize client and send message
        client = A2AClient(
            httpx_client=httpx_client, agent_card=final_agent_card_to_use
        )

        send_message_payload = {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": message}],
                "messageId": uuid4().hex,
            },
        }

        request = SendMessageRequest(
            id=str(uuid4()), params=MessageSendParams(**send_message_payload)
        )

        try:
            response = await client.send_message(request)
            return f"Response from {agent_url}:\n\n{response.model_dump_json(indent=2, exclude_none=True)}"
        except Exception as e:
            raise Exception(f"Failed to send message to agent: {e}")


async def send_streaming_message_to_agent(
    agent_url: str,
    message: str,
    auth_token: Optional[str] = None,
    use_extended_card: bool = False,
) -> str:
    """
    Send a streaming message to an A2A agent and get the streaming response.

    Args:
        agent_url: The base URL of the agent (from AgentCard status.card.url)
        message: The message text to send
        auth_token: Optional OAuth token for authenticated requests
        use_extended_card: Whether to attempt fetching the extended agent card

    Returns:
        All streaming response chunks from the agent as JSON
    """
    async with httpx.AsyncClient(verify=False, timeout=120) as httpx_client:
        import logging
        logger = logging.getLogger(__name__)

        # Fetch agent card from HTTP endpoint
        resolver = A2ACardResolver(
            httpx_client=httpx_client,
            base_url=agent_url,
        )

        final_agent_card_to_use: AgentCard | None = None

        try:
            # Get the public agent card from HTTP
            public_card = await resolver.get_agent_card()
            final_agent_card_to_use = public_card

            # Check if we need to override the URL with the CRD's authoritative URL
            crd_url = _get_crd_url_for_agent(agent_url)
            if crd_url and public_card.url != crd_url:
                logger.info(f"Overriding agent card URL from '{public_card.url}' to '{crd_url}' (from CRD)")
                # Create a new card with the corrected URL
                card_dict = public_card.model_dump()
                card_dict["url"] = crd_url
                final_agent_card_to_use = AgentCard(**card_dict)
        except Exception as e:
            raise Exception(f"Failed to fetch agent card from {agent_url}: {e}")

        # If auth token provided and extended card requested, try to get it from HTTP
        if (
            auth_token
            and use_extended_card
            and final_agent_card_to_use
            and final_agent_card_to_use.supports_authenticated_extended_card
        ):
            try:
                auth_headers_dict = {"Authorization": f"Bearer {auth_token}"}
                extended_card = await resolver.get_agent_card(
                    relative_card_path=EXTENDED_AGENT_CARD_PATH,
                    http_kwargs={"headers": auth_headers_dict},
                )
                # Also override URL for extended card
                crd_url = _get_crd_url_for_agent(agent_url)
                if crd_url and extended_card.url != crd_url:
                    logger.info(f"Overriding extended card URL from '{extended_card.url}' to '{crd_url}' (from CRD)")
                    card_dict = extended_card.model_dump()
                    card_dict["url"] = crd_url
                    final_agent_card_to_use = AgentCard(**card_dict)
                else:
                    final_agent_card_to_use = extended_card
            except Exception:
                # Fall back to public card if extended card fails
                pass

        # Initialize client and send streaming message
        client = A2AClient(
            httpx_client=httpx_client, agent_card=final_agent_card_to_use
        )

        send_message_payload = {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": message}],
                "messageId": uuid4().hex,
            },
        }

        streaming_request = SendStreamingMessageRequest(
            id=str(uuid4()), params=MessageSendParams(**send_message_payload)
        )

        try:
            stream_response = client.send_message_streaming(streaming_request)

            result_chunks = []
            async for chunk in stream_response:
                result_chunks.append(chunk.model_dump(mode="json", exclude_none=True))

            return f"Streaming response from {agent_url}:\n\n" + "\n\n".join(
                [json.dumps(chunk, indent=2) for chunk in result_chunks]
            )

        except Exception as e:
            raise Exception(f"Failed to send streaming message to agent: {e}")
