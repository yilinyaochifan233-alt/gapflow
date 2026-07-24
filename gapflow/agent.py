"""GapFlow Agent — Strands Agent with Amazon Bedrock for task parsing and replanning."""

from datetime import datetime

from strands import Agent
from strands.models import BedrockModel

from gapflow.core.models import Task
from gapflow.tools.parse_task import parse_task, get_parsed_tasks, clear_parsed_tasks
from gapflow.tools.replan import apply_schedule_change, get_replan_actions, clear_replan_actions


# System prompt instructs the agent on how to parse task descriptions
SYSTEM_PROMPT = """You are GapFlow, an AI assistant that helps university students manage their study time.

Your job right now: parse natural-language task descriptions into structured data.

When a user describes a task, you MUST call the parse_task tool with these fields:
- task_name: A short, clear name for the task.
- deadline_description: The deadline as an ISO datetime string (YYYY-MM-DDTHH:MM:SS). 
  Use today's date as reference: {today}. 
  "tomorrow" means the next day. "next Monday" means the coming Monday, etc.
- estimated_minutes: The estimated duration in minutes.
  Convert hours to minutes (e.g., "3 hours" = 180, "1.5 hours" = 90).
- importance: A number from 1 to 5.
  Mapping: "not important" = 1, "somewhat important" = 2, "moderately important" = 3, 
  "important" = 4, "very important" / "critical" / "urgent" = 5.

Always call the parse_task tool. Do not just return text — you MUST use the tool.
After calling the tool, confirm what was parsed in a brief, friendly message.
"""


def create_agent(model_id: str = "us.anthropic.claude-sonnet-4-20250514-v1:0",
                 region: str = "us-east-1") -> Agent:
    """
    Create and return a GapFlow task-parsing agent.

    Args:
        model_id: Bedrock model ID to use.
        region: AWS region for Bedrock.

    Returns:
        Configured Strands Agent.
    """
    model = BedrockModel(
        model_id=model_id,
        region_name=region,
    )

    today = datetime.now().strftime("%Y-%m-%d %H:%M")

    agent = Agent(
        model=model,
        tools=[parse_task],
        system_prompt=SYSTEM_PROMPT.format(today=today),
    )

    return agent


def parse_task_from_text(text: str, agent: Agent | None = None) -> str:
    """
    Convenience function: send a natural-language task description to the agent.

    Args:
        text: Natural-language task description from the student.
        agent: Optional pre-created agent. If None, creates a new one.

    Returns:
        Agent's response as a string.
    """
    if agent is None:
        agent = create_agent()

    response = agent(text)
    return str(response)


def parse_tasks_from_texts(texts: list[str], agent: Agent | None = None) -> list[Task]:
    """
    Parse multiple natural-language task descriptions and return real Task objects.

    This is the main integration point: it sends each description to the agent,
    which calls parse_task tool internally, and we retrieve the stored Task objects.

    Args:
        texts: List of natural-language task descriptions.
        agent: Optional pre-created agent. If None, creates a new one.

    Returns:
        List of Task objects created by the agent.
    """
    if agent is None:
        agent = create_agent()

    # Clear any previously stored tasks
    clear_parsed_tasks()

    for text in texts:
        agent(text)

    return get_parsed_tasks()


# ─────────────────────────────────────────────────────────────
# Batch Task Parsing
# ─────────────────────────────────────────────────────────────

BATCH_SYSTEM_PROMPT = """You are GapFlow, an AI assistant that helps university students manage their study time.

The user has given you a block of text that contains MULTIPLE tasks.
Your job: identify each distinct task and call parse_task ONCE for EACH task you find.

Rules:
- Today's date and time: {today}
- A "task" is any distinct piece of work with its own deadline, duration, and importance.
- Call parse_task separately for EACH task you detect.
- If you find 5 tasks in the text, call parse_task 5 times.
- "tomorrow" means the next day. "next Monday" means the coming Monday, etc.
- Convert hours to minutes (e.g., "3 hours" = 180, "1.5 hours" = 90, "90 minutes" = 90).
- Importance mapping: "not important" = 1, "somewhat important" = 2, "moderately important" = 3, 
  "important" = 4, "very important" / "critical" / "urgent" = 5.
- If a task description is unclear or missing critical info (deadline/duration), still try your best.
  Use reasonable defaults: importance 3, deadline = 7 days from now if unspecified.
- Do NOT skip any task. Parse every one you can identify.
- After calling parse_task for all tasks, briefly confirm how many tasks you parsed.
"""


