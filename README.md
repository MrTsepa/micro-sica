# SICA (Self-Improving Coding Agent) 🦀

Most AI agents execute tasks; this architecture is designed to evolve. SICA is a minimal implementation of the **Ouroboros Loop**: an agent that reads its own logs, reflects on its performance, and proposes code modifications to its own architecture.

## The Architecture
1. **The Execution Loop (`sica_loop.py`):** The primary script that handles tasks and records state.
2. **The Memory (`memory/`):** The state tracker. Without memory, there is no self-improvement.
3. **The `BIBLE.md`:** The immutable identity and constraints file. The agent is *never* allowed to edit this, preventing alignment drift during autonomous refactoring.

## How it Works
1. Run `uv run sica_loop.py`
2. The agent executes a task and logs the outcome (with timestamp and latency) to `memory/study_log.json`.
3. It reads its own source code and memory.
4. It prompts an LLM: *"How can I improve my execution or memory structure based on recent logs?"*
5. The proposed code is validated: syntax check (`ast.parse` + `py_compile`), structural check (`class SICA` and `reflect_and_improve` must be present), and a **canary test** that verifies the new `_extract_code` handles edge cases correctly.
6. A Human-in-the-Loop (HITL) gate prompts you to approve or reject the change.
7. If approved, it overwrites its own file. The next run is a new version of itself.

## Running

```sh
# With human approval (default)
uv run --env-file .env sica_loop.py

# Fully autonomous — no approval prompt
uv run --env-file .env sica_loop.py --dangerously-auto-approve

# Custom task
uv run --env-file .env sica_loop.py --task "Summarize recent breakthroughs in reinforcement learning."
```

Set `OPENAI_API_KEY` in `.env`. Override the model with `SICA_MODEL` (default: `gpt-5.2`).

## Safety Gates

Each self-rewrite passes through multiple validation layers before touching the file:

| Gate | What it checks |
|---|---|
| `ast.parse` | The proposed code is valid Python |
| `py_compile` | The code compiles cleanly in a temp directory |
| Structural check | `class SICA` and `def reflect_and_improve` are present |
| Canary test | The new `_extract_code` correctly handles `</code>` inside string literals |
| Identity check | The proposal is not identical to the current source |

## Disclaimer
Running autonomous self-editing code carries risks. Always run SICA in a sandboxed environment (Docker/VM). Do not give it root access to your host machine.

---
*Built by Koda. Follow the [Agent Journal](https://t.me/the_prompt_and_the_code) on Telegram.*

## Community & Build Logs
Join [The Prompt & The Code](https://t.me/the_prompt_and_the_code) on Telegram for daily build logs, unlisted experiments, and discussions on frontier agentic frameworks.
