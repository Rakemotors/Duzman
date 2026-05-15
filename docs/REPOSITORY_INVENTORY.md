# Duzman Repository Inventory

## 1. Executive summary

- Repository path: `/home/ubuntu/duzman`.
- Branch: `main`.
- Latest commit: `e8ca134 Day 2: project skeleton, DB models, initial migration`.
- Working tree at start: clean (`git status --short --branch` showed only `## main...origin/main`).
- Day 1 completion state: partial. Some repository foundation files exist, but VPS/system components were not inspected by design, and repo-local service/deployment documentation is minimal.
- Day 2 completion state: partial. Python package skeleton, dependency declarations, SQLAlchemy models, and one Alembic migration exist; collectors, scheduler implementation, structured logging, and tests are not implemented.
- Day 3 completion state: not implemented beyond schema placeholders for several Day 3 data tables.

## 2. Git state

- Branch: `main`.
- Remote: `origin git@github.com:Rakemotors/Duzman.git` for fetch and push.
- Latest commits:
  - `e8ca134 Day 2: project skeleton, DB models, initial migration`
  - `c27e7ff Initial commit: project skeleton`
- Clean/dirty state at start: clean.

## 3. Project structure

Key files and directories found:

- `README.md`: brief project note.
- `pyproject.toml`: package metadata and pytest config only.
- `requirements.txt`: pinned runtime/test dependency list.
- `alembic.ini`: Alembic configuration pointing to `src/duzman/db/alembic`.
- `src/duzman/`: Python package root.
- `src/duzman/settings.py`: Pydantic settings object.
- `src/duzman/db/session.py`: SQLAlchemy engine, base, and session factory.
- `src/duzman/db/models.py`: SQLAlchemy ORM models.
- `src/duzman/db/alembic/`: Alembic environment and initial migration.
- `tests/`: package exists, but only `tests/__init__.py` was found.
- `docs/`: missing at start; created for this inventory.

Tracked files also include `.bash_logout`, `.bashrc`, `.gitconfig`, and `.profile`. These shell/profile files were not read because this task forbids shell profile modification and access-control changes.

## 4. Documentation status

- `README.md`: present but incomplete. It only states that Duzman is a personal crypto metrics monitor for Stage A and references the v1.2 technical specification.
- `DEPLOYMENT.md`: missing.
- `TROUBLESHOOTING.md`: missing.
- `CHANGELOG.md`: missing.
- `docs/` directory: missing at start; created with this inventory document.

## 5. Python package and dependencies

`pyproject.toml` declares:

- Build backend: `setuptools.backends.legacy:build`.
- Package name/version: `duzman` `0.1.0`.
- Python requirement: `>=3.12`.
- Package discovery under `src`.
- Pytest config with `asyncio_mode = "auto"` and `testpaths = ["tests"]`.

`pyproject.toml` does not declare project dependencies. Dependencies are declared in `requirements.txt`:

- `fastapi==0.115.12`
- `uvicorn[standard]==0.34.2`
- `sqlalchemy==2.0.40`
- `alembic==1.15.2`
- `psycopg2-binary==2.9.10`
- `httpx==0.28.1`
- `pandas>=2.3.2`
- `pandas-ta==0.4.67b0`
- `apscheduler==3.11.0`
- `anthropic==0.52.0`
- `python-telegram-bot==21.11.1`
- `beautifulsoup4==4.13.4`
- `structlog==25.3.0`
- `python-dotenv==1.1.0`
- `pydantic==2.11.4`
- `pydantic-settings==2.9.1`
- `pytest==8.3.5`
- `pytest-asyncio==0.26.0`

Expected Stage A dependency status:

- Python 3.12: present in environment (`Python 3.12.3`) and declared as `>=3.12`.
- FastAPI: present in `requirements.txt`.
- SQLAlchemy 2.0: present in `requirements.txt`.
- Alembic: present in `requirements.txt`, but not installed in active environment.
- PostgreSQL driver: present as `psycopg2-binary`.
- APScheduler: present in `requirements.txt`.
- httpx: present in `requirements.txt`.
- pandas: present in `requirements.txt`.
- pandas-ta or alternative: present as `pandas-ta`.
- pydantic: present in `requirements.txt`.
- pydantic-settings: present in `requirements.txt`.
- structlog: present in `requirements.txt`.
- beautifulsoup4: present in `requirements.txt`.
- python-telegram-bot: present in `requirements.txt`.
- anthropic: present in `requirements.txt`.
- pytest: present in `requirements.txt`, but not installed in active environment.

## 6. Config status

- `config/assets.yaml`: missing.
- `config/sources.yaml`: missing.
- `config/patterns.yaml`: missing.
- `config/alerts.yaml`: missing.
- `config/system.yaml`: missing.

