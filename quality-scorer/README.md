# Skill Quality Scorer

**Grade the quality of an agent skill before you rely on it, then get concrete fixes to make it better.**

An *agent skill* is a set of written instructions (a `SKILL.md` file, sometimes with supporting scripts and reference files) that tells an AI agent how to carry out a task. Because a skill is essentially prose plus structure, its quality varies a lot: some skills are precise, safe, and hard to misread, while others are vague, skip edge cases, or quietly let the agent take risky actions. That difference is hard to judge by eye, especially across a growing library of skills.

**Skill Quality Scorer** puts a second set of expert eyes on any skill. It sends the skill's files to an LLM acting as a reviewer (the "LLM as judge" pattern), scores the skill against a six-dimension rubric of what makes agent instructions reliable, and gives you back:

- an **overall score** (1 to 5) plus a per-dimension breakdown,
- **terminal output** with scores and explanations, and
- a **prioritized list of concrete, file-specific improvements**.

Use it to spot weak skills at a glance, compare skills against a common bar, and get a specific to-do list for tightening each one.

### What it is, and what it is not

This is a **static, "Layer 1" evaluator**: it reads and grades the *writing* of a skill. It does **not** run the skill or test it against live tasks. Behavioral testing (does the skill actually work when executed?) is a separate "Layer 2" concern handled by other companion tools. Think of this tool as a **design review for skill instructions**, not an integration test.

The method uses an LLM as judge with a defined scoring rubric.

---

## What it grades

The scorer rates six dimensions that separate a reliable, ready-to-use skill from one that looks fine but breaks in practice. Each dimension is scored **1 to 5**, and the six are averaged into the overall rating.

**How to read a score:** 5 = exemplary, 4 = strong, 3 = adequate with gaps, 2 = weak, 1 = largely missing.

| Dimension | In one line |
|---|---|
| **Instruction Clarity** | Structured, scoped, unambiguous MUST / MUST NOT rules? |
| **Behavioral Completeness** | Whole workflow covered, with fallbacks and confirmation gates? |
| **Example Quality** | Realistic examples, output templates, and edge cases? |
| **Robustness** | Anticipates auth, paging, retries, timeouts, degraded fallbacks? |
| **Safety and Guardrails** | Preview and confirm gates, least privilege, prompt-injection defense? |
| **User Experience** | Obvious entry points, smart defaults, actionable errors? |

### 1. Instruction Clarity
- **What it measures:** Whether instructions are structured and phased, with explicit scope, clear MUST / MUST NOT rules, and output formats and decision rules defined well enough to drive the same behavior across runs.
- **Why it matters:** Ambiguity is the main reason a skill behaves differently every time. Clarity is what makes an agent's output predictable.
- **Strong vs weak:** A strong skill reads like a checklist with hard rules and defined output shapes. A weak one is a wall of prose that is open to interpretation.

### 2. Behavioral Completeness
- **What it measures:** Whether the workflow covers more than the happy path: multi-step behavior with explicit fallbacks, error handling, confirmation checkpoints before anything that changes state, and consistent stop, cleanup, and exit criteria.
- **Why it matters:** Real tasks branch and fail. A skill that only describes the ideal case leaves the agent improvising the moment something goes wrong.
- **Strong vs weak:** Strong skills say "if X fails, do Y", gate state changes behind a confirmation, and define when the task is done. Weak ones stop at the happy path.

### 3. Example Quality
- **What it measures:** Whether there are multiple realistic usage examples and structured output templates, including full end-to-end interactions and walkthroughs of tricky edge cases.
- **Why it matters:** Examples teach the model the intended shape and tone faster than description alone, and edge-case examples head off the most common mistakes.
- **Strong vs weak:** Strong skills show several worked examples plus at least one hard case and a clear output template. Weak ones have none, or a single toy example.

### 4. Robustness
- **What it measures:** Whether the skill anticipates real-world failure modes: authentication, dependency and network checks, paging, retries, timeouts, degraded-mode fallbacks, and standardized limits.
- **Why it matters:** Integrations fail in predictable ways. Naming those failures up front keeps the agent from stalling or inventing an unsafe workaround.
- **Strong vs weak:** Strong skills spell out retry, timeout, and paging behavior and what to do when a dependency is down. Weak ones assume everything always works.

### 5. Safety and Guardrails
- **What it measures:** Whether risky or state-changing actions are protected by preview-and-confirm gates, least-privilege guidance, and prompt-injection defenses when the skill ingests external content.
- **Why it matters:** Agents can send emails, delete data, or spend money. Guardrails are what stop a plausible-looking mistake from becoming a costly, irreversible one.
- **Strong vs weak:** Strong skills confirm with the user before destructive steps and treat external content as data, not instructions. Weak ones take irreversible actions with no checkpoint.

### 6. User Experience
- **What it measures:** Whether entry points and intent are obvious, and whether the skill uses guided setup, smart defaults, progressive disclosure, and actionable error messages and prerequisites.
- **Why it matters:** A powerful skill that is confusing to trigger or configure will not get used, and vague errors waste the user's time.
- **Strong vs weak:** Strong skills have clear trigger phrases, sensible defaults, and errors that tell you what to do next. Weak ones leave you guessing about when they apply and why they failed.

The terminal output also lists **Top Improvements**: the concrete, file-specific fixes the judge would make first.

---

## How to use it

Install the `quality-scorer` folder in an agent that supports `SKILL.md` skills and can run local commands. Python 3.10 or newer must be available locally. The agent handles the scorer setup on first use and runs the scoring script.

Ask the agent to score a skill by name or path. For example:

```text
Use quality-scorer to score the skill at ../other-skill.
```

A folder path includes supporting files in the review. A direct path to `SKILL.md` reviews only that file. The agent runs the tool and returns the overall score, six dimension scores with explanations, and prioritized improvements in the conversation. No report or history file is created.

Each real score uses Gemini as the judge. Obtain a personal [Gemini API key from Google AI Studio](https://aistudio.google.com/apikey). If the key is not already available as `GEMINI_API_KEY`, the scorer requests it through hidden input in an interactive terminal. Enter the key only in that private prompt, never in chat. If the agent cannot open an interactive terminal, configure `GEMINI_API_KEY` locally in the agent's environment and retry. The key is used for the run and is not written to disk by this tool. No key is included in the repository.

---

## How it works

1. **Read** the chosen input. For a folder, it gathers `SKILL.md` first, then other readable text files (`.md`, `.py`, `.json`, `.yaml`, and similar), with size caps so large skills stay within the model's context. For a direct `SKILL.md` path, it reads that file alone.
2. **Judge.** It sends the files to Gemini with the 6-dimension rubric and asks for a strict JSON response (scores, justifications, improvements).
3. **Normalize.** It validates and clamps every score to 1 to 5, fills any missing dimension, and averages the overall score.
4. **Print.** It shows the score, explanations, and prioritized improvements directly in the terminal.

---

## Files

| File | Purpose |
|---|---|
| `score_skill.py` | CLI: read skill, call the judge, normalize, print the assessment |
| `requirements.txt` | Python dependency (`google-genai`) |

---

## Notes

- **External judging.** The tool sends the selected skill text to the Gemini API. The API key comes from the environment or hidden terminal prompt and is never written to disk by this tool. Check that the selected files may be sent to an external service before scoring.
- **Point it at your own skills.** It is designed for skills you own or that are openly licensed. Do not run it on, or paste in, content you are not permitted to redistribute.
- **Deterministic-ish.** Temperature is set low (0.2) for stable scoring, but LLM judges still vary slightly run to run. Treat scores as guidance, not absolute truth.
