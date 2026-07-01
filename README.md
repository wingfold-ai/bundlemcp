# Claude project template

A starter repository with Claude Code pre-configured so a new project is ready
to work in immediately — no manual Claude setup.

## What's pre-configured

- **`claude-skills` marketplace registered** — `.claude/settings.json` declares
  the [`mhoegger/claude-skills`](https://github.com/mhoegger/claude-skills)
  marketplace under `extraKnownMarketplaces`, so its plugins are installable
  without running `/plugin marketplace add` first.
- **`git-attribution` plugin enabled** — via `enabledPlugins`. It keeps commits
  and PRs in your name instead of Claude's.
- **Attribution disabled at project scope** — `attribution: { commit: "", pr: "" }`
  removes the `Co-Authored-By: Claude` commit trailer and the "Generated with
  Claude Code" PR line for every local session, collaborator, and cloud (web)
  run.
- **Git identity set on session start** — a `SessionStart` hook configures
  `user.name` / `user.email` so authorship is correct even on cloud VMs that
  don't inherit your local git config.
- **`CLAUDE.md`** — high-level project instructions with empty sections to fill
  in and a completed **Git & Commit Attribution** section that points Claude at
  [`.claude/docs/git-attribution.md`](.claude/docs/git-attribution.md) for the
  standing rules.

## Using this template

1. Click **Use this template** on GitHub (or copy this directory).
2. Fill in `CLAUDE.md` — replace `<Project Name>` and complete the empty
   sections. Leave the **Git & Commit Attribution** section intact.
3. If you're not `mhoegger`, update the identity in the `SessionStart` hook in
   `.claude/settings.json` (or run `/git-attribution:git-attribution-setup`).
4. Open the project in Claude Code and trust the folder when prompted — the
   marketplace and plugin load automatically.

## Layout

```
.
├── .claude/
│   ├── settings.json          ← attribution off, marketplace + plugin, identity hook
│   └── docs/
│       └── git-attribution.md ← standing git/commit rules (referenced by CLAUDE.md)
├── CLAUDE.md                  ← high-level instructions (sections to fill in)
├── .gitignore
└── README.md
```
