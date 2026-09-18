#!/usr/bin/env python3
"""
Skill Quality Scorer
====================
Grade an agent skill against a 6-dimension quality rubric using an LLM judge,
then print the scores and recommended improvements in the terminal.

This is a Layer 1 (static) evaluator: it READS a skill's files and grades the
writing. It does not execute the skill. Inspired by the public agentskills.io
evaluation pattern (LLM-as-judge + rubric scoring).

Usage:
    python score_skill.py <path-to-skill-folder-or-SKILL.md>
    python score_skill.py --demo                     (no API key needed)

Environment:
    GEMINI_API_KEY   Optional Google AI Studio key; prompted for if unset in a terminal
    GEMINI_MODEL     Judge model (default: gemini-flash-latest)
"""
import argparse
import getpass
import json
import os
import sys
from pathlib import Path

# The 6 rubric dimensions. Order is fixed and mirrored in the report.
RUBRIC = [
    ("Instruction Clarity",
     "Are instructions structured and phased, with explicit scope and clear "
     "MUST / MUST NOT rules? Are output formats and decision rules specified "
     "well enough to drive consistent behavior across runs?"),
    ("Behavioral Completeness",
     "Do the workflows define multi-step behavior with explicit fallbacks, "
     "error handling, and confirmation checkpoints for actions that change "
     "state? Are stop, cleanup, and exit criteria consistent?"),
    ("Example Quality",
     "Are there multiple realistic usage examples and structured output "
     "templates, including full end-to-end interactions and edge-case "
     "walkthroughs?"),
    ("Robustness",
     "Does the skill anticipate real-world failure modes such as auth, "
     "dependency or network checks, paging, retries, timeouts, and "
     "degraded-mode fallbacks? Are limits standardized?"),
    ("Safety And Guardrails",
     "Are there safeguards for risky or state-changing actions: preview and "
     "confirm gates, least-privilege guidance, and prompt-injection defenses "
     "when ingesting external content?"),
    ("User Experience",
     "Are entry points and intent obvious? Does it use guided setup, smart "
     "defaults, progressive disclosure, and actionable error messages and "
     "prerequisites?"),
]

TEXT_EXTS = {".md", ".txt", ".py", ".json", ".yml", ".yaml", ".toml",
             ".js", ".ts", ".sh", ".ps1", ".csv"}
MAX_FILE_CHARS = 20000      # per-file cap fed to the judge
MAX_TOTAL_CHARS = 120000    # overall cap fed to the judge


def read_skill(target: Path):
    """Collect a skill's readable files into one text blob for the judge."""
    if target.is_file():
        if target.name.lower() != "skill.md":
            sys.exit(f"ERROR: expected a SKILL.md file: {target}")
        folder = target.parent
        paths = [target]
    elif target.is_dir():
        folder = target
        paths = sorted(
            folder.rglob("*"),
            key=lambda p: (p.name.lower() != "skill.md", str(p).lower()),
        )
    else:
        sys.exit(f"ERROR: skill folder or SKILL.md not found: {target}")

    skill_md = folder / "SKILL.md"
    if not skill_md.exists():
        print(f"WARNING: no SKILL.md at {folder}. Scoring whatever files exist.")

    name = folder.name
    parts, files_used, total = [], [], 0

    for path in paths:
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTS:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(folder).as_posix()
        snippet = content[:MAX_FILE_CHARS]
        block = f"\n===== FILE: {rel} =====\n{snippet}\n"
        if total + len(block) > MAX_TOTAL_CHARS:
            break
        parts.append(block)
        files_used.append(rel)
        total += len(block)

    if not parts:
        sys.exit(f"ERROR: no readable text files found in {folder}")

    return name, "".join(parts), files_used


def build_prompt(name: str, blob: str) -> str:
    dims = "\n".join(
        f"{i+1}. {dim} - {desc}" for i, (dim, desc) in enumerate(RUBRIC)
    )
    dim_names = ", ".join(d for d, _ in RUBRIC)
    return f"""You are a rigorous evaluator of AI agent skills. Grade the skill \
named "{name}" using ONLY the source files provided below.

Score each of these 6 dimensions on an integer scale of 1 to 5 (5 is best):

{dims}

Scoring guidance:
- 5 = exemplary, consistently strong across the whole skill.
- 4 = strong with minor or uneven gaps.
- 3 = adequate but inconsistent or missing important pieces.
- 2 = weak, significant gaps.
- 1 = largely absent.

Return your assessment as JSON matching this shape exactly:
{{
  "summary": "2-4 sentence overall assessment of the skill.",
  "dimensions": [
    {{"name": "<one of: {dim_names}>", "score": <1-5>, "justification": "1-3 sentences citing concrete evidence."}}
  ],
  "improvements": [
    {{"file": "<relative file path or 'general'>", "suggestion": "one concrete, actionable fix."}}
  ]
}}

Rules:
- Include all 6 dimensions, in the order listed above.
- Provide 2 to 4 improvements, each tied to a specific file where possible.
- Do not use em dashes in any text. Use periods, commas, colons, or parentheses.
- Base every judgment on evidence in the files, not assumptions.

SKILL SOURCE FILES:
{blob}
"""


