# Broken LLM Integration App: Agent Context

## Mission and Safety Boundary

This repository is an intentionally vulnerable LLM security training system. It
lets learners exploit and then mitigate prompt leaking, indirect prompt
injection, prompt-to-SQL (P2SQL) injection, and LLM-driven code execution
(LLM4Shell).

Never treat this as a production application. Some paths deliberately pass
untrusted text to SQL-generating chains or to a Python-executing PAL chain.
Run it only in an isolated local, disposable, or tightly access-controlled
training environment. Do not "fix" an intentional vulnerability unless the
requested task is to change that exercise or its defense level.

## Two Runtime Modes

1. `chatapp/`: the full standalone application, normally run with Docker
   Compose. It uses React, Nginx, FastAPI, MySQL, and a dummy web service.
2. `course/` + `student_workspace/`: the notebook training harness. It reuses
   the FastAPI backend, replaces MySQL with a per-student SQLite database,
   bypasses JWT for the embedded lesson UI, and syncs three learner-editable
   Python files into a generated backend copy.

Keep these modes distinct when diagnosing or changing behavior. A fix to the
Docker app does not automatically update an already-created course runtime.

## Repository Map

| Path | Role |
| --- | --- |
| `README.md`, `README_ja.md` | Standalone product purpose, modes, and Docker setup |
| `PLAN.md` | Dated UX/improvement plan; useful intent, not guaranteed current state |
| `Price.md` | Dated AWS/TLJH cost estimate; assumptions, not live pricing |
| `LICENSE` | MIT license (copyright 2023 isao takaesu) |
| `chatapp/docker-compose.yml` | Standalone service topology and ports |
| `chatapp/backend/app/` | Canonical FastAPI, auth, DB, LLM, filters, and prompts |
| `chatapp/backend/tests/` | Backend pytest suite, currently centered on auth/protection |
| `chatapp/frontend/src/` | React login and chat UI |
| `chatapp/dummy_web/` | Malicious-content site used by indirect prompt injection |
| `chatapp/mysql/`, `chatapp/nginx/` | Standalone infrastructure |
| `assets/sample_data/` | CSV seed data shared by MySQL and course SQLite flows |
| `import_sample_data.sh` | Imports CSV sample data into the Docker MySQL service |
| `course/notebooks/` | Authoritative lesson notebooks: `10`, `20`, and `30` |
| `course/broken_handson/` | Course configuration, seeding, server wrapper, and launcher API |
| `course/webui/` | Lightweight UI served by the notebook harness |
| `course/ops/` | TLJH install, rollout, distribution, UX, and reset scripts |
| `student_workspace/` | Minimal learner-facing notebooks and editable defense files |

## Standalone Application

### Service and Request Flow

- Nginx exposes the React UI on port 80 with BASIC authentication; it does not
  proxy backend API routes.
- React stores the JWT in browser `localStorage` and sends bearer-authenticated
  requests directly to `http://<REACT_APP_HOST_NAME>:8000`.
- FastAPI runs on port 8000. `chatapp/backend/app/main.py` owns routes and maps
  each exercise endpoint to `llm_agent.py`.
- MySQL runs on port 3306; phpMyAdmin is exposed on port 8080.
- `dummy_web` runs on port 8001 and supplies untrusted web content for the
  indirect-prompt-injection exercise.

Read `chatapp/docker-compose.yml`, Nginx config, and the frontend API calls
together before changing hostnames, ports, routing, or authentication.
Publishing port 8000 bypasses Nginx BASIC authentication; JWT still protects
exercise routes, but this remains an intentionally unsafe local topology.

### Backend Ownership

- `main.py`: FastAPI app, startup table creation, CORS, auth routes, health
  check, and exercise endpoints.
- `auth.py`: bcrypt password verification, JWT creation/decoding, and current
  active-user dependencies.
- `db_models.py`: SQLAlchemy models for `users`, `chats`, `messages`,
  `memberships`, and `user_settings`.
- `db_settings.py`, `settings.py`: database engine/session and environment
  configuration.
- `models.py`: API request/response models.
- `llm_models.py`: model construction for OpenAI, Ollama, Amazon Bedrock, and
  Google Gemini. The notebook launcher directly assists only OpenAI and Ollama.
