"""
Duke RadChat CLI - Interactive command-line interface
"""

import os
import sys

from .chat import create_chat, get_available_models


def print_models():
    """Print available models."""
    models = get_available_models()
    print("\nAvailable models (all support function calling):")
    print("-" * 50)
    for m in models:
        print(f"  {m['id']:<35} ({m['provider']})")
    print()


def main():
    """Run interactive CLI chat."""
    # Check for model selection flag
    model = os.environ.get("MODEL", "openai/gpt-4o-mini")

    if "--models" in sys.argv or "-m" in sys.argv:
        print_models()
        return

    if "--model" in sys.argv:
        idx = sys.argv.index("--model")
        if idx + 1 < len(sys.argv):
            model = sys.argv[idx + 1]

    print("Duke RadChat - Radiology Assistant")
    print("=" * 40)
    print(f"Model: {model}")
    print("Ask about phone contacts or ACR imaging criteria.")
    print("Type 'quit' to exit, 'clear' to reset, 'models' to list models.\n")
    print("Examples:")
    print("  - Who reads neuro MRIs after hours?")
    print("  - Need a chest tube placed for a patient at Duke North")
    print("  - 65yo with acute onset worst headache of life - best imaging?")
    print("  - CT vs MRI for suspected acute stroke?\n")

    chat = create_chat(provider_type="github", model=model)

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() == "quit":
            print("Goodbye!")
            break

        if user_input.lower() == "clear":
            chat.reset()
            print("Conversation cleared.\n")
            continue

        if user_input.lower() == "models":
            print_models()
            continue

        print("\nAssistant: ", end="", flush=True)

        # Stream response
        for chunk in chat.chat_stream(user_input):
            print(chunk, end="", flush=True)

        print("\n")


if __name__ == "__main__":
    main()
