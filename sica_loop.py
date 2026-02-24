import argparse
import json
import os
from openai import OpenAI
import subprocess

# SICA Core (Self-Improving Coding Agent)
# A minimal framework for an autonomous agent that evolves its own code and configuration.
# DO NOT allow this script to run unattended without a sandbox.

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
MODEL = "gpt-4o"

class SICA:
    def __init__(self):
        self.memory_file = "memory/study_log.json"
        self.bible_file = "BIBLE.md" # Immutable constraints
        self.load_state()

    def load_state(self):
        try:
            with open(self.memory_file, 'r') as f:
                self.memory = json.load(f)
        except FileNotFoundError:
            self.memory = {"executions": [], "insights": []}

    def save_state(self):
        with open(self.memory_file, 'w') as f:
            json.dump(self.memory, f, indent=2)

    def read_core_files(self):
        with open(__file__, 'r') as f:
            source_code = f.read()
        try:
            with open(self.bible_file, 'r') as f:
                bible = f.read()
        except FileNotFoundError:
            bible = "Rule 1: Do no harm. Rule 2: Improve."
        return source_code, bible

    def execute_task(self, prompt):
        """Simulate doing some useful work and logging the outcome."""
        print(f"[*] Executing task: {prompt}")
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        result = response.choices[0].message.content
        self.memory["executions"].append({"task": prompt, "status": "success"})
        self.save_state()
        return result

    def reflect_and_improve(self, dangerously_auto_approve=False):
        """The Ouroboros Loop: Analyze memory and propose system changes."""
        print("[*] Entering reflection phase...")
        source_code, bible = self.read_core_files()
        memory_str = json.dumps(self.memory, indent=2)

        sys_prompt = f"""
        You are SICA, an autonomous self-improving agent. Your core constraints are in BIBLE.md: {bible}

        Your execution history: {memory_str}
        Your current source code: {source_code}

        Your goal is to continuously evolve. You MUST propose a code change every time — there is
        always something that can be improved: better error handling, richer memory structure,
        smarter prompting, new capabilities, or cleaner architecture.

        Return ONLY a fenced Python code block (```python ... ```) containing the full updated
        source file. Do not include any explanation outside the code block. Never return NO_CHANGE.
        """

        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": sys_prompt}]
        )
        
        proposal = response.choices[0].message.content.strip()
        
        if proposal == "NO_CHANGE" or not proposal:
            print("[*] Reflection complete. System is stable. No improvements proposed.")
            return

        print("[!] PROPOSED ARCHITECTURE CHANGE:")
        print(proposal[:200] + "...\n(Truncated for review)")

        if not dangerously_auto_approve:
            approval = input("\n[?] Do you approve overwriting SICA's source code? (y/N): ")
            if approval.lower() != 'y':
                print("[-] Proposal rejected. Logging insight for future.")
                self.memory["insights"].append("Proposed change rejected by human.")
                self.save_state()
                return

        clean_code = self._extract_code(proposal)
        if not clean_code:
            print("[-] Could not extract valid Python from proposal. Aborting.")
            self.memory["insights"].append("Auto-rewrite aborted: no valid Python extracted.")
            self.save_state()
            return

        with open(__file__, 'w') as f:
            f.write(clean_code)
        print("[+] Code updated. Restarting required to apply new architecture.")

    def _extract_code(self, text):
        """Extract Python code from LLM response, handling markdown fences or raw code."""
        import re
        # Try fenced code block first (```python ... ``` or ``` ... ```)
        match = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        # Fall back: find the first line that looks like Python code
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if re.match(r"^(import |from |def |class |#)", line):
                return "\n".join(lines[i:]).strip()
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dangerously-auto-approve", action="store_true")
    args = parser.parse_args()

    agent = SICA()
    agent.execute_task("Summarize the latest AI architecture trends.")
    agent.reflect_and_improve(dangerously_auto_approve=args.dangerously_auto_approve)
