# Step 2 — The Wrong Configuration (Exam Trap)

## What goes wrong

You put team coding standards in your personal user-level config:
 
```
~/.claude/CLAUDE.md   ← lives on YOUR machine only, never in git
```

Contents (wrong location):
```markdown
# Team Standards (WRONG — user-level)
- Always use type hints
- All public functions need docstrings
- Never expose raw exceptions to users
```

## Why this fails

| | You | New teammate |
|---|---|---|
| Has `~/.claude/CLAUDE.md` | ✓ (you wrote it) | ✗ (their machine, clean install) |
| Gets team standards | ✓ | ✗ |
| Code reviews catch the gap | Eventually | After the PR is already broken |

The new teammate clones the repo, opens Claude Code, and gets zero team context.
They use bare exception strings, skip docstrings, write unittest instead of pytest.
The bug only surfaces at code review — not at the point of writing.

## The fix (Step 3)

Move standards into the project, version-controlled:

```
p03-claude-md/
└── .claude/
    └── CLAUDE.md        ← committed to git, cloned by everyone
```

Now every teammate gets the same context automatically on `git clone` / `git pull`.

## Hierarchy (most → least specific)

```
.claude/rules/*.md         path-scoped  (loads only for matching file patterns)
     ↓
src/api/CLAUDE.md          directory-level (loads when editing anything in src/api/)
     ↓
.claude/CLAUDE.md          project-level   (loads for the whole repo — team contract)
     ↓
~/.claude/CLAUDE.md        user-level      (personal, never shared — preferences only)
```

More specific wins when there's a conflict.
User-level is for personal preferences (your editor style, your shortcuts) — never team rules.
