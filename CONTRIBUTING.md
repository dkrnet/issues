# Contributing

Thank you for considering a contribution to Issues CGI Application.

Before making a non-trivial change, read `requirements.md` and `regression_testing_requirements.md`. The application is intentionally small, single-file, CGI-based, and suitable for authenticated internal deployments.

## Development workflow

1. Make focused changes that preserve the documented requirements.
2. Preserve existing regression guard comments unless a requirement is intentionally changed.
3. Update `requirements.md`, `regression_testing_requirements.md`, and `README.md` when behavior, deployment, configuration, or test expectations change.
4. Commit local repository changes on a development branch, not directly on `main`.
5. Before committing ordinary source changes, make sure `ISSUES_VERSION` in `issues.cgi` is set to the source default documented in `requirements.md`, currently `1.0.0`. Intentional build-output or release-stamping commits are the exception.
6. Run the syntax and regression checks before submitting a change:

```bash
python3 -m py_compile issues.cgi tests/*.py
python3 -m pytest -q
```

Use Python 3.9 through Python 3.12. Python 3.13 is not supported until the application no longer depends on the standard-library `cgi` module.

## Patch quality

When submitting patches, use normal unified diffs or pull requests. Avoid broad rewrites when a minimal, well-tested change is sufficient.
