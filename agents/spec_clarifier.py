import json
from pathlib import Path

import anthropic

from config import ANTHROPIC_API_KEY
from scripts.logger import get_logger

logger = get_logger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "output"
MODEL = "claude-sonnet-4-20250514"
SYSTEM_PROMPT = (
    "You are a senior software architect helping to clarify a project brief before any code is written. "
    "Your job is to identify the 3–5 questions that would most reduce ambiguity if answered. "
    "Prioritize questions about technical decisions that are hard to change later: "
    "authentication mechanism, database choice, API design, data schema, and expected scale. "
    "Deprioritize stylistic or cosmetic preferences. "
    'Return ONLY a JSON object with a single key "questions" containing a list of 3–5 question strings. '
    "No explanations, no markdown — just the raw JSON object."
)


def run_spec_clarifier(project_brief: str, conventions: str) -> dict[str, list[str]]:
    """Interrogate a project brief and return structured clarifying questions.

    Calls claude-sonnet-4-20250514 to identify the 3–5 questions that would most
    reduce ambiguity if answered, prioritising hard-to-change technical decisions.
    Writes a markdown summary to /output/spec_clarifications.md. For the MVP,
    answers are hardcoded placeholders — wire up real user input in a later task.

    Args:
        project_brief: Plain-English description of the project to be built.
        conventions: Content of CONVENTIONS.md, injected on every call.

    Returns:
        Dict with keys:
            questions (list[str]): 3–5 clarifying questions from Claude.
            answers (list[str]): Placeholder answers, one per question.

    Raises:
        anthropic.APIError: If the Claude API call fails.
        json.JSONDecodeError: If Claude returns malformed JSON.
        ValueError: If the parsed questions list is not 3–5 strings.
    """
    logger.info("Spec clarifier starting on brief (%d chars)", len(project_brief))

    user_prompt = (
        f"## Project Conventions\n\n{conventions}\n\n"
        f"## Project Brief\n\n{project_brief}\n\n"
        "Identify the 3–5 questions that would most reduce ambiguity in this brief. "
        'Return a JSON object: {"questions": ["...", ...]}'
    )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
        )
    except anthropic.APIError as e:
        logger.error("Claude API call failed in spec clarifier: %s", e)
        raise

    first_block = response.content[0]
    if not isinstance(first_block, anthropic.types.TextBlock):
        raise ValueError(f"Unexpected content block type: {type(first_block)}")

    raw = first_block.text.strip()
    logger.debug("Raw spec clarifier response: %s", raw)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("Spec clarifier returned invalid JSON: %s", e)
        raise

    questions: list[str] = parsed.get("questions", [])
    if not (3 <= len(questions) <= 5) or not all(isinstance(q, str) for q in questions):
        raise ValueError(f"Expected 3–5 question strings, got: {questions!r}")

    answers: list[str] = ["[placeholder] To be determined"] * len(questions)

    output_path = OUTPUT_DIR / "spec_clarifications.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Spec Clarifications\n"]
    for i, (q, a) in enumerate(zip(questions, answers), start=1):
        lines.append(f"## Q{i}: {q}\n\n**Answer:** {a}\n")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Spec clarifier wrote clarifications: %s", output_path)

    return {"questions": questions, "answers": answers}
