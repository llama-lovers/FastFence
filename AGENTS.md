# Repository boundary

This directory, `HackYeah2026-challenge-second`, is the canonical FastFence
repository. Run project commands and create project files here, never in its
workspace parent or sibling repositories. Check `git rev-parse --show-toplevel`
before making changes.

Use Pydantic models, not dataclasses. Follow the existing layer boundaries and
update a specification under `specs/changes/` for every implementation change.
Run the relevant checks and configured pre-commit hooks before committing.
