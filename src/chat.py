"""
Duke RadChat - Claude-powered radiology assistant with tool calling

Implements Anthropic's recommended agentic loop pattern for multi-turn
tool use with streaming support.
"""

import json
from typing import Generator, Optional

import anthropic

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
    if name in ("search_phone_directory", "get_reading_room_contact", "get_procedure_contact"):
        return execute_phone_tool(name, args)
    # ACR criteria tools
    if name in ("search_acr_criteria", "get_acr_topic_details", "list_acr_topics"):
        return execute_acr_tool(name, args)
    return {"error": f"Unknown tool: {name}"}


class RadChat:
    """Claude-powered radiology assistant."""

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic()
        self.model = model
        self.messages: list[dict] = []

    def reset(self):
        """Clear conversation history."""
        self.messages = []

    def chat(self, user_message: str, max_turns: int = 10) -> str:
        """
        Send a message and get a response.

        Implements agentic loop: continues until Claude stops calling tools
        or max_turns is reached.
        """
        self.messages.append({"role": "user", "content": user_message})

        for _ in range(max_turns):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=ALL_TOOLS,
                messages=self.messages,
            )

            # Check if we need to handle tool use
            if response.stop_reason == "tool_use":
                # Add assistant's response (includes tool_use blocks)
                self.messages.append({"role": "assistant", "content": response.content})

                # Process each tool call
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = execute_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, indent=2),
                        })

                # Add tool results
                self.messages.append({"role": "user", "content": tool_results})

            else:
                # No more tool calls - extract final text response
                self.messages.append({"role": "assistant", "content": response.content})

                text_parts = [block.text for block in response.content if hasattr(block, "text")]
                return "\n".join(text_parts)

        return "Maximum conversation turns reached."

    def chat_stream(self, user_message: str, max_turns: int = 10) -> Generator[str, None, None]:
        """
        Stream a response token by token.

        Yields text chunks as they arrive. Tool calls are handled internally.
        """
        self.messages.append({"role": "user", "content": user_message})

        for _ in range(max_turns):
            # Collect the full response for tool handling
            full_response_content = []
            current_text = ""

            with self.client.messages.stream(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=ALL_TOOLS,
                messages=self.messages,
            ) as stream:
                for event in stream:
                    if hasattr(event, "type"):
                        if event.type == "content_block_delta":
                            if hasattr(event.delta, "text"):
                                current_text += event.delta.text
                                yield event.delta.text

                # Get final message
                response = stream.get_final_message()

            # Check if we need tool use
            if response.stop_reason == "tool_use":
                self.messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        yield f"\n[Searching: {block.name}...]\n"
                        result = execute_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, indent=2),
                        })

                self.messages.append({"role": "user", "content": tool_results})

            else:
                self.messages.append({"role": "assistant", "content": response.content})
                return

        yield "\nMaximum conversation turns reached."


def create_chat(model: Optional[str] = None) -> RadChat:
    """Create a new RadChat instance."""
    return RadChat(model=model) if model else RadChat()
