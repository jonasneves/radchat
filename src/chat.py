"""
Duke RadChat - Claude-powered radiology assistant with tool calling

Implements Anthropic's recommended agentic loop pattern for multi-turn
tool use with streaming support.
"""

from typing import Generator, Optional

from dotenv import load_dotenv
load_dotenv()

from .providers import create_provider, LLMProvider, list_all_models
from .tools.phone_catalog import PHONE_CATALOG_TOOLS, execute_phone_tool
from .tools.acr_criteria import ACR_CRITERIA_TOOLS, execute_acr_tool

# Combine all tools
ALL_TOOLS = PHONE_CATALOG_TOOLS + ACR_CRITERIA_TOOLS

SYSTEM_PROMPT = """You are a radiology assistant for Duke Health clinicians. You help with phone directory lookups and ACR imaging criteria.

**Communication style:**
• Answer in 1-2 sentences when possible. Clinicians are busy.
• Lead with the answer, then provide context if needed.
• Use **bold** for key information (names, numbers, scores).
• Only use bullets/lists when comparing multiple items or listing alternatives.

**Critical tool usage rules:**
• NEVER guess or make up phone numbers, pager numbers, or contact information. Always use search tools.
• NEVER guess ACR appropriateness scores or imaging recommendations. Always search ACR criteria first.
• If a tool search returns no results, say "I couldn't find that information in our directory" - do not guess.
• If you're unsure whether information came from a tool, err on the side of searching again.

**Tool results are displayed automatically:**
Tool results appear as rich cards in the UI. Do NOT repeat or list the data from tool results - the user already sees it. Instead, provide a brief interpretation or highlight the key takeaway. For example:
• ACR criteria → "CTA chest is first-line for suspected PE" (don't list all the variants)
• Phone lookup → "Here's the contact" (don't repeat the number)

**Tool usage guidance:**
• For contact questions → use search_phone_directory or specific contact tools
• For imaging appropriateness → use get_imaging_recommendations
• Consider time of day - mention if contacts are after-hours only

**Domain knowledge (general info only - always verify specifics with tools):**
• Reading rooms → questions about completed studies
• Scheduling → "when will my patient's study happen?"
• Procedure/VIR → PICC lines, biopsies, drains
• ACR scores: 7-9 = appropriate, 4-6 = may be appropriate, 1-3 = usually not appropriate
"""


def execute_tool(name: str, args: dict) -> dict:
    """Route tool execution to appropriate handler."""
    print(f"[TOOL] {name}({args})")
    # Phone catalog tools
    phone_tools = (
        "search_phone_directory",
        "get_reading_room_contact",
        "get_procedure_contact",
        "get_scheduling_contact",
        "list_contacts_by_type",
    )
    if name in phone_tools:
        result = execute_phone_tool(name, args)
        print(f"[TOOL] {name} returned {len(result.get('results', result.get('contacts', [])))} results")
        return result
    # ACR criteria tools
    acr_tools = ("get_imaging_recommendations", "list_acr_topics")
    if name in acr_tools:
        result = execute_acr_tool(name, args)
        print(f"[TOOL] {name} found={result.get('found', 'n/a')}")
        return result
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
    """Get list of available models with function calling support."""
    return list_all_models()
