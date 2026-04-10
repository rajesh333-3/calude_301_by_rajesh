"""
CI Review Pipeline — Core Module
=================================
Two modes:

  MODE A: Claude Code CLI (`claude -p`)
    Uses the `claude` terminal tool with --output-format json.
    Requires: claude CLI installed + ANTHROPIC_API_KEY set.
    This is what real CI pipelines use.

  MODE B: OpenAI API fallback
    Uses openai.OpenAI() directly when claude CLI is not available.
    Produces the same JSON schema output.
    Requires: OPENAI_API_KEY set.

Both modes produce the same review_schema.json output format.
The pipeline code (multi-pass, duplicate prevention, etc.) works with either.

── Claude Code CLI vs OpenAI API ─────────────────────────────────────────────
  CLAUDE CLI (preferred in CI):
    subprocess.run(["claude", "-p", prompt, "--output-format", "json"])
    → Non-interactive, structured output, exits cleanly
    → Native Claude Code tools available (Read, Grep, Glob on repo files)

  OPENAI API (fallback):
    client.chat.completions.create(model="gpt-4o", ...)
    → Same review logic, no CLI dependency
    → Files must be passed as text content (no file-system tool access)
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

SCHEMA_PATH = Path(__file__).parent / "review_schema.json"
SAMPLE_PR   = Path(__file__).parent / "sample_pr"


# ── Mode detection ─────────────────────────────────────────────────────────────
def claude_cli_available() -> bool:
    """Check if `claude` CLI is installed and ANTHROPIC_API_KEY is set."""
    try:
        result = subprocess.run(["claude", "--version"],
                                capture_output=True, text=True, timeout=5)
        return result.returncode == 0 and bool(os.getenv("ANTHROPIC_API_KEY"))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ── Mode A: Claude Code CLI ────────────────────────────────────────────────────
def review_with_claude_cli(
    files: list[Path],
    prior_findings: list | None = None,
    pass_label: str = "single"
) -> list[dict]:
    """
    Run claude -p with structured JSON output.

    Key flags:
      -p                      → non-interactive (REQUIRED in CI)
      --output-format json    → machine-parseable output
      --model                 → pin model version for reproducibility

    CLAUDE: native file access via Read/Grep tools — no need to embed file content.
    """
    prior_block = ""
    if prior_findings:
        prior_block = (
            f"\n\nPRIOR REVIEW FINDINGS (do NOT re-report these unless still present):\n"
            f"{json.dumps(prior_findings, indent=2)}\n\n"
            f"Report ONLY new or still-unaddressed issues."
        )

    file_list = ", ".join(str(f.relative_to(Path.cwd())) for f in files)

    prompt = f"""Review these files for security vulnerabilities, bugs, and correctness issues.
Files: {file_list}
Pass: {pass_label}
{prior_block}
Return a JSON object matching this schema:
{SCHEMA_PATH.read_text()}

For each finding include: file, line number, severity (critical/high/medium/low),
category (security/correctness/performance/style/maintainability), issue description,
and a specific recommendation.
Set summary.pass = false if any critical or high findings exist."""

    result = subprocess.run(
        [
            "claude",
            "-p",                           # NON-INTERACTIVE — required for CI
            prompt,
            "--output-format", "json",      # machine-parseable
            "--model", "claude-opus-4-6",   # pin model for reproducibility
        ],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(Path(__file__).parent)
    )

    if result.returncode != 0:
        print(f"  [claude-cli] Error: {result.stderr[:200]}", file=sys.stderr)
        return []

    try:
        data = json.loads(result.stdout)
        return data.get("findings", [])
    except json.JSONDecodeError as e:
        print(f"  [claude-cli] JSON parse error: {e}", file=sys.stderr)
        return []


# ── Mode B: OpenAI API fallback ───────────────────────────────────────────────
def review_with_openai(
    files: list[Path],
    prior_findings: list | None = None,
    pass_label: str = "single"
) -> list[dict]:
    """
    OpenAI fallback: embed file content in the prompt, parse JSON from response.

    OPENAI vs CLAUDE differences:
      - Files are read and embedded as text (no native file-system tool access)
      - Output is in message.content as a JSON string, not structured output
      - Uses response_format={"type":"json_object"} for JSON mode
    """
    client = OpenAI()

    # Embed file contents (OpenAI has no file-system tool access in basic mode)
    file_blocks = []
    for f in files:
        try:
            content = f.read_text()
            file_blocks.append(f"=== {f.name} ===\n{content}")
        except Exception as e:
            file_blocks.append(f"=== {f.name} ===\n[Error reading file: {e}]")

    prior_block = ""
    if prior_findings:
        prior_block = (
            f"\n\nPRIOR REVIEW FINDINGS (do NOT re-report unless still present):\n"
            f"{json.dumps(prior_findings, indent=2)}\n\n"
            f"Report ONLY new or still-unaddressed issues."
        )

    prompt = f"""Review the following source files for security vulnerabilities, bugs, and correctness issues.
