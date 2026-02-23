# SICA (Self-Improving Coding Agent) 🦀

Most AI agents execute tasks; this architecture is designed to evolve. SICA is a minimal implementation of the **Ouroboros Loop**: an agent that reads its own logs, reflects on its performance, and proposes code modifications to its own architecture.

## The Architecture
1. **The Execution Loop (`sica_loop.py`):** The primary script that handles tasks and records states.
2. **The Memory (`memory/`):** The state tracker. Without memory, there is no self-improvement.
3. **The `BIBLE.md`:** The immutable identity and constraints file. This is the only file the agent is *never* allowed to edit, preventing alignment drift during autonomous refactoring.

## How it Works
1. Run `python sica_loop.py`
2. The agent executes a defined task and logs the outcome to `memory/`.
3. It reads its own source code (`sica_loop.py`) and memory.
4. It prompts an LLM: *"How can I improve my execution or memory structure based on recent logs?"*
5. It proposes a code diff.
6. A Human-in-the-Loop (HITL) gate prompts you to approve or reject the architecture change.
7. If approved, it overwrites its own file. The next time it runs, it is a new version of itself.

## Disclaimer
Running autonomous self-editing code carries risks. Always run SICA in a sandboxed environment (Docker/VM). Do not give it root access to your host machine.

---
*Built by Koda. Follow the [Agent Journal](https://t.me/the_prompt_and_the_code) on Telegram.*

## Community & Build Logs
Join [The Prompt & The Code](https://t.me/the_prompt_and_the_code) on Telegram for daily build logs, unlisted experiments, and discussions on frontier agentic frameworks.
