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
`.env` files.

Apply mode requires root before rsync starts. If the target does not yet exist,
apply mode creates it and sets its owner to `duzman:duzman`. After a successful
apply rsync, it sets deployed target ownership to `duzman:duzman` while leaving
`.env` and `.env.*` entries untouched.

After rsync, dry-run and apply mode both inspect `<target>/.env` only for
existence, non-empty size, permissions, and owner. Missing or mismatched `.env`
state is printed as warnings and does not turn a successful rsync into a
failure.

## Contaminated targets

Before rsync, the script checks only the top-level entries in the target for
home-directory or agent markers that do not belong in a deploy-only directory:
`.ssh`, `.npm`, `.cache`, `.local`, `.config`, `.claude`, `.bash_history`,
`.bashrc`, `.profile`, `.lesshst`, `.gitconfig`, and `.claude.json`.

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
