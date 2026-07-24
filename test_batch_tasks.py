"""
GapFlow Batch Task Parsing Test
================================
Tests the batch natural-language task input feature.

Sends a block of text containing 5 distinct tasks to the Strands Agent.
Verifies that all 5 are parsed into separate Task objects with correct fields.

Also tests that one malformed/vague task does not break the entire batch.

Prerequisites:
    - AWS credentials configured
    - Model access enabled in Amazon Bedrock
    - pip install strands-agents boto3

Usage:
    py test_batch_tasks.py
"""

from gapflow.agent import parse_batch_tasks


def test_1_batch_five_tasks():
    """
    5 well-defined tasks in one text block.
    All should be parsed correctly.
    """
    print("=" * 60)
    print("TEST 1: Batch Parse 5 Tasks")
    print("=" * 60)

    batch_input = """
I need to finish my Algorithms assignment by Monday at 6pm. It will take about 4 hours and it is very important.

I have a Database Systems quiz this Friday at 10am. I need about 2 hours to prepare and it is very important.

I need to review Machine Learning notes by Thursday at 8pm. It will take around 90 minutes and is moderately important.

I should write my lab report introduction. Deadline is Wednesday at 11:59pm. It will take about 1 hour and it is important.

I need to make flashcards for Biology vocab. Due Saturday at noon. About 30 minutes, not very important.
"""

    print("\n  Sending batch input to agent...")
    tasks, response = parse_batch_tasks(batch_input)

    print(f"\n  Agent response (summary):")
    for line in response.split("\n")[:5]:
        print(f"    {line}")

    print(f"\n  Parsed {len(tasks)} task(s):")
    for i, task in enumerate(tasks, 1):
        print(f"    {i}. {task.name}")
        print(f"       Deadline: {task.deadline.strftime('%Y-%m-%d %H:%M')}")
        print(f"       Duration: {task.estimated_minutes} min")
        print(f"       Importance: {task.importance}/5")
        print()

    # Assertions
    print("  Assertions:")

    assert len(tasks) >= 5, f"FAIL: Expected at least 5 tasks, got {len(tasks)}"
    print(f"    [PASS] At least 5 tasks parsed ({len(tasks)} total)")

    # Check durations are reasonable
    durations = [t.estimated_minutes for t in tasks]
    assert any(d >= 200 and d <= 260 for d in durations), \
        f"FAIL: No task with ~240 min (4 hours). Got durations: {durations}"
    print("    [PASS] Found a ~4-hour task (Algorithms)")

    assert any(d >= 100 and d <= 140 for d in durations), \
        f"FAIL: No task with ~120 min (2 hours). Got durations: {durations}"
    print("    [PASS] Found a ~2-hour task (Database)")

    assert any(d >= 80 and d <= 100 for d in durations), \
        f"FAIL: No task with ~90 min. Got durations: {durations}"
    print("    [PASS] Found a ~90 min task (ML notes)")

    assert any(d >= 50 and d <= 70 for d in durations), \
        f"FAIL: No task with ~60 min. Got durations: {durations}"
    print("    [PASS] Found a ~60 min task (lab report)")

    assert any(d >= 25 and d <= 35 for d in durations), \
        f"FAIL: No task with ~30 min. Got durations: {durations}"
    print("    [PASS] Found a ~30 min task (flashcards)")

    # Check importance values span a range
    importances = [t.importance for t in tasks]
    assert max(importances) >= 4, f"FAIL: No high-importance task. Got: {importances}"
    assert min(importances) <= 3, f"FAIL: No low/moderate importance task. Got: {importances}"
    print(f"    [PASS] Importance range: {min(importances)} to {max(importances)}")

    # Check deadlines are all distinct
    deadlines = [t.deadline for t in tasks]
    assert len(set(deadlines)) >= 4, \
        f"FAIL: Expected at least 4 distinct deadlines, got {len(set(deadlines))}"
    print(f"    [PASS] Deadlines are distinct ({len(set(deadlines))} unique)")

    print("\n  TEST 1 PASSED!")


def test_2_malformed_task_resilience():
    """
    Include one vague/malformed task in a batch of 3 clear tasks.
    The clear tasks should still be parsed successfully.
    """
    print("\n" + "=" * 60)
    print("TEST 2: Malformed Task Does Not Break Batch")
    print("=" * 60)

    batch_input = """
I need to study for the Physics exam on Tuesday at 2pm. It will take 3 hours and is very important.

asdfghjkl something something maybe do stuff idk

I have to submit my English essay by Friday at 5pm. About 2 hours of work, moderately important.
"""

    print("\n  Sending batch with 2 clear + 1 malformed task...")
    tasks, response = parse_batch_tasks(batch_input)

    print(f"\n  Parsed {len(tasks)} task(s):")
    for i, task in enumerate(tasks, 1):
        print(f"    {i}. {task.name} | {task.deadline.strftime('%Y-%m-%d %H:%M')} | "
              f"{task.estimated_minutes} min | importance {task.importance}/5")

    print("\n  Assertions:")

    # At least the 2 clear tasks should be parsed
    assert len(tasks) >= 2, f"FAIL: Expected at least 2 tasks, got {len(tasks)}"
    print(f"    [PASS] At least 2 tasks parsed ({len(tasks)} total)")

    # Check that we got the Physics and English tasks
    names_lower = [t.name.lower() for t in tasks]
    has_physics = any("physics" in n for n in names_lower)
    has_english = any("english" in n or "essay" in n for n in names_lower)
    assert has_physics, f"FAIL: Physics task not found in {names_lower}"
    assert has_english, f"FAIL: English task not found in {names_lower}"
    print("    [PASS] Physics and English tasks parsed correctly")

    # The malformed one might get parsed with defaults or skipped - both are ok
    if len(tasks) == 3:
        print("    [INFO] Agent attempted to parse the malformed task too (acceptable)")
    else:
        print("    [INFO] Agent correctly skipped the malformed task")

    print("\n  TEST 2 PASSED!")


if __name__ == "__main__":
    test_1_batch_five_tasks()
    test_2_malformed_task_resilience()

    print("\n" + "=" * 60)
    print("ALL BATCH TASK TESTS PASSED!")
    print("=" * 60)
