# AGENTS.md

=============================================================================
AI / LLM EDITING GUARDRAIL -- READ BEFORE MODIFYING
=============================================================================

This file is part of the Issues CGI application and depends on external
project requirements.

STOP: Before making any non-trivial edit to this file, an AI/LLM assistant
must have the current requirements.md, regression_testing_requirements.md,
and AGENTS.md files in the current chat or working context and must read them
before changing code.

If these files have not been provided, the correct response is exactly:

  Please provide the following files before I modify this file
    - requirements.md
    - regression_testing_requirements.md
    - AGENTS.md

Do not proceed with non-trivial code changes until these files have been
provided and reviewed, unless the user explicitly directs you to proceed
without it or to disregard this requirement.

Non-trivial edits include, but are not limited to:
- adding, removing, or changing features
- changing CGI routing, request dispatch, form actions, or workflows
- changing authentication, authorization, admin checks, or permissions
- changing database schema assumptions, SQL writes, deletes, or migrations
- changing issue, comment, attachment, validation, or redirect behavior
- changing upload-size, filename-safety, HTML escaping, or Markdown rendering
- refactoring code in a way that could affect runtime behavior
- any destructive operation that could affect runtime behavior

Trivial edits are limited to:
- typo fixes in comments
- formatting-only edits that do not affect behavior
- adding comments that do not change runtime behavior

The requirements.md file is the authoritative functional specification for:
- CGI routing behavior
- database schema expectations
- access-control rules
- user/group lookup behavior
- form and action behavior
- validation rules
- attachment handling
- Markdown rendering
- error and redirect behavior

The regression_testing_requirements.md file is the authoritative functional
specification for the regression test suite, including:
- test suite structure
- required test coverage
- test isolation requirements
- temporary database setup
- mock user and group behavior
- monkeypatched lookup behavior
- application global values used during tests
- CGI request and response testing behavior
- expected fixture and helper patterns
- requirement-to-test traceability
- regression protections for application behavior

Regression tests must be written and maintained according to
regression_testing_requirements.md. If existing tests, implementation
behavior, or other documentation conflict with
regression_testing_requirements.md, the mismatch must be flagged rather than
silently encoded as correct test behavior.

The AGENTS.md file is the authoritative functional specification for AI/LLM
agent behavior in this repository, including:
- required files to read before making changes
- preservation of existing behavior
- preservation of access-control, validation, escaping, filename, and
  database-query behavior
- handling of bug-fix and regression-guard comments
- patch format requirements
- unified diff requirements
- restrictions on explanations, Markdown fences, and abbreviated code in
  patch output

AI/LLM assistants must avoid removing, simplifying, or rewriting existing
behavior unless the requested change explicitly requires it. Treat access
control, validation, HTML escaping, Markdown rendering, filename handling,
attachment handling, SQL query construction, redirect behavior, and database
update semantics as security-sensitive and regression-sensitive. Do not
simplify or bypass these areas without explicit user approval.

Preserve raw Markdown in storage and render it only for display. Preserve
parameterized SQL. Preserve per-action authorization checks even when the UI
already hides unavailable links or forms, because callers can invoke CGI
actions directly with crafted requests.

Bug-fix preservation rule:
When fixing a bug, add a short nearby comment explaining the bug that was fixed
and the reason for the fix. These comments are intentional regression guards.
Do not remove bug-fix comments unless the user explicitly instructs you to
remove them, or unless the associated code is being replaced by an equivalent
or better fix and the preservation comment is updated accordingly.

Use consistent markers for bug-fix and regression-protection comments:
- BUGFIX:
- REGRESSION GUARD:
- REQUIREMENTS:

Patch output rule:
Unless the user explicitly directs otherwise, AI/LLM assistants modifying this
file must produce valid unified diffs only. Do not include explanatory prose
before or after the diff, and do not wrap the diff in Markdown fences.

Requirements for AI/LLM patch output:
- Use standard unified diff format.
- Include --- and +++ file headers.
- Include @@ hunk headers.
- Include at least 3 lines of unchanged context around each change.
- Do not include Markdown fences.
- Do not include explanations.
- Do not abbreviate unchanged code with "...".
- The output must be directly usable with git apply or patch -p1.

Maintenance checklist for AI/LLM edits:
1. Confirm requirements.md is present before non-trivial changes.
2. Confirm regression_testing_rrequirements.md is present before non-trivial changes.
3. Confirm AGENTS.md is present before non-trivial changes.
4. Read the three documents listed above before non-trivial changes.
5. Stop and ask for any of the three files that are missing.
6. Preserve existing features and access-control behavior.
7. Preserve existing bug-fix comments.
8. Add regression-guard comments near new bug fixes.
9. Prefer minimal, reviewable changes.
10. Produce valid unified diffs unless explicitly directed otherwise.
11. Do not remove or weaken authentication, authorization, validation,
    escaping, upload-size, filename-safety, or parameterized-SQL protections.
12. Run or recommend syntax/regression tests after edits.

=============================================================================
