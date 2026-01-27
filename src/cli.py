"""
Duke RadChat CLI - Interactive command-line interface
"""

import sys

from .chat import create_chat


def main():
    """Run interactive CLI chat."""
    print("Duke RadChat - Radiology Assistant")
    print("=" * 40)
    print("Ask about phone contacts or ACR imaging criteria.")
    print("Type 'quit' to exit, 'clear' to reset conversation.\n")

    chat = create_chat()

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

        print("\nAssistant: ", end="", flush=True)

        # Stream response
        for chunk in chat.chat_stream(user_input):
            print(chunk, end="", flush=True)

        print("\n")


if __name__ == "__main__":
    main()
