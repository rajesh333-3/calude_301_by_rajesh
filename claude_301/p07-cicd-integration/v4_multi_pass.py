"""
Version 4 — Multi-Pass Review for Large PRs
============================================
Single-pass review of a large PR misses cross-file issues:
  - auth.py generates tokens that orders.py trusts without verification
  - orders.py exposes raw DB errors that leak auth.py's table structure
  - A bug in one file creates a vulnerability in another

Two-pass approach:
  Pass 1 (per-file): independent local analysis of each file
  Pass 2 (integration): cross-file data flow, contradictions, shared state

Pass 2 receives Pass 1 findings as prior context so it doesn't re-report
the same local issues — it focuses on CROSS-FILE patterns only.

Why it works: Pass 2 has the full picture (all files + all local findings)
and is explicitly instructed to look for integration-level issues.
A single pass tends to focus on obvious local bugs and miss subtle interactions.

── OpenAI vs Claude CLI ──────────────────────────────────────────────────────
  Same routing as ci_review.py.
  Key insight: multi-pass is a prompt/architecture pattern, not an API feature.
  It works identically with claude CLI or openai API.
"""

import json
from pathlib import Path
from ci_review import run_review, format_as_pr_comments

SAMPLE_PR = Path(__file__).parent / "sample_pr"


def single_pass_review(files: list[Path]) -> list[dict]:
    """Review all files in one prompt — baseline for comparison."""
    print("── Single-pass review (all files together) ──")
    findings = run_review(files, pass_label="single-pass")
    print(f"  Found {len(findings)} issue(s)")
    return findings


def multi_pass_review(files: list[Path]) -> dict:
    """
    Two-pass review:
      Pass 1: per-file local analysis (parallelizable in real CI)
      Pass 2: cross-file integration analysis with Pass 1 findings as context
    """
    print("── Multi-pass review ──")

    # Pass 1: per-file (each file reviewed independently)
    print("\n  Pass 1: per-file analysis...")
    all_local_findings: list[dict] = []
    for f in files:
        print(f"    Reviewing {f.name}...")
        findings = run_review([f], pass_label=f"pass1:{f.name}")
        for finding in findings:
            finding["pass"] = 1
        all_local_findings.extend(findings)
        print(f"    → {len(findings)} issue(s) in {f.name}")

    print(f"\n  Pass 1 total: {len(all_local_findings)} local issue(s)")

    # Pass 2: integration pass — all files + all local findings as prior context
    # Explicitly scoped to cross-file patterns
    print("\n  Pass 2: cross-file integration analysis...")

    integration_prompt_addition = """
IMPORTANT — Pass 2 scope:
  You already have all local (per-file) findings above as prior context.
  Do NOT re-report those. Focus ONLY on cross-file integration issues:
    - Data flow between files (values produced in one file, trusted in another)
    - Shared state assumptions that are inconsistent across files
    - Security issues that only manifest when files interact
    - Contract violations (one file assumes behavior another doesn't guarantee)
  If you find nothing new, return an empty findings array."""

    integration_findings = run_review(
        files,
        prior_findings=all_local_findings,
        pass_label=f"pass2:integration{integration_prompt_addition}"
    )
    for f in integration_findings:
        f["pass"] = 2
    print(f"  Pass 2 total: {len(integration_findings)} integration issue(s)")

    return {
        "local":       all_local_findings,
        "integration": integration_findings,
        "all":         all_local_findings + integration_findings,
    }


def compare_approaches(files: list[Path]) -> None:
    """Run both approaches and compare findings."""
    print("=== Version 4: Multi-Pass Review ===\n")
    print(f"Files: {[f.name for f in files]}\n")

    # Single pass
    single = single_pass_review(files)

    print()

    # Multi-pass
    multi = multi_pass_review(files)

    # Compare
    print(f"\n── Comparison ──")
    print(f"  Single-pass  : {len(single)} finding(s) total")
    print(f"  Multi-pass   : {len(multi['local'])} local + "
          f"{len(multi['integration'])} integration = {len(multi['all'])} total")

    integration_only = [f for f in multi["integration"]]
    if integration_only:
        print(f"\n  Issues caught ONLY by multi-pass integration pass:")
        for f in integration_only:
            print(f"    [{f.get('severity','?')}] {f.get('file','?')}:{f.get('line','?')} "
                  f"— {f.get('issue','')[:70]}")
    else:
        print("\n  [Note] Integration pass found no additional issues on this small PR.")
        print("  In a 14+ file PR, cross-file interactions are more likely to surface.")

    print(f"\n── PR Comment (multi-pass, all findings) ──")
    print(format_as_pr_comments(multi["all"]))

    print(f"\n── When to use multi-pass ──")
    print("  PR with 5+ files touching shared state, auth, or data pipelines")
    print("  Monorepo changes that span multiple services")
    print("  Any change where a local fix might break a cross-module contract")
    print("  Pass 1 is parallelizable — each file can be reviewed concurrently")
    print("  Pass 2 is sequential — needs all Pass 1 findings as input")


def main():
    files = sorted(SAMPLE_PR.glob("*.py"))
    if not files:
        print(f"No Python files found in {SAMPLE_PR}")
        return
    compare_approaches(files)


if __name__ == "__main__":
    main()
