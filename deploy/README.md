# Duzman deploy script

`deploy/deploy.sh` is a manual Operator tool for synchronizing a reviewed
Duzman working tree into the production layout with `rsync`. It defaults to a
dry-run and does not change the target unless `--apply` is explicit.

## Prerequisites

- Root access for apply mode.
- `rsync` installed on the host.
- The `duzman` user and `duzman` group already present on the host.
- A source directory that is the Duzman repo root. The script checks for
  `pyproject.toml` as its repo marker.

## Usage

```bash
sudo bash deploy/deploy.sh --dry-run
sudo bash deploy/deploy.sh --apply
sudo bash deploy/deploy.sh --apply --source /home/ubuntu/duzman --target /opt/duzman
```

Omitting both `--apply` and `--dry-run` is also a dry-run. `--apply` and
`--dry-run` cannot be used together.

## Behavior

The script resolves the default source from the location of `deploy/deploy.sh`,
not from the current working directory. It prints the source, target, mode, and
exclude list before rsync. Rsync uses archive mode with delete handling and
excludes Git metadata, virtual environments, Python/cache artifacts, logs, and
`.env` files. Runtime state that must persist across deploys is also excluded,
including `.config/`, `.venv/`, and `backups/`.

The source working tree can also contain shell, agent, and workspace artifacts
that do not belong in production. Rsync excludes `.bashrc`, `.profile`,
`.bash_logout`, `.gitconfig`, `.claude/`, `.codex/`, `.agents/`, and
`backups/` from `/opt/duzman`.

Apply mode requires root before rsync starts. If the target does not yet exist,
apply mode creates it and sets its owner to `duzman:duzman`. After a successful
apply rsync, it sets deployed target ownership to `duzman:duzman` while leaving
`.env` and `.env.*` entries untouched.

After rsync, dry-run and apply mode both inspect `<target>/.env` only for
existence, non-empty size, permissions, and owner. Missing or mismatched `.env`
state is printed as warnings and does not turn a successful rsync into a
failure.

### Source contamination warning

Before target handling, the script checks the source top level for the excluded
shell, agent, and workspace entries above. It prints a warning if any are
present, then continues in both dry-run and apply mode because those entries are
already excluded from rsync.

The script does not modify, delete, or attempt to clean the source. Source
remediation is the Operator's responsibility and is separate from deploy.

## Contaminated targets

Before rsync, the script checks only the top-level entries in the target for
home-directory or agent markers that do not belong in a deploy-only directory:
`.ssh`, `.npm`, `.cache`, `.local`, `.claude`, `.bash_history`, `.bashrc`,
`.profile`, `.lesshst`, `.gitconfig`, and `.claude.json`.

`.config/` is allowed in the production target because Day 10B stores
`/opt/duzman/.config/rclone/rclone.conf` there for rclone OAuth token refresh.
The directory is excluded from rsync, so deploy never deletes or overwrites
that runtime config.

Dry-run mode prints a warning with any detected marker names and continues so
the Operator can inspect the rsync plan. Apply mode refuses the target before
rsync with a pre-flight failure until the target is clean. This refusal is
intentional, not a bug; the script does not move, delete, copy, chmod, chown, or
read those marker entries.

For the production target, remediate a contaminated directory manually:

1. Back up `/opt/duzman/.env` to a safe location outside `/opt/duzman`.
2. Rename `/opt/duzman` to `/opt/duzman.contaminated.YYYYMMDD`.
3. Create a fresh `/opt/duzman` owned by `duzman:duzman`.
4. Place `.env` back into `/opt/duzman` with mode `600` and owner
   `duzman:duzman`.
5. Run `sudo bash deploy/deploy.sh --dry-run` to verify the clean state, then
   run `sudo bash deploy/deploy.sh --apply`.

## Boundaries

The script does not copy, create, overwrite, modify, chmod, or print the
contents of `/opt/duzman/.env`. `.env` and `.env.*` are excluded from rsync.
It does not invoke `sudo`, run systemd, or run database migrations.

The Operator must create `/opt/duzman/.env` manually when needed, set its mode
to `600`, and set its owner to `duzman:duzman`.

Systemd units, the local health service, and backups are handled by later Day
9B through Day 9D work, not by this script.

## Venv bootstrap

This script bootstraps the production venv at `/opt/duzman/.venv`.

Step 0, mandatory if `/opt/duzman` is not yet at latest main:

