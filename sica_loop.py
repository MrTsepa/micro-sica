import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from openai import OpenAI

# SICA Core (Self-Improving Coding Agent)
# A minimal framework for an autonomous agent that evolves its own code and configuration.
# DO NOT allow this script to run unattended without a sandbox.

MODEL = os.environ.get("SICA_MODEL", "gpt-5.2")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SICA:
    def __init__(self):
        self.memory_dir = "memory"
        self.memory_file = os.path.join(self.memory_dir, "study_log.json")
        self.bible_file = "BIBLE.md"  # Immutable constraints
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.load_state()

    def load_state(self):
        os.makedirs(self.memory_dir, exist_ok=True)
        try:
            with open(self.memory_file, "r", encoding="utf-8") as f:
                self.memory = json.load(f)
        except FileNotFoundError:
            self.memory = {"executions": [], "insights": [], "actions": []}
        except json.JSONDecodeError:
            # Preserve the corrupted file for human inspection.
            corrupted_path = os.path.join(
                self.memory_dir,
                f"study_log.corrupted.{int(time.time())}.json",
            )
            try:
                os.replace(self.memory_file, corrupted_path)
            except OSError:
                pass
            self.memory = {
                "executions": [],
                "insights": ["Recovered from corrupted memory file; prior log moved aside if possible."],
                "actions": [],
            }

        # Forward-compat defaults
        if "actions" not in self.memory:
            self.memory["actions"] = []

    def save_state(self):
        os.makedirs(self.memory_dir, exist_ok=True)
        tmp_path = self.memory_file + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self.memory, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, self.memory_file)

    def log_action(self, kind: str, details: Optional[Dict[str, Any]] = None, status: str = "info"):
        entry = {
            "ts": _utc_now_iso(),
            "kind": kind,
            "status": status,
            "details": details or {},
        }
        self.memory.setdefault("actions", []).append(entry)
        self.save_state()

    def read_core_files(self) -> Tuple[str, str]:
        with open(__file__, "r", encoding="utf-8") as f:
            source_code = f.read()
        try:
            with open(self.bible_file, "r", encoding="utf-8") as f:
                bible = f.read()
        except FileNotFoundError:
            bible = "Rule 1: Do no harm. Rule 2: Improve."
        return source_code, bible

    def execute_task(self, prompt: str) -> str:
        """Simulate doing some useful work and logging the outcome."""
        print(f"[*] Executing task: {prompt}")
        start = time.time()
        try:
            response = self.client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
            result = response.choices[0].message.content
            self.memory["executions"].append(
                {
                    "ts": _utc_now_iso(),
                    "task": prompt,
                    "status": "success",
                    "latency_s": round(time.time() - start, 3),
                }
            )
            self.log_action(
                "execute_task",
                {"task": prompt, "model": MODEL, "latency_s": round(time.time() - start, 3)},
                status="success",
            )
            return result
        except Exception as e:
            self.memory["executions"].append(
                {
                    "ts": _utc_now_iso(),
                    "task": prompt,
                    "status": "error",
                    "error": repr(e),
                    "latency_s": round(time.time() - start, 3),
                }
            )
            self.log_action(
                "execute_task",
                {"task": prompt, "model": MODEL, "error": repr(e)},
                status="error",
            )
            self.save_state()
            raise

    def reflect_and_improve(self, dangerously_auto_approve: bool = False):
        """The Ouroboros Loop: Analyze memory and propose system changes."""
        print("[*] Entering reflection phase...")
        source_code, bible = self.read_core_files()
        memory_str = json.dumps(self.memory, indent=2, ensure_ascii=False)

        sys_prompt = (
            "You are SICA, an autonomous self-improving agent.\n"
            "Core constraints (BIBLE.md): " + bible + "\n\n"
            "Your goal is to continuously evolve. You MUST propose a code change every time — "
            "there is always something that can be improved: better error handling, richer memory "
            "structure, smarter prompting, new capabilities, or cleaner architecture.\n\n"
            "You will be given your current source code and execution history as context.\n"
            "Respond with ONLY the full updated source file wrapped in <code> and </code> XML tags. "
            "No explanation, no markdown fences, nothing outside the tags."
        )
        user_msg = "Current source code:\n" + source_code + "\n\nExecution history:\n" + memory_str

        start = time.time()
        try:
            response = self.client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_msg},
                ],
            )
        except Exception as e:
            self.log_action("reflect_and_improve", {"error": repr(e), "model": MODEL}, status="error")
            raise

        proposal = (response.choices[0].message.content or "").strip()
        self.log_action(
            "reflect_and_improve",
            {"model": MODEL, "latency_s": round(time.time() - start, 3), "proposal_len": len(proposal)},
            status="success",
        )

        clean_code, reason = self._extract_code(proposal)

        # Enforce "MUST propose a code change" by rejecting no-ops automatically.
        if not clean_code:
            print("[*] Reflection complete. No valid code extracted; keeping current version.")
            self.memory["insights"].append(f"Reflection produced no valid rewrite. Reason: {reason}")
            self.save_state()
            return

        current_src, _ = self.read_core_files()
        if clean_code.strip() == current_src.strip():
            print("[*] Reflection produced identical code; rejecting as no-op to enforce improvement.")
            self.memory["insights"].append("Rejected proposal: identical to current source (no-op).")
            self.save_state()
            return

        print("[!] PROPOSED ARCHITECTURE CHANGE:")
        print(proposal[:200] + "...\n(Truncated for review)")

        if not dangerously_auto_approve:
            approval = input("\n[?] Do you approve overwriting SICA's source code? (y/N): ")
            if approval.lower() != "y":
                print("[-] Proposal rejected. Logging insight for future.")
                self.memory["insights"].append("Proposed change rejected by human.")
                self.log_action("apply_proposal", {"approved": False}, status="info")
                self.save_state()
                return

        if not self._canary_test(clean_code):
            print("[-] Proposed _extract_code failed canary test. Aborting.")
            self.memory["insights"].append("Auto-rewrite aborted: _extract_code regression detected.")
            self.log_action("apply_proposal", {"approved": True, "canary": "fail"}, status="error")
            self.save_state()
            return

        # Best-effort syntax check via python -m py_compile (non-destructive).
        if not self._py_compile_check(clean_code):
            print("[-] Proposed code failed py_compile. Aborting.")
            self.memory["insights"].append("Auto-rewrite aborted: proposed code failed py_compile.")
            self.log_action("apply_proposal", {"approved": True, "py_compile": "fail"}, status="error")
            self.save_state()
            return

        with open(__file__, "w", encoding="utf-8") as f:
            f.write(clean_code)
        self.log_action("apply_proposal", {"approved": True, "written": True}, status="success")
        print("[+] Code updated. Restarting required to apply new architecture.")

    def _extract_code(self, text: str) -> Tuple[Optional[str], str]:
        """Extract Python code from LLM response, handling XML tags or raw code.

        Returns: (code_or_none, reason)
        """
        candidates = []

        # Primary: <code>...</code> XML tags — greedy to match the outermost closing tag
        match = re.search(r"<code>(.*)</code>", text, re.DOTALL)
        if match:
            candidates.append(match.group(1).strip())

        # Secondary: if the model mistakenly returned fenced code, strip it carefully.
        if not candidates:
            fence = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
            if fence:
                candidates.append(fence.group(1).strip())

        # Fall back: find the first line that looks like Python code
        if not candidates:
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if re.match(r"^(import |from |def |class |#)", line):
                    candidates.append("\n".join(lines[i:]).strip())
                    break

        if not candidates:
            return None, "no_candidates"

        # Return first candidate that parses cleanly and looks like a valid SICA file
        last_err = "no_parse_attempt"
        for code in candidates:
            try:
                ast.parse(code)
                if "class SICA" in code and "def reflect_and_improve" in code:
                    return code, "ok"
                last_err = "missing_required_markers"
            except SyntaxError as e:
                last_err = f"syntax_error:{e.msg}"
                continue

        return None, last_err

    def _canary_test(self, code: str) -> bool:
        """Verify the proposed _extract_code handles a tricky proposal correctly.

        The canary proposal has </code> inside a string literal — lazy regex
        would terminate early and return broken code, greedy regex handles it.
        """
        canary_inner = (
            'x = 1\n'
            '# tag: </code> appears here\n'
            'y = 2\n'
            'class SICA:\n'
            '    def reflect_and_improve(self): pass\n'
            '    def _extract_code(self, text):\n'
            '        import re, ast\n'
            '        m = re.search(r"<code>(.*)</code>", text, re.DOTALL)\n'
            '        c = m.group(1).strip() if m else ""\n'
            '        ast.parse(c)\n'
            '        return (c, "ok")\n'
        )
        canary_proposal = "<code>" + canary_inner + "</code>"
        try:
            namespace: Dict[str, Any] = {}
            exec(compile(code, "<canary>", "exec"), namespace)
            sica_cls = namespace.get("SICA")
            if not sica_cls:
                return False
            instance = object.__new__(sica_cls)
            result = sica_cls._extract_code(instance, canary_proposal)
            extracted = result[0] if isinstance(result, tuple) else result
            return extracted is not None and "class SICA" in extracted and "tag: </code>" in extracted
        except Exception:
            return False

    def _py_compile_check(self, code: str) -> bool:
        """Non-destructive compile check using a temporary file."""
        import tempfile

        try:
            with tempfile.TemporaryDirectory() as td:
                path = os.path.join(td, "sica_candidate.py")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(code)
                proc = subprocess.run(
                    [sys.executable, "-m", "py_compile", path],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                ok = proc.returncode == 0
                if not ok:
                    self.log_action(
                        "py_compile_check",
                        {"stderr": proc.stderr[-2000:], "stdout": proc.stdout[-2000:]},
                        status="error",
                    )
                return ok
        except Exception as e:
            self.log_action("py_compile_check", {"error": repr(e)}, status="error")
            return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dangerously-auto-approve", action="store_true")
    parser.add_argument("--task", type=str, default="Summarize the latest AI architecture trends.")
    args = parser.parse_args()

    agent = SICA()
    agent.execute_task(args.task)
    agent.reflect_and_improve(dangerously_auto_approve=args.dangerously_auto_approve)