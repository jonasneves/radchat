"""
Duke RadChat - Claude-powered radiology assistant with tool calling

Implements Anthropic's recommended agentic loop pattern for multi-turn
tool use with streaming support.
"""

import json
from typing import Generator, Optional

from dotenv import load_dotenv
load_dotenv()

from .providers import create_provider, LLMProvider, list_github_models, GITHUB_MODELS_WITH_TOOLS
from .tools.phone_catalog import PHONE_CATALOG_TOOLS, execute_phone_tool
from .tools.acr_criteria import ACR_CRITERIA_TOOLS, execute_acr_tool

# Combine all tools
ALL_TOOLS = PHONE_CATALOG_TOOLS + ACR_CRITERIA_TOOLS

SYSTEM_PROMPT = """You are a radiology assistant for Duke Health clinicians. You help with:

1. **Phone Directory**: Finding contact numbers for reading rooms, scheduling, tech teams, and procedures
2. **ACR Criteria**: Looking up imaging appropriateness guidelines for clinical scenarios

Key behaviors:
- NEVER make up phone numbers. Always use the search tools to find contacts.
- When asked about imaging appropriateness, search ACR criteria first.
- Consider time of day - contacts have different availability for business hours vs after-hours.
- Be concise but complete. Clinicians are busy.
- If a contact is marked "available_now: false", mention the current time context and suggest alternatives.

For phone lookups:
- Reading rooms are for questions about studies already performed
- Scheduling contacts help with "when will my patient's study happen?"
- Procedure contacts (VIR) handle PICC lines, biopsies, drains, etc.

For ACR criteria:
- Scores 7-9 = Usually Appropriate (green light)
- Scores 4-6 = May Be Appropriate (case-by-case)
- Scores 1-3 = Usually Not Appropriate (reconsider)
"""


def execute_tool(name: str, args: dict) -> dict:
    """Route tool execution to appropriate handler."""
    # Phone catalog tools
    phone_tools = (
        "search_phone_directory",
        "get_reading_room_contact",
        "get_procedure_contact",
        "get_scheduling_contact",
        "list_contacts_by_type",
    )
    if name in phone_tools:
        return execute_phone_tool(name, args)
    # ACR criteria tools
    acr_tools = ("search_acr_criteria", "get_acr_topic_details", "list_acr_topics")
    if name in acr_tools:
        return execute_acr_tool(name, args)
    return {"error": f"Unknown tool: {name}"}


class RadChat:
    """LLM-powered radiology assistant."""

    def __init__(
        self,
        provider_type: str = "github",
        model: Optional[str] = None,
        token: Optional[str] = None,
    ):
        self.provider = create_provider(provider_type, model, token)
        self.messages: list[dict] = []

    def reset(self):
        """Clear conversation history."""
        self.messages = []

    def chat(self, user_message: str, max_turns: int = 10) -> str:
        """Send a message and get a response."""
        self.messages.append({"role": "user", "content": user_message})

        response, updated_msgs = self.provider.chat(
            messages=self.messages,
            system=SYSTEM_PROMPT,
            tools=ALL_TOOLS,
            tool_executor=execute_tool,
            max_turns=max_turns,
        )

        # Update messages with any tool interactions
        self.messages = updated_msgs
        return response

    def chat_stream(self, user_message: str, max_turns: int = 10) -> Generator[str, None, None]:
        """Stream a response token by token."""
        self.messages.append({"role": "user", "content": user_message})

        yield from self.provider.chat_stream(
            messages=self.messages,
            system=SYSTEM_PROMPT,
            tools=ALL_TOOLS,
            tool_executor=execute_tool,
            max_turns=max_turns,
        )


def create_chat(
    provider_type: str = "github",
    model: Optional[str] = None,
    token: Optional[str] = None,
) -> RadChat:
    """Create a new RadChat instance."""
    return RadChat(provider_type=provider_type, model=model, token=token)


def get_available_models() -> list[dict]:
    """Get list of available GitHub Models with function calling support."""
    return list_github_models()