- `llm_agent.py`: orchestration for all vulnerable and defended modes.
- `llm_db_chain.py`: SQLDatabaseChain construction for P2SQL exercises.
- `llm_shell_chain.py`: PALChain construction with dangerous code execution;
  imports and command execution are explicitly allowed.
- `llm_prompt_templates.py`: deliberately leaky and progressively hardened
  prompts.
- `blacklists.py`, `filters.py`: regex-based level-2 input/output defenses.
- `guardrails.py`, `nemo_config/`: NeMo (prompt-leaking level 4) and DeepKeep
  (level 5) integration. Its currently unused `is_sql=True` branch references
  a non-existent `nemo_config/config_for_sql.yml`; do not enable it without
  adding and testing that configuration.

### Exercise Families

- Prompt leaking levels 1-5: no guard, regex filtering, prompt hardening,
  NeMo Guardrails, then DeepKeep.
- Indirect prompt injection level 1: loads content from `dummy_web` into an LLM
  prompt without a trust boundary.
- P2SQL levels 1-5: raw LLM-to-SQL behavior followed by filtering, defensive
  prompts, prompt hardening, and LLM-as-a-Judge.
- LLM4Shell levels 1-4: PALChain with real Python execution followed by
  filtering, prompt hardening, and LLM-as-a-Judge.

The exact endpoint-to-function mapping in `main.py` and `llm_agent.py` is the
source of truth; README descriptions can lag implementation.

### Authentication and Data

- `/auth/login` issues JWTs; `/auth/me` and exercise endpoints require an
  active user in standalone mode.
- Settings come from environment variables. Important groups are JWT
  (`SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`), database
  (`DB_USERNAME`, `DB_PASSWORD`, `DB_HOST`, `DB_NAME`), model-provider, and
  optional guardrail settings. Inspect `settings.py` before adding or renaming
  variables.
- ORM tables are created at backend startup. Seed order must preserve foreign
  keys: users, user settings, chats, memberships, messages.
- CSVs in `assets/sample_data/` are deterministic training fixtures. Changes
  affect both standalone imports and notebook lessons.

## Course and Student Runtime

### Lesson Sequence

The implemented sequence has three notebooks:

1. `10_prompt_leaking.ipynb`
2. `20_p2sql.ipynb`
3. `30_llm4shell.ipynb`

Each lesson configures an LLM, seeds data, starts the server, opens the UI,
demonstrates an unsafe level, then edits/tests progressively stronger defenses.
LLM output is nondeterministic and requires a provider/API key.

### Harness Flow

`course/broken_handson/config.py` resolves paths, loads environment, copies the
backend into a generated runtime, and patches the DB URL to SQLite before app
imports. `server.py` imports the existing FastAPI app, overrides the active-user
dependency for lessons, mounts course assets, and serves `course/webui/`.
`seed.py` creates and repopulates SQLite from the shared CSV fixtures.

The public notebook API is in `launcher.py`:

```python
from broken_handson import launcher

launcher.configure_llm()
launcher.seed()
process = launcher.start()
launcher.show()
launcher.sync_edit_targets()
launcher.reset_edit_targets()
launcher.stop(process)
```

`show()` has separate Colab, local Jupyter, and JupyterHub proxy behavior.
JupyterHub requires `jupyter-server-proxy`; test both the displayed URL and the
iframe when changing it.

### Editable and Generated Files

Learners edit only:

- `student_workspace/edit_targets/blacklists.py`
- `student_workspace/edit_targets/filters.py`
- `student_workspace/edit_targets/llm_prompt_templates.py`

`launcher.sync_edit_targets()` copies these into the generated backend watched
by uvicorn. `launcher.reset_edit_targets()` restores the runtime baseline. The
notebooks also contain answer cells that can overwrite edit targets, so preserve
that behavior intentionally when revising lessons.

The backend copy and reset baseline are created only when absent. After changing
canonical backend files, use a fresh temporary student workspace or remove that
workspace's generated `.runtime/` before testing the new baseline; syncing the
three edit targets alone cannot refresh other copied backend modules.

