# Contributing to bundlemcp

Thanks for taking the time to contribute. This guide explains how to report
problems, propose changes and get a pull request merged.

## Ways to contribute

- **Report a bug** with the bug report form in the issue tracker.
- **Suggest a feature** with the feature request form. For open-ended ideas or
  questions, open an issue describing the problem you want to solve first.
- **Improve the documentation.** Small fixes need no issue first.
- **Fix an issue.** Issues labelled `good first issue` are a good place to start;
  `help wanted` marks work the maintainers would like help with.

Security problems are the exception: never open a public issue for them. Follow
[SECURITY.md](SECURITY.md).

## Development setup

```sh
git clone https://github.com/mhoegger/bundlemcp.git
cd bundlemcp
uv sync --all-packages     # Python >= 3.13 workspace (gateway + library)
uv run pytest -q           # hermetic tests, no Docker or network
uv run ruff check .        # lint
uv run lint-imports        # clean-architecture import contracts
```

The full stack (gateway, web UI, Postgres, Valkey, a dev OIDC provider) runs with
`docker compose -f deploy/docker-compose.yml up`; [deploy/TESTING.md](deploy/TESTING.md)
covers the integration suite. The web UI lives in `apps/web` (`npm ci && npm run build`).

New behaviour starts with a spec change in [`spec/`](spec/README.md): each file
holds requirement IDs (`SRV-1`, `EP-3`, …) that tests reference. Architectural
decisions land with an ADR in `docs/adr/` in the same pull request.

## Making a change

1. Fork the repository and create a branch from `main`.
2. Keep the change focused. One pull request should do one thing.
3. Add or update tests for the behaviour you change.
4. Run the tests and the linter locally before you push.

### Commit and pull request titles

Pull requests are squash-merged, so the **pull request title** becomes the commit
message. Write it in the [Conventional Commits](https://www.conventionalcommits.org/)
style:

```
fix(parser): handle empty input
feat: add --json output
docs: explain the retry setting
```

Use `feat` for new behaviour, `fix` for bug fixes, and `docs`, `test`, `refactor`,
`chore`, `ci` or `build` for the rest. Mark a breaking change with `!`
(`feat!: drop Node 18`) and describe the migration in the pull request body.

## Opening a pull request

- Fill in the pull request template and link the issue it resolves.
- CI must pass. If a check fails for a reason unrelated to your change, say so in
  the pull request.
- A maintainer reviews every pull request. Expect a first response within a week;
  feel free to leave a comment if it takes longer.
- Review comments are about the code, not about you. Push follow-up commits rather
  than force-pushing, so reviewers can see what changed.

## Licensing of contributions

By contributing you agree that your contribution is licensed under the same terms
as the project ([Apache-2.0](LICENSE)).

## Code of Conduct

This project follows a [Code of Conduct](CODE_OF_CONDUCT.md). By taking part you
agree to uphold it.
