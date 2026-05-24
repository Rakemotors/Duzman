# Codex git workflow investigation — 2026-05-24

## Codex CLI version and effective config

`codex --version` output:

```text
WARNING: proceeding, even though we could not update PATH: Read-only file system (os error 30)
codex-cli 0.133.0
```

Session sandbox values reported by the Codex harness for this run:

```text
sandbox_mode = "workspace-write"
approval_policy = "on-failure"
writable_roots = ["/home/ubuntu/.codex/memories", "/home/ubuntu/duzman"]
```

`~/.codex/config.toml` currently contains:

```toml
approval_policy = "never"
sandbox_mode = "danger-full-access"

[projects."/home/ubuntu/duzman"]
trust_level = "trusted"

[tui.model_availability_nux]
"gpt-5.5" = 4
```

No `requirements.toml` file was found under `~/.codex` at max depth 2. The equivalent rules file read was `~/.codex/rules/default.rules`. It contains no explicit `deny` rules. Relevant git rules present there:

```text
prefix_rule(pattern=["git", "add"], decision="allow")
prefix_rule(pattern=["git", "commit"], decision="allow")
prefix_rule(pattern=["git", "ls-files"], decision="allow")
prefix_rule(pattern=["git", "pull"], decision="allow")
prefix_rule(pattern=["touch", ".git/refs/heads/.codex-write-test"], decision="allow")
prefix_rule(pattern=["git", "checkout", "-b", "pr1-docs-sync-day6"], decision="allow")
prefix_rule(pattern=["git", "checkout", "-b", "pr-tz-v1.7"], decision="allow")
prefix_rule(pattern=["git", "fetch", "origin", "feat/gh-automation-layer:refs/remotes/origin/feat/gh-automation-layer"], decision="allow")
prefix_rule(pattern=["git", "fetch", "origin", "+feat/gh-automation-layer:refs/remotes/origin/feat/gh-automation-layer"], decision="allow")
prefix_rule(pattern=["git", "checkout", "-b", "techdebt/07-canonicalize-pricesnapshot"], decision="allow")
prefix_rule(pattern=["touch", ".git/codex_write_probe"], decision="allow")
prefix_rule(pattern=["git", "branch", "-f", "fix/agent-pr-check-allow-env-example", "9bcecb8"], decision="allow")
prefix_rule(pattern=["git", "fetch", "origin"], decision="allow")
prefix_rule(pattern=["git", "checkout", "feat/day8-ai-explanations"], decision="allow")
prefix_rule(pattern=["git", "rebase", "origin/main"], decision="allow")
prefix_rule(pattern=["git", "checkout", "main"], decision="allow")
prefix_rule(pattern=["git", "checkout", "-b", "docs/day8-architecture"], decision="allow")
prefix_rule(pattern=["/bin/bash", "-lc", "touch ~/duzman/.git/refs/.codex_write_probe 2>&1 && ls -la ~/duzman/.git/refs/.codex_write_probe && rm ~/duzman/.git/refs/.codex_write_probe"], decision="allow")
prefix_rule(pattern=["git", "checkout", "-b", "feat/day8-smoke-scripts"], decision="allow")
prefix_rule(pattern=["git", "checkout", "-b", "feat/day8-ai-runtime-wiring"], decision="allow")
prefix_rule(pattern=["git", "checkout", "-B", "feat/day8-smoke-scripts", "main"], decision="allow")
prefix_rule(pattern=["git", "switch", "feat/day8-smoke-scripts"], decision="allow")
prefix_rule(pattern=["git", "fetch", "--prune"], decision="allow")
prefix_rule(pattern=["git", "branch", "-D", "feat/day8-smoke-scripts"], decision="allow")
prefix_rule(pattern=["git", "checkout", "-b", "pr-tz-v1.8-claude-mcp-role"], decision="allow")
prefix_rule(pattern=["git", "checkout", "-b", "pr-tz-v1.9-document-status-policy"], decision="allow")
prefix_rule(pattern=["git", "checkout", "-b", "pr-fix-telegram-startup-digest-test"], decision="allow")
prefix_rule(pattern=["git", "branch", "-d", "day9a-deploy-layout-rsync"], decision="allow")
prefix_rule(pattern=["git", "switch", "-c", "pr-day9a-deploy-script"], decision="allow")
prefix_rule(pattern=["git", "checkout", "pr-day9a-deploy-script"], decision="allow")
prefix_rule(pattern=["git", "checkout", "-b", "pr-deps-fastapi-uvicorn"], decision="allow")
prefix_rule(pattern=["git", "switch", "-c", "pr-day9b-health-service"], decision="allow")
prefix_rule(pattern=["git", "switch", "-c", "pr-day9c1-scheduler-entrypoint"], decision="allow")
prefix_rule(pattern=["git", "switch", "-c", "pr-day9c15-bootstrap-venv"], decision="allow")
prefix_rule(pattern=["git", "checkout", "pr-day9c15-bootstrap-venv"], decision="allow")
prefix_rule(pattern=["git", "checkout", "-b", "pr-deps-consolidation"], decision="allow")
prefix_rule(pattern=["git", "checkout", "--detach", "origin/main"], decision="allow")
prefix_rule(pattern=["rm", "-f", ".git/index.lock"], decision="allow")
prefix_rule(pattern=["git", "checkout", "-b", "fix/issue-33-httpx-log-suppression"], decision="allow")
```