```bash
sudo bash deploy/deploy.sh --apply
```

Step 1:

```bash
sudo bash deploy/bootstrap_venv.sh
```

If the script reports `venv at /opt/duzman/.venv is valid; nothing to do`,
bootstrap is done. If it reports
`existing venv at /opt/duzman/.venv is invalid; rerun with --recreate`, run
Step 2.

Step 2, for an invalid existing venv or after a deploy refresh:

```bash
sudo bash deploy/bootstrap_venv.sh --recreate
```

Do not manually `rm -rf /opt/duzman/.venv`; always use `--recreate`. Do not
manually clean `/opt/duzman/.cache`. If it appears after bootstrap, that is a
regression and needs a new issue.

The script refuses to run if `/opt/duzman` is missing Day 9B or Day 9C.1
runtime files; run Step 0 first.

The success indicator is the final line `bootstrap_venv: success`.

## Systemd install

Prerequisite: `/opt/duzman/.venv` must be valid. Run
`sudo bash deploy/bootstrap_venv.sh` first if needed.

Review planned actions without writing files or calling systemctl:

```bash
sudo bash deploy/install_systemd.sh --dry-run
```

Install and enable the runtime umbrella and backup timer. This does not start
any service:

```bash
sudo bash deploy/install_systemd.sh
```

Start both child services through the umbrella:

```bash
sudo systemctl start duzman
```

Verify runtime state:

```bash
sudo systemctl status duzman duzman-health duzman-scheduler
sudo systemctl list-timers duzman-backup.timer --no-pager
curl -fsS http://127.0.0.1:8080/health
sudo journalctl -u duzman-scheduler -n 50 --no-pager
sudo journalctl -u duzman-health -n 50 --no-pager
```

The health endpoint should return `{"status":"ok",...}`. Scheduler logs should
include `scheduler_started jobs_count=N`; health logs should include
`health_server_started`.

Rollback if the first start fails:

```bash
sudo systemctl stop duzman
sudo journalctl -u duzman-health -n 100 --no-pager
sudo journalctl -u duzman-scheduler -n 100 --no-pager
sudo systemctl disable duzman
```

The disable command is optional when reverting the install. `systemctl stop
duzman` stops both children through the umbrella relationship.

`install_systemd.sh` does not touch `/opt/duzman/.env`; the Operator is
responsible for keeping `.env` correct. The installer overwrites the old stub
`duzman.service` silently. If `/opt/duzman/.venv` is missing or invalid, install
fails during preflight before any partial install.

## Backup and restore

Backup runs daily at 02:30 UTC via `duzman-backup.timer`. Encrypted file is
delivered to the configured Telegram backup channel and kept locally (last 7)
in `/opt/duzman/backups`.

Required env (in `/opt/duzman/.env`, mode 600, owner `duzman:duzman`):

- `BACKUP_GPG_PASSPHRASE` (canonical copy in Bitwarden)
- `TELEGRAM_CHAT_ID_BACKUP`

Manual trigger:

```bash
sudo systemctl start duzman-backup.service
```

Status:

```bash
sudo systemctl status duzman-backup.service
sudo journalctl -u duzman-backup.service -n 100 --no-pager
sudo systemctl list-timers duzman-backup.timer --no-pager
ls -la /opt/duzman/backups/
```

### Restore from backup

Recovery is manual. Target RTO 30 minutes. Get the encrypted backup from one of:
Telegram backup channel, `/opt/duzman/backups`, OneDrive (Day 9E when
available).

Decrypt (passphrase from Bitwarden, NOT from `.env` in a recovery scenario
where `.env` itself may be the lost asset):

```bash
gpg --decrypt --output backup.tar.gz duzman-YYYYMMDD-HHMMSS.tar.gz.gpg
```

Extract:

```bash
mkdir restore && tar -xzf backup.tar.gz -C restore
```

Verify contents:

```bash
ls -la restore/
head restore/db.sql
```

Restore database (DESTRUCTIVE for current data in the backed-up tables):

```bash
sudo -u postgres psql duzman < restore/db.sql
```

Verify row counts:

```bash
sudo -u postgres psql duzman -c "SELECT
  (SELECT count(*) FROM pattern_triggers) AS pattern_triggers,
  (SELECT count(*) FROM alert_deliveries) AS alert_deliveries,
  (SELECT count(*) FROM alembic_version) AS alembic_version;"
```