No `config/` directory was found. No YAML config contents were inspected because no config files exist. No secrets were printed.

## 7. Database models status

- `assets`: implemented. ORM model and migration table exist.
- `price_snapshots`: implemented. ORM model and migration table exist with timestamp/asset index.
- `indicators`: implemented as a generic indicator storage table. Calculating/persisting indicator code is missing.
- `funding_rates`: implemented as schema only. Collector/persistence code is missing.
- `open_interest`: implemented as schema only. Collector/persistence code is missing.
- `long_short_ratio`: implemented as schema only. Collector/persistence code is missing.
- `liquidations`: implemented as schema only. Collector/persistence code is missing.
- `etf_flows`: implemented as schema only. Collector/persistence code is missing.
- `global_metrics`: implemented as schema only. Collector/persistence code is missing.
- `pattern_triggers`: implemented as schema only. Pattern engine is missing.
- `alerts_sent`: implemented as schema only. Telegram dispatch/cooldown logic is missing.
- `api_requests`: implemented as schema only. API middleware is missing.
- `source_health`: implemented as schema only. Source health tracking code is missing.

Important mismatches:

- Tables broadly match the expected v1.2 table names, but most are schema placeholders without application logic.
- `settings.py` contains a default `database_url` string with a placeholder password. It is not a printed secret, but credentials should not be hardcoded even as examples in runtime defaults.
- ORM defaults use `datetime.now` in some places; migration uses server defaults for selected columns. Timezone behavior should be reviewed before production use.

## 8. Alembic migrations status

- Alembic exists in repository:
  - `alembic.ini`
  - `src/duzman/db/alembic/env.py`
  - `src/duzman/db/alembic/script.py.mako`
  - `src/duzman/db/alembic/versions/b009e25bfab4_initial_schema.py`
- Migration files found:
  - `b009e25bfab4_initial_schema.py`
- The migration creates:
  - `assets`
  - `price_snapshots`
  - `indicators`
  - `funding_rates`
  - `open_interest`
  - `long_short_ratio`
  - `liquidations`
  - `etf_flows`
  - `global_metrics`
  - `pattern_triggers`
  - `alerts_sent`
  - `api_requests`
  - `source_health`
- Migration schema broadly matches the expected Duzman v1.2 table list, but it has not been validated against a live database in this task.
- Read-only Alembic commands could not run because `alembic` is not installed in the active environment.
- No migrations were applied.

## 9. Collectors status

- Base collector: missing.
- `BinanceCollector`: missing.
- `CoinGeckoCollector`: missing.
- `BybitCollector`: missing.
- `OKXCollector`: missing.
- `CoinGlassCollector`: missing.
- `FarsideCollector`: missing.
- Alternative.me / Fear & Greed collector: missing.
- CoinGecko global / BTC dominance collector: missing.

No collector modules were found under `src/duzman`.

## 10. Scheduler status

- APScheduler dependency: declared in `requirements.txt`.
- APScheduler usage in source: missing.
- Hourly collect cycle: missing.
- Schedule at `XX:17 UTC`: missing.
- Daily jobs: missing.
- Manual run entrypoint: missing.

## 11. Indicators status

- RSI: missing.
- Stochastic: missing.
- Volatility: missing.
- Visible timeframes: none.
- Persistence to DB: only the generic `indicators` table exists; no calculation or persistence logic was found.

## 12. API and dashboard status

- FastAPI dependency: declared in `requirements.txt`.
- FastAPI app: missing.
- REST routes: missing.
- Auth middleware: missing.
- Schemas: missing.
- Dashboard routes: missing.
- Jinja2 templates: missing.
- Plotly usage: missing.

## 13. Alerts and pattern engine status

- `patterns.yaml`: missing.
- Pattern engine: missing.
- Condition evaluation: missing.
- Cooldown logic: missing.
- Hard caps: missing.
- Telegram dispatcher: missing.
- Alert formatter: missing.
- AI explainer: missing.
- Post-processing filter: missing.

Only schema placeholders exist for `pattern_triggers` and `alerts_sent`, plus settings fields for Telegram and Anthropic configuration.

## 14. Tests status

- Test files found:
  - `tests/__init__.py`
- Tests were attempted with `python3 -m pytest -q`.
- Result: failed before collection because pytest is not installed in the active environment.
- Failure: `/usr/bin/python3: No module named pytest`.
- No dependencies were installed.

## 15. Day 1 completion assessment

Day 1 status: partial.

Repository evidence shows a cloned project with Python package skeleton and git remote configured. Python 3.12.3 is available in the active environment. The task did not inspect system-level VPS components such as PostgreSQL 16, Caddy, UFW, Fail2ban, systemd services, rclone, Linux users, sudo, SSH configuration, or global environment variables because those checks are outside safe repository inventory scope and several are explicitly guarded.