## Workspace git baseline

`git rev-parse --git-dir`:

```text
.git
```

`git status`:

```text
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean
```

`git remote -v`:

```text
origin	git@github.com:Rakemotors/Duzman.git (fetch)
origin	git@github.com:Rakemotors/Duzman.git (push)
```

`git config --list --local`:

```text
core.repositoryformatversion=0
core.filemode=true
core.bare=false
core.logallrefupdates=true
remote.origin.url=git@github.com:Rakemotors/Duzman.git
remote.origin.fetch=+refs/heads/*:refs/remotes/origin/*
branch.main.remote=origin
branch.main.merge=refs/heads/main
branch.docs/day7-telegram-spec.remote=origin
branch.docs/day7-telegram-spec.merge=refs/heads/docs/day7-telegram-spec
branch.chore/codex-deny-alembic-downgrade.remote=origin
branch.chore/codex-deny-alembic-downgrade.merge=refs/heads/chore/codex-deny-alembic-downgrade
branch.fix/agent-pr-check-allow-env-example.remote=origin
branch.fix/agent-pr-check-allow-env-example.merge=refs/heads/fix/agent-pr-check-allow-env-example
branch.pr-fix-telegram-startup-digest-test.remote=origin
branch.pr-fix-telegram-startup-digest-test.merge=refs/heads/pr-fix-telegram-startup-digest-test
branch.pr-day9c2-systemd-units.remote=origin
branch.pr-day9c2-systemd-units.merge=refs/heads/pr-day9c2-systemd-units
branch.pr-day9d-backup-systemd.remote=origin
branch.pr-day9d-backup-systemd.merge=refs/heads/pr-day9d-backup-systemd
branch.feat/day10b-onedrive-backup.remote=origin
branch.feat/day10b-onedrive-backup.merge=refs/heads/feat/day10b-onedrive-backup
branch.fix/issue-66-settings-extra-ignore.remote=origin
branch.fix/issue-66-settings-extra-ignore.merge=refs/heads/fix/issue-66-settings-extra-ignore
```

## Filesystem characterization of .git

`ls -la /home/ubuntu/duzman/.git`:

```text
total 88
drwxrwxr-x   8 ubuntu ubuntu  4096 May 24 08:44 .
drwxrwxr-x  17 ubuntu ubuntu  4096 May 24 11:38 ..
-rw-rw-r--   1 ubuntu ubuntu   631 May 24 08:30 COMMIT_EDITMSG
-rw-rw-r--   1 ubuntu ubuntu    88 May 24 08:43 FETCH_HEAD
-rw-rw-r--   1 ubuntu ubuntu    21 May 24 08:43 HEAD
-rw-rw-r--   1 ubuntu ubuntu    41 May 24 08:43 ORIG_HEAD
drwxrwxr-x   2 ubuntu ubuntu  4096 May 15 14:44 branches
-rw-rw-r--   1 ubuntu ubuntu  1127 May 24 08:30 config
-rw-rw-r--   1 ubuntu ubuntu    73 May 15 14:44 description
drwxrwxr-x   2 ubuntu ubuntu  4096 May 15 14:44 hooks
-rw-rw-r--   1 ubuntu ubuntu 26493 May 24 08:44 index
drwxrwxr-x   2 ubuntu ubuntu  4096 May 15 14:44 info
drwxrwxr-x   3 ubuntu ubuntu  4096 May 15 14:44 logs
drwxrwxr-x 259 ubuntu ubuntu  4096 May 24 08:43 objects
-rw-rw-r--   1 ubuntu ubuntu   112 May 22 20:23 packed-refs
drwxrwxr-x   5 ubuntu ubuntu  4096 May 24 06:21 refs
```

`ls -la /home/ubuntu/duzman/.git/refs`:

```text
total 24
drwxrwxr-x 5 ubuntu ubuntu 4096 May 24 06:21 .
drwxrwxr-x 8 ubuntu ubuntu 4096 May 24 08:44 ..
drwxrwxr-x 9 ubuntu ubuntu 4096 May 24 08:43 heads
drwxrwxr-x 3 ubuntu ubuntu 4096 May 15 14:44 remotes
-rw-rw-r-- 1 ubuntu ubuntu   41 May 24 06:21 stash
drwxrwxr-x 2 ubuntu ubuntu 4096 May 15 14:44 tags
```

`ls -la /home/ubuntu/duzman/.git/refs/heads`:

```text
total 80
drwxrwxr-x 9 ubuntu ubuntu 4096 May 24 08:43 .
drwxrwxr-x 5 ubuntu ubuntu 4096 May 24 06:21 ..
drwxrwxr-x 2 ubuntu ubuntu 4096 May 19 14:47 audit
drwxrwxr-x 2 ubuntu ubuntu 4096 May 20 05:00 chore
drwxrwxr-x 2 ubuntu ubuntu 4096 May 20 04:47 day7
drwxrwxr-x 2 ubuntu ubuntu 4096 May 20 16:00 docs
drwxrwxr-x 2 ubuntu ubuntu 4096 May 24 06:22 feat
drwxrwxr-x 2 ubuntu ubuntu 4096 May 24 08:30 fix
-rw-rw-r-- 1 ubuntu ubuntu   41 May 24 08:43 main
-rw-rw-r-- 1 ubuntu ubuntu   41 May 22 13:48 pr-day9a-deploy-script
-rw-rw-r-- 1 ubuntu ubuntu   41 May 23 07:07 pr-day9c15-bootstrap-venv
-rw-rw-r-- 1 ubuntu ubuntu   41 May 23 07:56 pr-day9c2-systemd-units
-rw-rw-r-- 1 ubuntu ubuntu   41 May 23 12:21 pr-day9d-backup-systemd
-rw-rw-r-- 1 ubuntu ubuntu   41 May 23 06:10 pr-deps-consolidation
-rw-rw-r-- 1 ubuntu ubuntu   41 May 22 07:18 pr-fix-telegram-startup-digest-test
-rw-rw-r-- 1 ubuntu ubuntu   41 May 19 04:57 pr-tz-v1.7
-rw-rw-r-- 1 ubuntu ubuntu   41 May 22 05:19 pr-tz-v1.8-claude-mcp-role
-rw-rw-r-- 1 ubuntu ubuntu   41 May 22 06:02 pr-tz-v1.9-document-status-policy
-rw-rw-r-- 1 ubuntu ubuntu   41 May 22 20:19 review-pr-52-day-9c1-scheduler-entrypoint
drwxrwxr-x 2 ubuntu ubuntu 4096 May 20 03:38 techdebt
```

