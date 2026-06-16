"""
AuraOS · CLI smoke test
Run: python cli.py "continue my fake news project"
     python cli.py "what should I work on today?"
     python cli.py "open VS Code"
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from core.agent import Agent

def main():
    if len(sys.argv) < 2:
        print("Usage: python cli.py \"your command here\"")
        sys.exit(1)

    user_input = " ".join(sys.argv[1:])
    print(f"\n{'─'*50}")
    print(f"AuraOS › {user_input}")
    print(f"{'─'*50}\n")

    agent = Agent()
    try:
        for token in agent.run(user_input):
            print(token, end="", flush=True)
    finally:
        agent.close()

if __name__ == "__main__":
    main()