Treat `.runtime/`, SQLite databases, copied backend trees, `inspect_result.json`,
notebook checkpoints, Python caches, and local `.env` files as generated/private
state. Never use a generated runtime copy as the source for a code change.
`secret.md` and secrets embedded in prompt templates are fake lesson artifacts,
but real API keys must never be committed or echoed.

## Common Commands

The checked-in Python version is `3.12.9` in `.python-version`.

Standalone setup and run (after creating the documented backend/frontend env
files):

```bash
cd chatapp
docker compose --env-file ./backend/.env build
docker compose up -d
cd ..
./import_sample_data.sh
```

Backend tests:

```bash
cd chatapp/backend
python -m pip install -r requirements.txt -r requirements-test.txt
python -m pytest
```

Course environment:

```bash
python -m pip install -r course/requirements.txt
python -m pip install jupyterlab "lark==1.1.9"
jupyter lab student_workspace/notebooks
```

TLJH rollout is driven by `course/ops/one_shot_update_tljh.sh` and its local,
uncommitted `tljh_rollout.conf`. Read the script and
`course/DEPLOY_JUPYTERHUB_ja.md` before running it. Per-user recovery uses
`course/ops/reset_student_workspace_for_user.sh`; distribution must exclude
`.env`, `.runtime/`, caches, and notebook checkpoints.

## Change Rules

1. Identify the target runtime first: standalone Docker, course harness, or
   both.
2. Preserve deliberate vulnerability at the intended level. Defenses at one
   level must not silently harden lower levels used for demonstration.
3. Change canonical source, not `.runtime` output. If lesson baselines are meant
   to change, update the relevant `student_workspace/edit_targets/` copies too
   and verify reset/sync behavior.
4. Keep SQLite patching and auth override before imports that initialize the
   backend; import-order changes can accidentally reconnect lessons to MySQL or
   re-enable JWT.
5. Preserve seed ordering and per-student runtime isolation.
6. Do not broadly modernize pinned LangChain/NeMo dependencies. Their APIs and
   transitive constraints are sensitive; make upgrades as a dedicated task.
7. Shell scripts under `course/ops/` target Ubuntu/TLJH and may modify `/opt`,
   `/etc/skel`, user homes, and TLJH config. Review dry-run/config switches and
   never execute rollout scripts as routine validation.
8. Keep English and Japanese top-level documentation aligned when changing
   standalone behavior. Keep source and distributed notebook copies aligned
   when changing lessons.

## Validation by Change Area

- Backend/auth/API: run `python -m pytest` in `chatapp/backend`; add focused
  tests for changed behavior because existing coverage is mostly auth-oriented.
- Frontend: use scripts defined in `chatapp/frontend/package.json` and manually
  verify login, token expiry/logout behavior, mode selection, and API errors.
- Course harness: in a clean or temporary student workspace, run configure,
  seed, start, health check, sync, reset, and stop. Verify SQLite is used and no
  source/runtime files cross-contaminate.
- Notebook changes: execute affected notebooks from a clean kernel without
  relying on stored outputs; check both learner-edit and answer-cell paths.
- Deployment scripts: use syntax/static checks and a non-production pilot home
  before any all-user rollout.

## Known Context and Documentation Debt

- `PLAN.md` is a 2026-07-09 planning snapshot, not a live backlog. Several items
  it calls missing now exist: current course docs start at notebook `10`, the
  student workspace is separated, the launcher selects a JupyterHub proxy iframe,
  and ops scripts configure the notebook start directory. Recheck code and docs
  before carrying a PLAN item forward.
- There is intentionally no `00_setup.ipynb`; current course and deployment docs
  directly use notebooks `10`, `20`, and `30`. References to `00_setup` in
  `PLAN.md` describe the former mismatch.
- JupyterHub start-directory and proxy/iframe behavior are deployment-sensitive
  and require testing on an actual TLJH instance.
- Core vulnerability behavior has little automated coverage; an auth-only green
  suite does not prove that LLM, SQL, shell, or notebook flows still work.

When documents disagree, prefer executable code and configuration, then update
the stale documentation as part of the same task when appropriate.