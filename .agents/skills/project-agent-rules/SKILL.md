---
name: project-agent-rules
description: "Mandatory workflow and quality rules for AI agents modifying this project. Use when implementing, fixing, testing, refactoring, branching, committing, opening a pull request, or updating AI_Development_Log.md."
---

# Mandatory Project Agent Rules

AI is a support tool, not the final authority. Prioritize correctness, security,
maintainability, and traceability over the amount of code produced. The decision
to accept and merge changes always belongs to an authorized person.

## Required Workflow

Follow these steps in order:

1. **Analyze**
2. **Issue and branch**
3. **Implement with commits**
4. **Test**
5. **Review**
6. **Record in the log**
7. **Open a pull request**

Work is **not complete** until a pull request is ready for review. If the
environment cannot create one, leave the branch ready and report the limitation.

## 1. Pre-Change Analysis

Before changing anything:

- Review the repository structure and files related to the task.
- Understand the existing architecture, technologies, conventions, and behavior.
- Read the issue and its acceptance criteria.
- Identify the components that will change and possible consequences.
- Report missing information, contradictions, or anything that prevents safe
  completion.
- Do not rewrite working components or change the architecture without
  issue-related justification.

## 2. Issues and Branches

- Every change must be associated with an existing issue, or with an issue
  created and approved before work begins.
- Create a new branch from the agreed base, normally `main` or `develop`.
- Use descriptive names such as `feature/123-calendar-availability`,
  `fix/124-cancelled-reservations`, or `test/125-reservation-tests`.
- Never work directly on `main` or `develop`.
- Use one branch per issue; do not mix independent tasks.
- Do not modify or delete another contributor's work without authorization.
- If work outside the scope is needed, document it and request authorization or
  create a separate issue.

## 3. Commits

- Keep commits small, descriptive, and limited to the issue.
- Include the issue identifier, for example:
  `fix: correct date availability (#124)`.
- Never include temporary files, credentials, passwords, private keys, or
  sensitive configuration.
- Do not rewrite history with destructive operations without authorization.
- Do not include changes unrelated to the task.
- Do not claim that something was saved in Git without verifying it.

## 4. Testing and Validation

Before requesting review:

- Run the existing automated tests related to the change.
- Create or update tests for the implemented behavior.
- Cover normal cases, edge cases, and relevant errors.
- Verify that existing functionality is not broken.
- Run available quality checks such as static analysis, builds, and formatting.
- Record the actual results.
- If a test fails, investigate and fix it when it is within scope. Otherwise,
  report the failure and its possible causes.

**Prohibited:** inventing results, claiming tests passed without running them, or
deleting tests merely to obtain a successful run.

## 5. Modification Restrictions

- Do not add unrequested or unapproved features.
- Do not remove existing features without justification and authorization.
- Do not change dependencies, versions, database schemas, or global
  configuration without demonstrated need.
- Do not add new libraries when existing tools can solve the problem, unless
  justified.
- Do not put credentials, private data, or sensitive information in code,
  commits, or records.
- Do not hide errors with generic exceptions, disabled validation, or deleted
  tests.
- Do not claim ownership of decisions the team did not make.
- Do not assume an AI suggestion is correct merely because it appears
  technically valid.

**Stop and request review** when the change has significant risks, requires
  expanding scope, or may affect existing data.

## 6. Self-Review Before the Pull Request

Verify that the changes:

- [ ] Meet the issue acceptance criteria.
- [ ] Follow the project architecture and conventions.
- [ ] Contain no unnecessary changes.
- [ ] Introduce no obvious security or functional errors.
- [ ] Include necessary tests and documentation.
- [ ] Include entries in the AI usage log.

Self-review does not replace review by another team member.

## 7. AI Usage Log (`AI_Development_Log.md`)

Update the log after every significant change and before considering the issue
ready. If the team already uses another filename for this log, preserve that
filename and do not create a duplicate.

Each entry must include:

| Field | Content |
|---|---|
| Date | When the activity occurred |
| Issue | Related issue |
| Activity | What was done |
| Tool/agent | Which AI was used |
| Request | What was asked of the AI |
| Result | What was obtained |
| Validations | Tests or checks performed |
| Human decision | Accepted, partially accepted, modified, or rejected |
| Reason | Why that decision was made |
| Reference | Commit or pull request, when available |

- Do not log every prompt. Log interventions that affect development, technical
  decisions, tests, bug fixes, and acceptance or rejection of proposals.
- Also document incorrect AI responses, unsuitable solutions, and changes the
  team rejected.
- The log must reflect real facts; never invent results, human decisions, or
  AI errors.

## 8. Pull Request Required

Create the pull request from the working branch into the agreed base branch. It
must include:

- The issue identifier and link.
- A summary of the problem and solution.
- Modified files or components.
- Tests run and their results.
- Known limitations and pending work.
- References to the `AI_Development_Log` entries.

Verify that the branch and pull request contain only the intended changes.

The agent **must not** approve or merge its own pull request, or close the issue
as complete, without authorization. That decision belongs to an authorized
person.

## 9. Ready-for-Review Checklist

- [ ] The requested solution was implemented.
- [ ] The issue scope was respected.
- [ ] Work was done on an independent branch.
- [ ] Descriptive commits were created.
- [ ] Relevant tests were run.
- [ ] Actual results were documented.
- [ ] `AI_Development_Log` was updated.
- [ ] The pull request was created.
- [ ] Every limitation or pending task was reported.

The issue is definitively complete only after an authorized person reviews,
accepts, and integrates it according to the repository procedure.
