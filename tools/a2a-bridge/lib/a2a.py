"""A2A messaging functionality for sending messages to agents."""

import json
import httpx
from typing import Optional
from uuid import uuid4

from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (
    AgentCard,
    SendMessageRequest,
    SendStreamingMessageRequest,
    MessageSendParams,
)


EXTENDED_AGENT_CARD_PATH = "/.well-known/agent.json"


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
    async with httpx.AsyncClient(verify=False, timeout=30) as httpx_client:
        # Initialize A2ACardResolver
        resolver = A2ACardResolver(
            httpx_client=httpx_client,
            base_url=agent_url,
        )

        # Fetch agent card
        final_agent_card_to_use: AgentCard | None = None

        try:
            # Try to get the public agent card first
            public_card = await resolver.get_agent_card()
            final_agent_card_to_use = public_card

            # If auth token provided and extended card requested, try to get it
            if (
                auth_token
                and use_extended_card
                and public_card.supports_authenticated_extended_card
            ):
                try:
                    auth_headers_dict = {"Authorization": f"Bearer {auth_token}"}
                    extended_card = await resolver.get_agent_card(
                        relative_card_path=EXTENDED_AGENT_CARD_PATH,
                        http_kwargs={"headers": auth_headers_dict},
                    )
                    final_agent_card_to_use = extended_card
                except Exception:
                    # Fall back to public card if extended card fails
                    pass

        except Exception as e:
            raise Exception(f"Failed to fetch agent card from {agent_url}: {e}")

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
    async with httpx.AsyncClient(verify=False, timeout=30) as httpx_client:
        # Initialize A2ACardResolver
        resolver = A2ACardResolver(
            httpx_client=httpx_client,
            base_url=agent_url,
        )

        # Fetch agent card
        final_agent_card_to_use: AgentCard | None = None

        try:
            # Try to get the public agent card first
            public_card = await resolver.get_agent_card()
            final_agent_card_to_use = public_card

            # If auth token provided and extended card requested, try to get it
            if (
                auth_token
                and use_extended_card
                and public_card.supports_authenticated_extended_card
            ):
                try:
                    auth_headers_dict = {"Authorization": f"Bearer {auth_token}"}
                    extended_card = await resolver.get_agent_card(
                        relative_card_path=EXTENDED_AGENT_CARD_PATH,
                        http_kwargs={"headers": auth_headers_dict},
                    )
                    final_agent_card_to_use = extended_card
                except Exception:
                    # Fall back to public card if extended card fails
                    pass

        except Exception as e:
            raise Exception(f"Failed to fetch agent card from {agent_url}: {e}")

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
