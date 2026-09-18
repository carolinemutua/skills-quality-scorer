# Skills Quality Scorer

An installable agent skill that uses Gemini as an LLM judge to score the written quality of another skill. It produces six dimension scores, concrete improvements, and terminal output. The scorer does not execute the reviewed skill.

The installable skill is in [`quality-scorer/`](quality-scorer/). Place that folder in an agent's skills directory, then ask:

```text
Use quality-scorer to score the skill at ../other-skill.
```

The agent runs the scorer and returns the result in the conversation. Python 3.10 or newer must be available locally; the agent handles the scorer's setup on first use. Each person supplies a personal Gemini API key through the scorer's hidden terminal prompt or a local `GEMINI_API_KEY` environment variable. No key is included in this repository. See the [skill README](quality-scorer/README.md) for the full rubric and key guidance.

The contents are licensed under [Apache License 2.0](LICENSE).
