# Decisions Log

> Architecture Decision Records. Append-only. One entry per significant decision.
> This prevents re-litigating the same questions in every new AI session.

---

## 2026-05-20: Use uv as package manager
**Decision:** uv (over pip+venv, poetry, pdm).
**Reasoning:** 10-100x faster than pip; unified tool replacing pip, pip-tools, virtualenv, pyenv; lockfile by default; backed by Astral (same team as ruff).
**Alternatives considered:** Poetry (slower, more config overhead, separate from venv tooling). pip+venv (no lockfile by default, manual workflow).
**Consequences:** All dependency operations go through `uv add` / `uv remove` / `uv sync`. Never edit pyproject.toml dependencies manually.

## 2026-05-20: Use ruff for lint and format
**Decision:** ruff replaces black + flake8 + isort + pyupgrade.
**Reasoning:** Single tool, much faster, consistent config, actively maintained.
**Consequences:** Don't add black, flake8, or isort as separate tools.

## 2026-05-20: Mypy strict mode
**Decision:** Mypy in strict mode from day one.
**Reasoning:** Strictness is much easier to enforce from the start than retrofit. Catches whole categories of bugs at write-time.
**Consequences:** Every function needs full type hints. `# type: ignore` requires an inline comment explaining why.

## 2026-05-20: Migrate from flat directory to package-based layout
**Decision:** Ported initial prototype scripts (`watcher.py` & `test_watcher.py`) into the highly structured Python workspace `obsidian-inbox-watcher` cloned from the `python-template` repository.
**Reasoning:** Allows clean distribution, test separation, dependency encapsulation via Astral's `uv`, unified configurations (`pyproject.toml`), and local packaging support (editable installation via `make install`).
**Alternatives considered:** Keeping the project as flat scripts (leads to dependency pollution, linting issues, fragile test paths, and lacks strict developer gates).
**Consequences:** The code is fully structured inside the `src/obsidian_inbox_watcher` package and is fully compliant with PEP-8 formatting and static check standards.

## 2026-05-20: Configuration file for environment secrets
**Decision:** Place API keys and credentials in `~/.config/vault_watcher/env` instead of hardcoding or requiring global system environment exports.
**Reasoning:** Systemd user-level services can easily read clean `EnvironmentFile=` files. This completely isolates private API keys from getting tracked inside Git histories.
**Alternatives considered:** Injecting keys via command-line arguments (insecure as they appear in system process lists), or standard environment variables (requires exporting in multiple shells and isn't captured by systemd automatically).
**Consequences:** The environment file must be created on any target PC before activating the systemd service.