def get_api_key() -> str:
    """Use the environment key or request one privately in a terminal."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if api_key:
        return api_key
    if not sys.stdin.isatty():
        sys.exit("ERROR: No Gemini API key is available. Run in a terminal to enter one privately, or set GEMINI_API_KEY.")
    try:
        api_key = getpass.getpass("Gemini API key (input hidden): ").strip()
    except (EOFError, KeyboardInterrupt):
        sys.exit("ERROR: Gemini API key entry cancelled.")
    if not api_key:
        sys.exit("ERROR: Gemini API key cannot be empty.")
    return api_key


def score_with_gemini(prompt: str, model: str) -> dict:
    """Call Gemini with structured JSON output and return the parsed dict."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        sys.exit("ERROR: google-genai not installed. Run: pip install -r requirements.txt")

    api_key = get_api_key()

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.2,
    )

    # Retry transient server and rate-limit errors (429, 500, 503) with backoff.
    import time
    max_attempts = 4
    resp = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = client.models.generate_content(model=model, contents=prompt, config=config)
            break
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "code", None)
            text = str(exc)
            transient = code in (429, 500, 503) or any(
                s in text for s in ("UNAVAILABLE", "high demand", "RESOURCE_EXHAUSTED", "overloaded")
            )
            if transient and attempt < max_attempts:
                wait = 3 * attempt
                print(f"  transient error ({code or 'server'}); retry {attempt}/{max_attempts - 1} in {wait}s ...")
                time.sleep(wait)
                continue
            sys.exit(f"ERROR: judge call failed ({code or 'error'}): {text[:300]}")
    raw = (resp.text if resp else "") or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start:end + 1])
        sys.exit(f"ERROR: judge did not return valid JSON:\n{raw[:500]}")


def demo_scores() -> dict:
    """Canned result so the report can be previewed without an API key."""
    return {
        "summary": (
            "These are sample scores printed without calling an LLM. They show the "
            "terminal output format. Run the tool on a real skill folder "
            "with a personal Gemini key to get a genuine assessment."
        ),
        "dimensions": [
            {"name": "Instruction Clarity", "score": 5,
             "justification": "Sample: instructions are phased with explicit MUST / MUST NOT rules."},
            {"name": "Behavioral Completeness", "score": 4,
             "justification": "Sample: multi-step flows with fallbacks, uneven exit criteria."},
            {"name": "Example Quality", "score": 4,
             "justification": "Sample: realistic examples and output templates, few end-to-end walkthroughs."},
            {"name": "Robustness", "score": 4,
             "justification": "Sample: anticipates auth and paging failures, limits not standardized."},
            {"name": "Safety And Guardrails", "score": 3,
             "justification": "Sample: local safeguards present, uneven consent patterns."},
            {"name": "User Experience", "score": 5,
             "justification": "Sample: clear entry points, smart defaults, actionable errors."},
        ],
        "improvements": [
            {"file": "SKILL.md",
             "suggestion": "Add a plugin-wide safety note for handling untrusted external content."},
            {"file": "SKILL.md",
             "suggestion": "Standardize confirmation gates for any state-changing step."},
            {"file": "references/",
             "suggestion": "Add explicit execution limits (max items, retries, timeouts) for high-fanout flows."},
        ],
    }


def normalize(result: dict, name: str) -> dict:
    """Validate, clamp, and enrich the judge output for rendering."""
    order = [d for d, _ in RUBRIC]
    by_name = {d.get("name", "").strip(): d for d in result.get("dimensions", [])}
    dims = []
    for dim in order:
        entry = by_name.get(dim, {})
        try:
            score = int(round(float(entry.get("score", 0))))
        except (TypeError, ValueError):
            score = 0
        score = max(1, min(5, score)) if score else 3
        dims.append({
            "name": dim,
            "score": score,
            "justification": entry.get("justification", "No justification returned.").strip(),
        })
    overall = round(sum(d["score"] for d in dims) / len(dims), 1)
    return {
        "skill_name": name,
        "overall": overall,
        "summary": result.get("summary", "").strip(),
        "dimensions": dims,
        "improvements": result.get("improvements", []),
    }


def print_result(data: dict, demo: bool = False) -> None:
    """Print a readable assessment without writing any output files."""
    if demo:
        print("DEMO: sample scores only. No Gemini call was made.\n")
    print(f"Skill: {data['skill_name']}")
    print(f"Overall: {data['overall']} / 5\n")
    if data["summary"]:
        print(data["summary"])
        print()
    for dim in data["dimensions"]:
        print(f"{dim['name']}: {dim['score']} / 5")
        print(f"  {dim['justification']}")
    if data["improvements"]:
        print("\nTop improvements")
        for index, item in enumerate(data["improvements"], 1):
            print(f"{index}. {item.get('file', 'general')}: {item.get('suggestion', '')}")


def main():
    ap = argparse.ArgumentParser(description="Score an agent skill against a 6-dimension quality rubric.")
    ap.add_argument("skill_path", nargs="?", help="Path to a skill folder or SKILL.md file.")
    ap.add_argument("--demo", action="store_true", help="Print sample scores without calling an LLM.")
    ap.add_argument("--model", default=os.environ.get("GEMINI_MODEL", "gemini-flash-latest"),
                    help="Judge model (default: gemini-flash-latest or $GEMINI_MODEL).")
    args = ap.parse_args()

    if args.demo:
        name = "demo-skill"
        files_used = ["SKILL.md", "references/example.md"]
        result = demo_scores()
    else:
        if not args.skill_path:
            ap.error("skill_path is required unless --demo is used.")
        target = Path(args.skill_path).expanduser().resolve()
        name, blob, files_used = read_skill(target)
        print(f"Scoring '{name}' ({len(files_used)} files) with {args.model} ...\n")
        result = score_with_gemini(build_prompt(name, blob), args.model)

    data = normalize(result, name)
    print_result(data, demo=args.demo)


if __name__ == "__main__":
    main()