Pass: {pass_label}
{prior_block}

{chr(10).join(file_blocks)}

Return a JSON object with this exact structure:
{{
  "findings": [
    {{
      "file": "filename.py",
      "line": 22,
      "severity": "critical",
      "category": "security",
      "issue": "Clear description of the problem",
      "recommendation": "Specific fix",
      "is_new": true
    }}
  ],
  "summary": {{
    "total_findings": 5,
    "critical_count": 1,
    "high_count": 2,
    "medium_count": 1,
    "low_count": 1,
    "pass": false,
    "notes": "Optional notes"
  }}
}}

Set summary.pass = false if any critical or high findings exist.
Return ONLY the JSON object, no markdown fences."""

    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=2048,
        response_format={"type": "json_object"},  # JSON mode — no markdown wrapping
        messages=[
            {"role": "system",
             "content": "You are a security-focused code reviewer. Return only valid JSON."},
            {"role": "user", "content": prompt}
        ]
    )

    try:
        data = json.loads(response.choices[0].message.content)
        return data.get("findings", [])
    except json.JSONDecodeError as e:
        print(f"  [openai] JSON parse error: {e}", file=sys.stderr)
        return []


# ── Unified interface ──────────────────────────────────────────────────────────
def run_review(
    files: list[Path],
    prior_findings: list | None = None,
    pass_label: str = "single"
) -> list[dict]:
    """
    Route to Claude CLI or OpenAI fallback based on availability.
    Both return the same list[Finding] format.
    """
    if claude_cli_available():
        print(f"  [mode] Claude Code CLI (claude -p)")
        return review_with_claude_cli(files, prior_findings, pass_label)
    else:
        print(f"  [mode] OpenAI API fallback (claude CLI not available)")
        return review_with_openai(files, prior_findings, pass_label)


# ── Format findings as PR comments ────────────────────────────────────────────
def format_as_pr_comments(findings: list[dict]) -> str:
    """Format findings as inline PR review comments."""
    if not findings:
        return "✓ No issues found."

    lines = ["## Automated Code Review\n"]
    by_severity = {"critical": [], "high": [], "medium": [], "low": []}
    for f in findings:
        by_severity.get(f.get("severity", "low"), []).append(f)

    icons = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}

    for severity in ("critical", "high", "medium", "low"):
        group = by_severity[severity]
        if not group:
            continue
        lines.append(f"### {icons[severity]} {severity.upper()} ({len(group)})\n")
        for finding in group:
            new_tag = " `[NEW]`" if finding.get("is_new", True) else ""
            lines.append(
                f"**{finding['file']}:{finding.get('line', '?')}**{new_tag}  \n"
                f"**Issue:** {finding['issue']}  \n"
                f"**Fix:** {finding['recommendation']}  \n"
            )

    total    = len(findings)
    critical = len(by_severity["critical"])
    high     = len(by_severity["high"])
    status   = "❌ FAIL" if (critical + high) > 0 else "✅ PASS"
    lines.append(f"\n---\n**{status}** — {total} finding(s), "
                 f"{critical} critical, {high} high")
    return "\n".join(lines)


# ── Main demo ──────────────────────────────────────────────────────────────────
def main():
    print("=== CI Review Pipeline ===\n")

    files = sorted(SAMPLE_PR.glob("*.py"))
    if not files:
        print(f"No Python files found in {SAMPLE_PR}")
        return

    print(f"Reviewing {len(files)} file(s): {[f.name for f in files]}\n")

    findings = run_review(files, pass_label="full-review")

    print(f"\nFound {len(findings)} issue(s):\n")
    print(format_as_pr_comments(findings))

    # Save findings for use in duplicate-prevention demo (v3)
    output = Path(__file__).parent / "prior_findings.json"
    output.write_text(json.dumps(findings, indent=2))
    print(f"\n[saved] {output} — use in v3_duplicate_prevention.py")


if __name__ == "__main__":
    main()