`stat /home/ubuntu/duzman/.git/HEAD`:

```text
  File: /home/ubuntu/duzman/.git/HEAD
  Size: 21        	Blocks: 8          IO Block: 4096   regular file
Device: 8,1	Inode: 818988      Links: 1
Access: (0664/-rw-rw-r--)  Uid: ( 1000/  ubuntu)   Gid: ( 1000/  ubuntu)
Access: 2026-05-24 08:43:26.853094997 +0000
Modify: 2026-05-24 08:43:26.847094924 +0000
Change: 2026-05-24 08:43:26.848094937 +0000
 Birth: 2026-05-24 08:43:26.846094912 +0000
```

`stat /home/ubuntu/duzman/.git/config` before probes:

```text
  File: /home/ubuntu/duzman/.git/config
  Size: 1127      	Blocks: 8          IO Block: 4096   regular file
Device: 8,1	Inode: 819991      Links: 1
Access: (0664/-rw-rw-r--)  Uid: ( 1000/  ubuntu)   Gid: ( 1000/  ubuntu)
Access: 2026-05-24 08:30:43.704820910 +0000
Modify: 2026-05-24 08:30:38.927762717 +0000
Change: 2026-05-24 08:30:38.927762717 +0000
 Birth: 2026-05-24 08:30:38.926762705 +0000
```

`findmnt --target /home/ubuntu/duzman`:

```text
TARGET              SOURCE                         FSTYPE OPTIONS
/home/ubuntu/duzman /dev/sda1[/home/ubuntu/duzman] ext4   rw,nosuid,nodev,relatime,discard,errors=remount-ro,commit=30
```

`findmnt --target /home/ubuntu/duzman/.git`:

```text
TARGET                   SOURCE                              FSTYPE OPTIONS
/home/ubuntu/duzman/.git /dev/sda1[/home/ubuntu/duzman/.git] ext4   ro,nosuid,nodev,relatime,discard,errors=remount-ro,commit=30
```

Filtered `mount` lines touching `/home/ubuntu/duzman`:

```text
/dev/sda1 on /home/ubuntu/duzman type ext4 (rw,nosuid,nodev,relatime,discard,errors=remount-ro,commit=30)
/dev/sda1 on /home/ubuntu/duzman/.git type ext4 (ro,nosuid,nodev,relatime,discard,errors=remount-ro,commit=30)
tmpfs on /home/ubuntu/duzman/.agents type tmpfs (ro,nosuid,nodev,relatime,mode=555,uid=1000,gid=1000,inode64)
/dev/sda1 on /home/ubuntu/duzman/.codex type ext4 (ro,nosuid,nodev,relatime,discard,errors=remount-ro,commit=30)
```

## Write probes

Probe 1 command:

```sh
bash -lc 'probe="/home/ubuntu/duzman/.git/.codex_probe_$(date +%s)"; echo "probe_path=$probe"; touch "$probe"; code=$?; echo "touch_exit=$code"; if [ "$code" -eq 0 ]; then rm "$probe"; echo "rm_exit=$?"; else echo "reverted=not_created"; fi; exit "$code"'
```

Exit code: `1`

Output and stderr:

```text
probe_path=/home/ubuntu/duzman/.git/.codex_probe_1779622729
touch: cannot touch '/home/ubuntu/duzman/.git/.codex_probe_1779622729': Read-only file system
touch_exit=1
reverted=not_created
```

Revert status: no file was created, so no revert action was needed.

Probe 2 command:

```sh
bash -lc 'git config --local user.email "probe@local"; code=$?; echo "git_config_exit=$code"; if [ "$code" -eq 0 ]; then git config --local --unset user.email; echo "unset_exit=$?"; else echo "reverted=not_set"; fi; exit "$code"'
```