Restore configs and `.env` manually as needed from `restore/config/` and
`restore/.env`. Review `.env` before placing into `/opt/duzman/.env` (it
contains the backup passphrase itself).

## Weekly OneDrive backup

Weekly snapshot of the latest local encrypted daily backup uploaded
to OneDrive. Independent 12-week remote retention. Runs Sunday 03:00 UTC,
after the daily 02:30 UTC backup.

### One-time Operator setup

1. **Install rclone binary (upstream pinned).**
   - Download `rclone-v1.74.2-linux-amd64.zip` from
     https://github.com/rclone/rclone/releases/tag/v1.74.2
   - Verify SHA256 against the checksum on the release page.
   - Unzip; copy `rclone` to `/usr/local/bin/rclone`.
   - `sudo chown root:root /usr/local/bin/rclone`
   - `sudo chmod 755 /usr/local/bin/rclone`
   - Verify: `rclone version` (must start with `rclone v1.74.2`).

2. **Run OAuth flow on a machine with a browser.**
   - On Operator local machine (not VPS): `rclone config`
   - Create new remote named `onedrive` of type `onedrive`.
   - At the scopes prompt, select custom and enter:
     `Files.ReadWrite,offline_access`
   - Complete browser OAuth.
   - Verify with `rclone lsd onedrive:` locally.

3. **Transfer config to VPS.**
   - Run `sudo bash /opt/duzman/deploy/deploy.sh --dry-run` and then
     `sudo bash /opt/duzman/deploy/deploy.sh --apply` before the first OAuth
     config transfer when possible.
   - `scp ~/.config/rclone/rclone.conf vps:/tmp/rclone.conf.new`
   - On VPS: `sudo mv /tmp/rclone.conf.new /opt/duzman/.config/rclone/rclone.conf`
   - `sudo chown duzman:duzman /opt/duzman/.config/rclone/rclone.conf`
   - `sudo chmod 600 /opt/duzman/.config/rclone/rclone.conf`
   - If `rclone.conf` already exists from an earlier OAuth run, deploy is still
     safe: `deploy/deploy.sh` excludes `.config/` and preserves the file.

4. **Add env vars to `/opt/duzman/.env`.**
   - Verify `TELEGRAM_CHAT_ID_SYSTEM` is set (first shell consumer in Day 10B).
   - `TELEGRAM_CHAT_ID_BACKUP` already used by daily backup.

5. **Install systemd units.**
   - `sudo bash /opt/duzman/deploy/install_onedrive_backup.sh`

6. **Smoke test.**
   - As root: `sudo -u duzman RCLONE_CONFIG=/opt/duzman/.config/rclone/rclone.conf rclone lsd onedrive:`
   - Manual oneshot: `sudo systemctl start duzman-onedrive-backup.service`
   - Check status: `systemctl status duzman-onedrive-backup.service`
   - Check Telegram backup channel for success message.
   - Check `/opt/duzman/backups/onedrive_upload_manifest.jsonl` for new entry.

### Token refresh behavior

rclone OneDrive backend refreshes OAuth access tokens periodically
and persists the refreshed token back to rclone.conf. The systemd
service unit grants write access to /opt/duzman/.config/rclone to
allow this. The rclone.conf file remains mode 600 owned by duzman.
If you see unexpectedly frequent modifications to rclone.conf,
investigate.

### Restore from OneDrive

1. Download encrypted backup from OneDrive `/Duzman/Backups/<filename>`.
2. Decrypt: `gpg --decrypt --output backup.tar.gz backup.tar.gz.gpg` (enter passphrase from Bitwarden).
3. Extract: `tar xzf backup.tar.gz`.
4. Restore database: `psql -U duzman_app duzman < dump.sql`.
5. Restore configs and .env from extracted archive.
6. Verify row counts per table against pre-restore baseline.

### Reduced OAuth scopes — safety clause

Day 10B targets `Files.ReadWrite` + `offline_access` scopes only. If
during smoke test rclone operations fail with permission errors,
STOP. Do NOT re-run OAuth with broader scopes silently. Report the
exact non-secret error message in the PR thread and let Reviewer
decide whether scope expansion is appropriate.

### Failure behavior

- Failure marker: `/opt/duzman/backups/.last_onedrive_upload_failed`
- Failure notification: both `TELEGRAM_CHAT_ID_SYSTEM` and `TELEGRAM_CHAT_ID_BACKUP`
- Marker is removed automatically on next successful upload.
