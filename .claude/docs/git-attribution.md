# Git & Commit Attribution

How to handle commits, pull requests and git identity in this repository. These are standing rules for every
contributor and every coding assistant working on their behalf.

## The rule

A commit or pull request lands in the name of the person who made it, never in an assistant's.

- **Do not** add a `Co-Authored-By: Claude <...>` trailer to commit messages.
- **Do not** add a "Generated with Claude Code" line, or any equivalent AI attribution, to commit messages or
  pull-request bodies.
- Write commit messages and PR descriptions as the contributor would, with no AI byline.

The shared `.claude/settings.json` sets Claude Code's `attribution` to empty so it adds none of these on its own.

## Committing and opening pull requests

- Commit with your own git identity. The repository never sets `user.name` or `user.email`; configure them in your
  global git config.
- Only commit or push when the contributor asks. On the default branch, branch first.
- Cloud (web) commits are authored by the contributor but carry no GitHub "Verified" badge, because the sandbox has no
  signing key. Authorship is correct; only the signature is absent.
- Titles and descriptions follow [CONTRIBUTING.md](../../CONTRIBUTING.md#commit-and-pull-request-titles).

## Personal settings stay local

`.claude/settings.json` is shared, so it holds only what applies to everyone. Your own plugins, marketplaces, hooks and
permission rules go in `.claude/settings.local.json`, which git ignores. When you change the shared file, read and merge
it rather than overwriting it.

## Never

- Never write a GitHub token or PAT into a settings file, an environment variable or a hook command. Anything committed
  or exported is visible to others.
