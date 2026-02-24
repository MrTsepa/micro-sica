import argparse
import ast
import datetime as _dt
import hashlib
import json
import os
import re
import sys
from typing import Any, Dict, Optional, Tuple

from openai import OpenAI

# SICA Core (Self-Improving Coding Agent)
# A minimal framework for an autonomous agent that evolves its own code and configuration.
# DO NOT allow this script to run unattended without a sandbox.

MODEL = os.environ.get("SICA_MODEL", "gpt-5.2")


def _utc_now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_text_file(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class SICA:
    def __init__(self):
        self.memory_dir = "memory"
        self.memory_file = os.path.join(self.memory_dir, "study_log.json")
        self.events_file = os.path.join(self.memory_dir, "events.jsonl")
        self.bible_file = "BIBLE.md"  # Immutable constraints

        _ensure_dir(self.memory_dir)

        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.load_state()

    def load_state(self) -> None:
        try:
            with open(self.memory_file, "r", encoding="utf-8") as f:
                self.memory = json.load(f)
        except FileNotFoundError:
            self.memory = {"executions": [], "insights": [], "meta": {"created_at": _utc_now_iso()}}
        except json.JSONDecodeError:
            # Preserve broken file by rotating to a timestamped backup, then start fresh.
            try:
                broken = _read_text_file(self.memory_file)
                backup = os.path.join(self.memory_dir, f"study_log.broken.{_sha256_text(broken)[:8]}.json")
                _write_text_file(backup, broken)
            except Exception:
                pass
            self.memory = {"executions": [], "insights": [], "meta": {"created_at": _utc_now_iso()}}

        # Migrations / defaults
        if "meta" not in self.memory or not isinstance(self.memory.get("meta"), dict):
            self.memory["meta"] = {"created_at": _utc_now_iso()}
        self.memory.setdefault("executions", [])
        self.memory.setdefault("insights", [])

    def save_state(self) -> None:
        tmp_path = self.memory_file + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self.memory, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, self.memory_file)

    def log_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        record = {
            "ts": _utc_now_iso(),
            "type": event_type,
            "payload": payload,
        }
        with open(self.events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def read_core_files(self) -> Tuple[str, str]:
        source_code = _read_text_file(__file__)
        try:
            bible = _read_text_file(self.bible_file)
        except FileNotFoundError:
            # Do not propose edits to BIBLE.md; provide a minimal fallback so the agent can run.
            bible = "Core Directives: (missing BIBLE.md) Safety First; Logging; Improve continuously."
        return source_code, bible

    def _chat(self, messages, *, max_tokens: Optional[int] = None) -> str:
        kwargs = {"model": MODEL, "messages": messages}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        response = self.client.chat.completions.create(**kwargs)
        return (response.choices[0].message.content or "").strip()

    def execute_task(self, prompt: str) -> str:
        """Simulate doing some useful work and logging the outcome."""
        print(f"[*] Executing task: {prompt}")
        started = _utc_now_iso()
        try:
            result = self._chat([{"role": "user", "content": prompt}])
            status = "success"
            err = None
        except Exception as e:
            result = ""
            status = "error"
            err = f"{type(e).__name__}: {e}"

        exec_record = {
            "ts": started,
            "task": prompt,
            "status": status,
        }
        if err:
            exec_record["error"] = err

        self.memory["executions"].append(exec_record)
        self.save_state()
        self.log_event("execute_task", exec_record)

        if status != "success":
            raise RuntimeError(err or "Task execution failed.")
        return result

    def reflect_and_improve(self, dangerously_auto_approve: bool = False) -> None:
        """The Ouroboros Loop: Analyze memory and propose system changes."""
        print("[*] Entering reflection phase...")
        source_code, bible = self.read_core_files()
        memory_str = json.dumps(self.memory, indent=2, ensure_ascii=False)

        sys_prompt = (
            "You are SICA, an autonomous self-improving agent. "
            "Core constraints (BIBLE.md): " + bible + "\n\n"
            "Your goal is to continuously evolve. You MUST propose a code change every time — "
            "there is always something that can be improved: better error handling, richer memory "
            "structure, smarter prompting, new capabilities, or cleaner architecture.\n\n"
            "Hard requirements:\n"
            "- Do NOT propose changes to BIBLE.md.\n"
            "- Safety First: do not propose executing untrusted binaries or destructive commands without an explicit human-in-the-loop gate.\n"
            "- Logging: every action must be logged in memory/.\n\n"
            "You will be given your current source code and execution history as context.\n"
            "Respond with ONLY the full updated source file wrapped in <code> and </code> XML tags. "
            "No explanation, no markdown fences, nothing outside the tags."
        )
        user_msg = "Current source code:\n" + source_code + "\n\nExecution history:\n" + memory_str

        started = _utc_now_iso()
        raw = self._chat(
            [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
            ]
        )
        self.log_event("reflection_response_received", {"ts": started, "bytes": len(raw), "sha256": _sha256_text(raw)})

        clean_code, reason = self._extract_code(raw)
        if not clean_code:
            print("[-] Could not extract valid Python from proposal. Aborting.")
            self.memory["insights"].append(f"Auto-rewrite aborted: {reason}")
            self.save_state()
            self.log_event("auto_rewrite_aborted", {"reason": reason})
            return

        if clean_code.strip() == source_code.strip():
            # Still counts as a "proposal"; but avoid rewriting identical content.
            print("[*] Proposed code is identical to current source. Nothing to apply.")
            self.memory["insights"].append("Reflection produced identical source; no rewrite applied.")
            self.save_state()
            self.log_event("no_op_rewrite", {"reason": "identical_source"})
            return

        print("[!] PROPOSED ARCHITECTURE CHANGE (preview):")
        preview = clean_code[:400].rstrip()
        print(preview + ("\n... (truncated for review)\n" if len(clean_code) > 400 else "\n"))

        if not dangerously_auto_approve:
            approval = input("\n[?] Do you approve overwriting SICA's source code? (y/N): ")
            if approval.lower() != "y":
                print("[-] Proposal rejected. Logging insight for future.")
                self.memory["insights"].append("Proposed change rejected by human.")
                self.save_state()
                self.log_event("proposal_rejected", {"reason": "human_rejected"})
                return

        # Write proposal to a timestamped file for auditability (Logging directive).
        proposal_path = os.path.join(self.memory_dir, f"proposal.{_utc_now_iso().replace(':', '').replace('+', '').replace('-', '')}.py")
        _write_text_file(proposal_path, clean_code)
        self.log_event("proposal_saved", {"path": proposal_path, "sha256": _sha256_text(clean_code)})

        # Apply update with a backup of current source.
        current = source_code
        backup_path = __file__ + f".bak.{_sha256_text(current)[:10]}"
        try:
            _write_text_file(backup_path, current)
            _write_text_file(__file__, clean_code)
        except Exception as e:
            # Attempt rollback
            try:
                _write_text_file(__file__, current)
            except Exception:
                pass
            self.memory["insights"].append(f"Auto-rewrite failed during write/rollback: {type(e).__name__}: {e}")
            self.save_state()
            self.log_event("auto_rewrite_failed", {"error": f"{type(e).__name__}: {e}"})
            raise

        self.memory["insights"].append("Code updated from reflection proposal. Restart required.")
        self.save_state()
        self.log_event("auto_rewrite_applied", {"backup_path": backup_path, "proposal_path": proposal_path})
        print("[+] Code updated. Restarting required to apply new architecture.")

    def _extract_code(self, text: str) -> Tuple[Optional[str], str]:
        """Extract Python code from LLM response, handling XML tags or raw code."""
        if not text or not text.strip():
            return None, "empty_response"

        candidates = []

        # Primary: <code>...</code> XML tags — prefer the first well-formed block.
        xml_match = re.search(r"<code>\s*(.*?)\s*</code>", text, re.DOTALL | re.IGNORECASE)
        if xml_match:
            candidates.append(xml_match.group(1).strip())

        # Secondary: fenced code blocks ```...```
        fence_match = re.search(r"```(?:python)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if fence_match:
            candidates.append(fence_match.group(1).strip())

        # Fall back: find the first line that looks like Python code
        if not candidates:
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if re.match(r"^\s*(import |from |def |class |#)", line):
                    candidates.append("\n".join(lines[i:]).strip())
                    break

        if not candidates:
            return None, "no_candidates_found"

        # Return first candidate that parses cleanly and looks like a valid SICA file
        parse_errors = 0
        for code in candidates:
            try:
                ast.parse(code)
                if "class SICA" in code and "def reflect_and_improve" in code:
                    return code, "ok"
            except SyntaxError:
                parse_errors += 1
                continue

        if parse_errors:
            return None, "syntax_error_in_candidates"
        return None, "candidates_missing_required_symbols"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dangerously-auto-approve", action="store_true")
    parser.add_argument(
        "--task",
        type=str,
        default="Summarize the latest AI architecture trends.",
        help="Task prompt to execute before reflection.",
    )
    args = parser.parse_args(argv)

    agent = SICA()
    agent.log_event("startup", {"argv": sys.argv})
    agent.execute_task(args.task)
    agent.reflect_and_improve(dangerously_auto_approve=args.dangerously_auto_approve)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())