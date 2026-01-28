"""
LLM Provider abstraction - supports Anthropic and GitHub Models
"""

import json
import os
from abc import ABC, abstractmethod
from typing import Generator, Optional

# GitHub Models that support function calling (tool-calling capability)
GITHUB_MODELS_WITH_TOOLS = [
    # OpenAI - GPT-4.1 family first (better tool calling reliability)
    {"id": "openai/gpt-4.1-mini", "name": "GPT-4.1 Mini", "provider": "OpenAI"},
    {"id": "openai/gpt-4.1", "name": "GPT-4.1", "provider": "OpenAI"},
    {"id": "openai/gpt-4.1-nano", "name": "GPT-4.1 Nano", "provider": "OpenAI"},
    {"id": "openai/gpt-4o", "name": "GPT-4o", "provider": "OpenAI"},
    {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini", "provider": "OpenAI"},
    {"id": "openai/gpt-5", "name": "GPT-5", "provider": "OpenAI"},
    {"id": "openai/gpt-5-mini", "name": "GPT-5 Mini", "provider": "OpenAI"},
    {"id": "openai/gpt-5-nano", "name": "GPT-5 Nano", "provider": "OpenAI"},
    {"id": "openai/o1", "name": "o1", "provider": "OpenAI"},
    {"id": "openai/o3", "name": "o3", "provider": "OpenAI"},
    {"id": "openai/o3-mini", "name": "o3 Mini", "provider": "OpenAI"},
    {"id": "openai/o4-mini", "name": "o4 Mini", "provider": "OpenAI"},
    # DeepSeek
    {"id": "deepseek/deepseek-r1", "name": "DeepSeek R1", "provider": "DeepSeek"},
    {"id": "deepseek/deepseek-r1-0528", "name": "DeepSeek R1 0528", "provider": "DeepSeek"},
    {"id": "deepseek/deepseek-v3-0324", "name": "DeepSeek V3", "provider": "DeepSeek"},
    # Meta
    {"id": "meta/llama-4-maverick-17b-128e-instruct-fp8", "name": "Llama 4 Maverick", "provider": "Meta"},
    {"id": "meta/llama-4-scout-17b-16e-instruct", "name": "Llama 4 Scout", "provider": "Meta"},
    # Mistral
    {"id": "mistral-ai/ministral-3b", "name": "Ministral 3B", "provider": "Mistral AI"},
    {"id": "mistral-ai/mistral-medium-2505", "name": "Mistral Medium 3", "provider": "Mistral AI"},
    {"id": "mistral-ai/mistral-small-2503", "name": "Mistral Small 3.1", "provider": "Mistral AI"},
    # Cohere
    {"id": "cohere/cohere-command-r-plus-08-2024", "name": "Command R+", "provider": "Cohere"},
    # AI21
    {"id": "ai21-labs/ai21-jamba-1.5-large", "name": "Jamba 1.5 Large", "provider": "AI21 Labs"},
]

GITHUB_MODELS_ENDPOINT = "https://models.github.ai/inference"


def convert_anthropic_tools_to_openai(tools: list[dict]) -> list[dict]:
    """Convert Anthropic tool format to OpenAI function calling format."""
    openai_tools = []
    for tool in tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            }
        })
    return openai_tools


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        tool_executor: callable,
        max_turns: int = 10,
    ) -> str:
        """Send messages and get a response, handling tool calls."""
        pass

    @abstractmethod
    def chat_stream(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        tool_executor: callable,
        max_turns: int = 10,
    ) -> Generator[str, None, None]:
        """Stream a response, handling tool calls."""
        pass


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider."""

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        import anthropic
        self.client = anthropic.Anthropic()
        self.model = model

    def chat(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        tool_executor: callable,
        max_turns: int = 10,
    ) -> str:
        msgs = list(messages)

        for _ in range(max_turns):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system,
                tools=tools,
                messages=msgs,
            )

            if response.stop_reason == "tool_use":
                msgs.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = tool_executor(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, indent=2),
                        })

                msgs.append({"role": "user", "content": tool_results})
            else:
                msgs.append({"role": "assistant", "content": response.content})
                text_parts = [block.text for block in response.content if hasattr(block, "text")]
                return "\n".join(text_parts), msgs

        return "Maximum conversation turns reached.", msgs

    def chat_stream(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        tool_executor: callable,
        max_turns: int = 10,
    ) -> Generator[str, None, None]:
        msgs = list(messages)

        for _ in range(max_turns):
            with self.client.messages.stream(
                model=self.model,
                max_tokens=4096,
                system=system,
                tools=tools,
                messages=msgs,
            ) as stream:
                for event in stream:
                    if hasattr(event, "type"):
                        if event.type == "content_block_delta":
                            if hasattr(event.delta, "text"):
                                yield event.delta.text

                response = stream.get_final_message()

            if response.stop_reason == "tool_use":
                msgs.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        yield f"\n[Searching: {block.name}...]\n"
                        result = tool_executor(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, indent=2),
                        })

                msgs.append({"role": "user", "content": tool_results})
            else:
                msgs.append({"role": "assistant", "content": response.content})
                return

        yield "\nMaximum conversation turns reached."


class GitHubModelsProvider(LLMProvider):
    """GitHub Models provider using OpenAI-compatible API."""

    def __init__(self, model: str = "openai/gpt-4.1-mini", token: Optional[str] = None):
        from openai import OpenAI

        self.token = token or os.environ.get("GH_MODELS_TOKEN")
        if not self.token:
            raise ValueError("GitHub token required. Set GH_MODELS_TOKEN or pass token parameter.")

        self.client = OpenAI(
            base_url=GITHUB_MODELS_ENDPOINT,
            api_key=self.token,
        )
        self.model = model

    def _convert_messages(self, messages: list[dict], system: str) -> list[dict]:
        """Convert messages to OpenAI format with system message."""
        result = [{"role": "system", "content": system}]

        for msg in messages:
            if msg["role"] == "user":
                content = msg["content"]
                # Handle tool results
                if isinstance(content, list):
                    tool_results = []
                    for item in content:
                        if item.get("type") == "tool_result":
                            tool_results.append({
                                "role": "tool",
                                "tool_call_id": item["tool_use_id"],
                                "content": item["content"],
                            })
                    result.extend(tool_results)
                else:
                    result.append({"role": "user", "content": content})
            elif msg["role"] == "assistant":
                content = msg["content"]
                if isinstance(content, list):
                    # Handle Anthropic-style content blocks
                    text_content = ""
                    tool_calls = []
                    for block in content:
                        if hasattr(block, "text"):
                            text_content += block.text
                        elif hasattr(block, "type") and block.type == "tool_use":
                            tool_calls.append({
                                "id": block.id,
                                "type": "function",
                                "function": {
                                    "name": block.name,
                                    "arguments": json.dumps(block.input),
                                }
                            })
                    msg_dict = {"role": "assistant", "content": text_content or None}
                    if tool_calls:
                        msg_dict["tool_calls"] = tool_calls
                    result.append(msg_dict)
                else:
                    result.append({"role": "assistant", "content": content})

        return result

    def chat(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        tool_executor: callable,
        max_turns: int = 10,
    ) -> str:
        msgs = list(messages)
        openai_tools = convert_anthropic_tools_to_openai(tools)

        for _ in range(max_turns):
            openai_msgs = self._convert_messages(msgs, system)

            response = self.client.chat.completions.create(
                model=self.model,
                messages=openai_msgs,
                tools=openai_tools,
            )

            choice = response.choices[0]
            assistant_msg = choice.message

            if choice.finish_reason == "tool_calls" or assistant_msg.tool_calls:
                # Store in Anthropic-like format for consistency
                content_blocks = []
                if assistant_msg.content:
                    content_blocks.append(type("TextBlock", (), {"type": "text", "text": assistant_msg.content})())

                for tc in assistant_msg.tool_calls:
                    content_blocks.append(type("ToolUseBlock", (), {
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.function.name,
                        "input": json.loads(tc.function.arguments),
                    })())

                msgs.append({"role": "assistant", "content": content_blocks})

                tool_results = []
                for tc in assistant_msg.tool_calls:
                    args = json.loads(tc.function.arguments)
                    result = tool_executor(tc.function.name, args)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": json.dumps(result, indent=2),
                    })

                msgs.append({"role": "user", "content": tool_results})
            else:
                return assistant_msg.content or "", msgs

        return "Maximum conversation turns reached.", msgs

    def chat_stream(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        tool_executor: callable,
        max_turns: int = 10,
    ) -> Generator[str, None, None]:
        msgs = list(messages)
        openai_tools = convert_anthropic_tools_to_openai(tools)

        for _ in range(max_turns):
            openai_msgs = self._convert_messages(msgs, system)

            # Collect streamed response
            full_content = ""
            tool_calls_data = {}

            stream = self.client.chat.completions.create(
                model=self.model,
                messages=openai_msgs,
                tools=openai_tools,
                stream=True,
            )

            for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                if delta.content:
                    full_content += delta.content
                    yield delta.content

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_data:
                            tool_calls_data[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc.id:
                            tool_calls_data[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_data[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_data[idx]["arguments"] += tc.function.arguments

            # Check if we have tool calls
            if tool_calls_data:
                content_blocks = []
                if full_content:
                    content_blocks.append(type("TextBlock", (), {"type": "text", "text": full_content})())

                for idx in sorted(tool_calls_data.keys()):
                    tc = tool_calls_data[idx]
                    content_blocks.append(type("ToolUseBlock", (), {
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["name"],
                        "input": json.loads(tc["arguments"]) if tc["arguments"] else {},
                    })())

                msgs.append({"role": "assistant", "content": content_blocks})

                tool_results = []
                for idx in sorted(tool_calls_data.keys()):
                    tc = tool_calls_data[idx]
                    tool_name = tc["name"]

                    # Emit tool call start marker
                    yield f"__TOOL_START__{tool_name}__"

                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                    result = tool_executor(tool_name, args)

                    # Determine tool type
                    acr_tools = ["get_imaging_recommendations", "search_acr_criteria", "list_acr_topics", "get_acr_topic_details"]
                    if tool_name in acr_tools or "acr" in tool_name.lower():
                        tool_type = "acr"
                    else:
                        tool_type = "contacts"

                    # Emit structured tool result
                    yield f"__TOOL_RESULT__{json.dumps({'type': tool_type, 'tool': tool_name, 'data': result})}__"

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "content": json.dumps(result, indent=2),
                    })

                msgs.append({"role": "user", "content": tool_results})
            else:
                return

        yield "\nMaximum conversation turns reached."


def create_provider(
    provider_type: str = "github",
    model: Optional[str] = None,
    token: Optional[str] = None,
) -> LLMProvider:
    """Create an LLM provider instance."""
    if provider_type == "anthropic":
        return AnthropicProvider(model=model or "claude-sonnet-4-20250514")
    elif provider_type == "github":
        return GitHubModelsProvider(model=model or "openai/gpt-4.1-mini", token=token)
    else:
        raise ValueError(f"Unknown provider: {provider_type}")


def list_github_models() -> list[dict]:
    """List available GitHub Models that support function calling."""
    return GITHUB_MODELS_WITH_TOOLS