Exit code: `0`

Output and stderr:

```text
git_config_exit=0
unset_exit=0
```

Revert status: reverted successfully on the first attempt. A follow-up read-only `git config --local --get user.email` returned exit code `1` with no output, confirming `user.email` was not left set. A follow-up `git status` showed the working tree clean on `main`. During this probe, the harness displayed: `Approved command prefix saved: ["bash", "-lc", "git config --local user.email \"probe@local\"; code=$?; echo \"git_config_exit=$code\"; if [ \"$code\" -eq 0 ]; then git config --local --unset user.email; echo \"unset_exit=$?\"; else echo \"reverted=not_set\"; fi; exit \"$code\""]`. That makes this probe less representative of ordinary sandboxed `.git` writes than probes 1 and 3.

`stat /home/ubuntu/duzman/.git/config` after probe 2:

```text
  File: /home/ubuntu/duzman/.git/config
  Size: 1127      	Blocks: 8          IO Block: 4096   regular file
Device: 8,1	Inode: 819991      Links: 1
Access: (0664/-rw-rw-r--)  Uid: ( 1000/  ubuntu)   Gid: ( 1000/  ubuntu)
Access: 2026-05-24 11:43:08.486748366 +0000
Modify: 2026-05-24 11:43:08.486748366 +0000
Change: 2026-05-24 11:43:08.487748378 +0000
 Birth: 2026-05-24 11:43:08.486748366 +0000
```

Probe 3 command:

```sh
bash -lc 'orig=$(git branch --show-current); name="codex-probe-$(date +%s)"; echo "probe_branch=$name"; git checkout -b "$name"; code=$?; echo "checkout_new_exit=$code"; if [ "$code" -eq 0 ]; then git checkout "$orig"; back_code=$?; echo "checkout_back_exit=$back_code"; if [ "$back_code" -eq 0 ]; then git branch -D "$name"; echo "delete_exit=$?"; else echo "reverted=failed_checkout_back"; exit "$back_code"; fi; else echo "reverted=not_created"; fi; exit "$code"'
```

Exit code: `128`

Output and stderr:

```text
probe_branch=codex-probe-1779623001
fatal: cannot lock ref 'refs/heads/codex-probe-1779623001': Unable to create '/home/ubuntu/duzman/.git/refs/heads/codex-probe-1779623001.lock': Read-only file system
checkout_new_exit=128
reverted=not_created
```

Revert status: no branch was created, so no revert action was needed. A follow-up `git branch --show-current` returned `main`, and `git status` returned a clean working tree.

## Root cause hypothesis

Chosen hypothesis: read-only bind-mount of .git.

Evidence: `findmnt --target /home/ubuntu/duzman` reports the workspace root mounted `rw`, while `findmnt --target /home/ubuntu/duzman/.git` reports `.git` mounted separately with `ro` options. Direct creation of an ephemeral file inside `.git` failed with `Read-only file system`. Creating a probe branch failed when Git tried to create `.git/refs/heads/codex-probe-*.lock`, also with `Read-only file system`. The Codex rules file contains git `allow` rules and no explicit deny rule, so the observed failure is not explained by a deny-rule. The only ambiguous data point is the `git config --local` probe, which succeeded and reverted; the harness recorded that exact shell command as an approved prefix during execution, so it should not override the stronger mount and direct-write evidence.

## Recommendation

C. Recommend accepting the limitation and documenting manual git workflow as the sanctioned procedure.

The evidence points to a filesystem namespace decision in the Codex sandbox: `.git` is deliberately mounted read-only even though the workspace itself is writable. A narrowed deny-rule change would not address a read-only mount, and there is no evidence that this is a repository-local Git configuration problem. Until the sandbox can be configured to mount `.git` read-write for trusted Duzman sessions, the lowest-risk operational path is to document that Codex performs file edits and local verification, while the Operator performs git branch, commit, and push operations manually outside the Codex sandbox.
