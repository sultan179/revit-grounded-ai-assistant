# Revit Grounded AI Assistant

A small Python core for an AI assistant that answers questions about the
revisions of a Revit model, such as "what changed between revision A and
revision B?".

The rule it is built around: **the language model words the answer, and it
never supplies a fact.** Every number in an answer must match a value that a
tool returned. If the check fails, the caller gets the plain table of results
instead of the model's text.

## Status

Under construction. This repository currently holds the project skeleton only.
The parts below are being added in small commits, each with its tests.

| Part | What it does | State |
|---|---|---|
| Gateway | Off switch, spend caps per question and per day, and a log entry written before every model call | planned |
| Tools | Read-only tools with validated input; the model can call nothing else | planned |
| Loop | A bounded conversation: a fixed number of tool calls and a time limit | planned |
| Verifier | Checks every number in the answer against the tool results | planned |
| Evaluation | A fixed set of questions and attack cases on an invented building | planned |

All examples and tests use an invented building. The repository contains no
real project data.

## Development

Requires Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pytest
uv run ruff check .
uv run mypy
```

The tests never call a real model: network access is blocked while they run.

### Guards against leaks

Enable the Git hooks once per clone:

```bash
git config core.hooksPath .githooks
```

- **Before each commit**, the staged changes are scanned for secrets with
  [gitleaks](https://github.com/gitleaks/gitleaks). Without gitleaks installed,
  the commit is refused.
- **Before each push**, the commits are checked against a private word list
  that is kept outside the repository (`tools/check_push.py` explains how to
  set it). Without a list, the push is refused.
- **In CI**, the whole history is scanned for secrets and the locked
  dependencies are audited.

## Licence and trademarks

MIT; see [LICENSE](LICENSE).

Revit is a trademark of Autodesk, Inc. This project is not affiliated with,
sponsored by or endorsed by Autodesk.