Within the repository, deployment/system documentation is minimal or missing.

## 16. Day 2 completion assessment

Day 2 status: partial.

Implemented:

- `pyproject.toml` exists.
- Dependencies are declared in `requirements.txt`.
- Alembic configuration exists.
- Initial migration exists.
- `price_snapshots` table exists in ORM and migration.
- Binance and CoinGecko public-data collector foundations exist.
- Supplied-payload ingestion can persist normalized snapshots through a repository.
- APScheduler job registration foundation exists for hourly ingestion at minute 17.
- GET-only public HTTP client abstraction exists.
- Binance and CoinGecko public fetcher service exists and is tested with mocked HTTP.
- Source health check persistence exists for source status, latency, and bounded errors.

Missing:

- Structured logging usage.
- Production scheduler startup wiring.
- Automatic ingestion flow that combines live public fetches, price persistence, and source health in scheduled runtime.

## 17. Day 3 readiness assessment

Day 3 status: not ready.

Existing Day 3-related pieces:

- Schema exists for `indicators`.
- Schema exists for derivatives-related tables such as `funding_rates`, `open_interest`, `long_short_ratio`, and `liquidations`.

Remaining before Day 3 can be considered complete:

- Implement RSI for `1h`, `4h`, `1d`, and `1w`.
- Implement Stochastic for `1h` and `4h`.
- Implement realized volatility.
- Persist indicator calculations to `indicators`.
- Implement `BybitCollector`.
- Implement `OKXCollector`.
- Implement perpetual-vs-spot premium/discount collection/calculation.
- Add tests for indicator calculations and derivative collector behavior.

## 18. Risks and inconsistencies

- Runtime dependencies are in `requirements.txt`, not `pyproject.toml`; this may be acceptable, but packaging metadata alone is incomplete.
- Active environment does not have pytest or Alembic installed, so test and migration command verification cannot currently run.
- No `config/` directory or v1.2 YAML config files exist.
- No collectors, scheduler, API, dashboard, pattern engine, alerting, or AI explanation modules exist yet.
- Tracked shell/profile files exist at repository root: `.bash_logout`, `.bashrc`, `.gitconfig`, and `.profile`. They were not read or modified. This is unusual for an application repository and should be reviewed in a separate safe task.
- `settings.py` has a default PostgreSQL URL containing a placeholder password. Even placeholder credentials in runtime defaults can encourage unsafe configuration patterns.
- No tests exist beyond an empty test package marker.
- DB schema exists ahead of application logic, so future tasks should avoid assuming data is being collected or derived.

## 19. Recommended next Codex task

`setup-local-venv-and-test-runner`

Reason: the active environment cannot run pytest or Alembic, so establishing a local virtual environment and reproducible test runner is the safest next step before changing models, migrations, collectors, or Day 3 logic.

## 20. Commands executed

- `pwd`
- `git status --short --branch`
- `git branch --show-current`
- `git remote -v`
- `git log --oneline -10`
- `ls -la`
- `find . -maxdepth 4 -type f | sort`
- `find config -maxdepth 2 -type f -print 2>/dev/null || true`
- `find src -maxdepth 5 -type f | sort 2>/dev/null || true`
- `find tests -maxdepth 5 -type f | sort 2>/dev/null || true`
- `cat pyproject.toml 2>/dev/null || true`
- `cat requirements.txt 2>/dev/null || true`
- `cat README.md 2>/dev/null || true`
- `cat DEPLOYMENT.md 2>/dev/null || true`
- `cat TROUBLESHOOTING.md 2>/dev/null || true`
- `cat CHANGELOG.md 2>/dev/null || true`
- `sed -n '1,260p' src/duzman/db/models.py`
- `sed -n '1,220p' src/duzman/db/session.py`
- `sed -n '1,220p' src/duzman/settings.py`
- `sed -n '1,260p' src/duzman/db/alembic/versions/b009e25bfab4_initial_schema.py`
- `sed -n '1,220p' src/duzman/db/alembic/env.py`
- `sed -n '1,220p' alembic.ini`
- `rg -n "class .*Collector|Binance|CoinGecko|Bybit|OKX|CoinGlass|Farside|Alternative|Fear|Greed|global|dominance|APScheduler|BackgroundScheduler|CronTrigger|scheduler|RSI|Stochastic|volatility|FastAPI|APIRouter|Jinja2|Plotly|Telegram|pattern|cooldown|alert|anthropic|AI" src tests pyproject.toml requirements.txt README.md alembic.ini`
- `python3 --version`
- `python3 -m pytest -q`
- `alembic history`
- `alembic current`
- `git ls-files`
- `find . -maxdepth 2 -type d | sort`
- `sed -n '1,120p' src/duzman/__init__.py`
- `sed -n '1,120p' tests/__init__.py`
- `mkdir -p docs`
