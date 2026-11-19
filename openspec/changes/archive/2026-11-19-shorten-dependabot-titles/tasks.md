# Tasks

## 1. Dependabot titles

- [x] 1.1 Add `shorten_bot_title` and the `bot-title` command to `tools/pull_request_release.py`. Add
  `test_dep12_a_dependabot_title_over_the_limit_is_cut_to_fit` and
  `test_dep12_a_dependabot_title_within_the_limit_is_kept`, and verify that they pass (DEP-12).
- [x] 1.2 In `release-entry.yml`, shorten and save a Dependabot pull request's title before the title check, and use
  the shortened title in the entry job. Verify that the YAML parses (DEP-12).
- [x] 1.3 Describe the shortening in `CONTRIBUTING.md` and in the comment in `.github/dependabot.yml`.

## 2. E2E-28

- [x] 2.1 Make E2E-28 wait until the count of successful audit records stops changing before it compares against it.
  Verify that it passes against the compose stack.
