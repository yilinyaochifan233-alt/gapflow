"""
GapFlow Agent Test Script
=========================
Tests the Strands Agent's ability to parse natural-language task descriptions
into structured Task data using Amazon Bedrock.

Prerequisites:
    - AWS credentials configured (aws configure or environment variables)
    - Model access enabled in Amazon Bedrock console
    - pip install strands-agents

Usage:
    py test_agent.py
"""

from gapflow.agent import create_agent, parse_task_from_text


def main():
    print("=" * 60)
    print("GAPFLOW AGENT TEST — Natural Language Task Parsing")
    print("=" * 60)
    print("\nConnecting to Amazon Bedrock...\n")

    # Create the agent once and reuse it for all test cases
    agent = create_agent()

    # Test cases — various natural-language task descriptions
    test_inputs = [
        "I have a database coursework due tomorrow at 5pm. It will take about 3 hours and it is very important.",
        "Need to review flashcards for biology, maybe 20 minutes. It's due Friday at 9am, not super important.",
        "Critical: finish the machine learning report by next Monday 23:59. Probably need 4 hours total.",
    ]

    for i, text in enumerate(test_inputs, 1):
        print("-" * 60)
        print(f"TEST {i}:")
        print(f"  Input: \"{text}\"")
        print()

        try:
            response = parse_task_from_text(text, agent=agent)
            print(f"  Agent response:")
            # Indent the response for readability
            for line in str(response).split("\n"):
                print(f"    {line}")
        except Exception as e:
            print(f"  ERROR: {e}")

        print()

    print("=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
