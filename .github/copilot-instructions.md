# Project-Wide Agent Instructions

These instructions apply to every agent task in this repository.

## Mandatory Rules

- Follow the complete workflow in
  [the project-agent-rules skill](../.agents/skills/project-agent-rules/SKILL.md).
- Analyze the repository, issue, acceptance criteria, architecture, and related
  files before editing.
- Work from an issue-approved branch; never work directly on `main` or `develop`.
- Keep changes scoped, avoid unapproved features, and do not modify other
  contributors' work.
- Never commit secrets, credentials, private keys, temporary files, or sensitive
  configuration.
- Run relevant tests and quality checks, record real results, and never claim
  checks passed without running them.
- Update `AI_Development_Log.md` (or the repository's existing equivalent) for
  significant work.
- Prepare a pull request for review when the environment allows it. Do not
  approve or merge the agent's own pull request.

## Stop Conditions

Stop and request human review if the change expands scope, has significant
security or data risks, changes architecture without issue justification, or
requires modifying existing data or global configuration.

The linked skill is the source of the complete workflow, commit requirements,
validation checklist, logging fields, and pull-request requirements.
