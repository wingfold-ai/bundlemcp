# Git & Commit Attribution

How to handle commits, pull requests, and git identity while working in this
repository. Follow these continuously — they are the standing rules, not setup.

## The rule

Commits and PRs land in the **user's name**, never Claude's.

- **Do not** add a `Co-Authored-By: Claude <...>` trailer to commit messages.
- **Do not** add the "Generated with Claude Code" line (or any equivalent AI
  attribution) to commit messages or pull-request bodies.
- Write commit messages and PR descriptions as the user would — no AI byline.

## Committing & opening PRs

- Commit normally; append no attribution trailer or footer.
- Only commit or push when the user asks. If on the default branch, branch
  first.
- Cloud (web) commits are **authored** by the user but will **not** carry
  GitHub's "Verified" badge — there's no signing key in the sandbox. Authorship
  is correct; only the cryptographic signature is absent. This is expected, not
  a bug to fix.

## Never

- Never write a GitHub token / PAT into `settings.json`, environment variables,
  or a hook command — anything committed or in the environment is visible to
  others. No token is needed: cloud pushes go through Anthropic's GitHub proxy
  with scoped credentials.
- Never clobber `.claude/settings.json`. If you must change it, read and merge —
  preserve the `attribution`, `enabledPlugins`, and `hooks` blocks.

## Reconfiguring

To change identity or re-run the full setup (including user-global scope), use
the marketplace skill:

```
/git-attribution:git-attribution-setup
```