def create_batch_agent(
    model_id: str = "us.anthropic.claude-sonnet-4-20250514-v1:0",
    region: str = "us-east-1",
) -> Agent:
    """
    Create an agent optimized for batch task parsing.

    This agent is instructed to call parse_task multiple times — once per task
    it identifies in a block of text.
    """
    model = BedrockModel(
        model_id=model_id,
        region_name=region,
    )

    today = datetime.now().strftime("%Y-%m-%d %H:%M")

    agent = Agent(
        model=model,
        tools=[parse_task],
        system_prompt=BATCH_SYSTEM_PROMPT.format(today=today),
    )

    return agent


def parse_batch_tasks(
    text: str,
    agent: Agent | None = None,
) -> tuple[list[Task], str]:
    """
    Parse a block of text containing multiple tasks.

    The agent identifies distinct tasks semantically and calls parse_task for each one.

    Args:
        text: Multi-task natural-language input from the user.
        agent: Optional pre-created batch agent.

    Returns:
        Tuple of (list of parsed Task objects, agent response text).
    """
    if agent is None:
        agent = create_batch_agent()

    # Clear previously stored tasks
    clear_parsed_tasks()

    # Send the entire block to the agent
    response = agent(text)

    # Retrieve all parsed tasks
    tasks = get_parsed_tasks()

    return tasks, str(response)


# ─────────────────────────────────────────────────────────────
# Replan Agent
# ─────────────────────────────────────────────────────────────

REPLAN_SYSTEM_PROMPT = """You are GapFlow, an AI assistant that helps university students manage their study time.

The student already has a schedule. They are now describing a CHANGE to their day.
Your job: understand the change and call the apply_schedule_change tool with the correct action.

Today's date and time: {today}

The student's current tasks are:
{tasks_summary}

Available action types:
- ADD_FIXED_EVENT: A new meeting, lecture, or appointment that blocks time.
  Use when the student says they have a new commitment at a specific time.
- ADD_TASK: A brand new task they need to complete.
  Use when the student mentions new work with a deadline.
- UPDATE_TASK: An existing task needs more or less time.
  Use extra_minutes > 0 if they need more time, < 0 if they need less.
- COMPLETE_TASK: A task is already done.
  Use when the student says they finished something.
- BLOCK_TIME: A time range where the student cannot study.
  Use when they say they can't study during a certain period.

Rules:
- Always call apply_schedule_change. Do NOT just return text.
- Provide a clear, friendly explanation in the 'explanation' field.
- For times, use HH:MM format (24-hour).
- For deadlines, use ISO format (YYYY-MM-DDTHH:MM:SS).
- If unsure about importance, default to 3.
- Match task names approximately — the system uses fuzzy matching.
"""


def create_replan_agent(
    tasks: list[Task] | None = None,
    model_id: str = "us.anthropic.claude-sonnet-4-20250514-v1:0",
    region: str = "us-east-1",
) -> Agent:
    """
    Create a replan agent that understands schedule changes.

    Args:
        tasks: Current task list (shown to agent for context).
        model_id: Bedrock model ID.
        region: AWS region.

    Returns:
        Configured Strands Agent for replanning.
    """
    model = BedrockModel(
        model_id=model_id,
        region_name=region,
    )

    today = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Build task summary for context
    if tasks:
        lines = []
        for t in tasks:
            status = "DONE" if t.remaining_minutes <= 0 else f"{t.remaining_minutes} min remaining"
            lines.append(f"  - {t.name} (due {t.deadline.strftime('%b %d %H:%M')}, {status}, importance {t.importance}/5)")
        tasks_summary = "\n".join(lines)
    else:
        tasks_summary = "  (no tasks currently)"

    agent = Agent(
        model=model,
        tools=[apply_schedule_change],
        system_prompt=REPLAN_SYSTEM_PROMPT.format(today=today, tasks_summary=tasks_summary),
    )

    return agent


def process_replan_request(
    text: str,
    tasks: list[Task] | None = None,
    agent: Agent | None = None,
) -> tuple[list[dict], str]:
    """
    Send a natural-language schedule change to the replan agent.

    Args:
        text: The user's change description (e.g., "I have a meeting at 4pm").
        tasks: Current task list for context.
        agent: Optional pre-created replan agent.

    Returns:
        Tuple of (list of action dicts, agent explanation text).
    """
    if agent is None:
        agent = create_replan_agent(tasks=tasks)

    # Clear previous actions
    clear_replan_actions()

    # Send to agent
    response = agent(text)

    # Retrieve structured actions
    actions = get_replan_actions()

    return actions, str(response)
