# Handoff

> Written at session end or before hitting a usage limit.
> The next session (or different model) starts here.
> Overwrite this file with each new handoff.

# Handoff – 2026-06-06
Model: Claude Opus 4.8 (operator session: hub deployment)

## Done in this session
The watcher code was already complete (WI-1/1b/2/3/5/7 committed; WI-4 + WI-6
deferred to IDEAS). This session was operator-side — deployed the watcher onto the
always-on hub `charlie-mini-pc` and verified it end-to-end.
- **Mini-PC Docker migration:** moved Docker off the eMMC onto the USB HDD
  `/srv/cloud` (data-root `/srv/cloud/docker` + all DB bind mounts under
  `/srv/cloud/appdata/*`), `daemon.json` data-root + `RequiresMountsFor=/srv/cloud`,
  compose bind paths rewritten. Reboot-tested (auto-mount + all 6 containers
  auto-start). Originals kept on the eMMC as a safety net (not yet deleted).
- **Hub watcher deploy:** installed uv (`~/.local/bin`); transferred this repo from
  the workstation WSL via a tarball (the GitHub repo is **private** → a hub
  `git clone` failed for lack of credentials); `uv sync`; wrote
  `/home/charlie/.config/vault_watcher/env` (mode 600, **reused the workstation's
  GEMINI_API_KEY**) with the `/srv/cloud/*` paths; `loginctl enable-linger charlie`
  (worked **without sudo**); linked + enabled + started
  `obsidian-inbox-watcher.hub.service` (user unit).
- **E2E test passed:** a `.txt` in `/srv/cloud/inbox/raw` became a
  `domain`-frontmatter note in `/srv/cloud/vault/notes/inbox` in ~16 s (inotify on
  ext4); original archived. Test artifacts cleaned up.

## In progress
- Nothing in flight. Service is `active (running)` + `enabled`.

## Next concrete step (operator, on the hub)
- **DONE 2026-06-06 — vault Syncthing sync:** `titan-vault` shares hub
  `/srv/cloud/vault` ↔ workstation `F:\vault` (bidirectional, `.stignore` excludes
  `.git`/`.obsidian` caches). Verified both ways. Hub & workstation were already
  paired devices; workstation runs SyncTrayzor (autostart already set). Hub syncthing
  is the Docker container — it needed a new bind mount
  `/srv/cloud/vault:/var/syncthing/titan-vault`. The personal `Obsidian-KI-Vault`
  share (`C:\Users\charl\Documents\Obsidian`) is separate and was left untouched.
- **NEXT: raw-input path** to `/srv/cloud/inbox/raw`. The Telegram capture service
  (Appendix A) runs on the hub and writes raw files directly (no Syncthing). For
  phone/laptop drops via Syncthing, mind the receive-only "hub consumes files"
  subtlety (the watcher moves files out of raw → a receive-only folder then shows
  "locally changed"). Design this before wiring it.
- Then **restic backups** to the H100 NAS (needs sudo + NFS/SMB details). Note: the
  hub's Syncthing vault mirror is an off-machine *copy*, not a real backup (deletes
  propagate) — restic is still needed.
- **Cleanup:** delete the eMMC Docker originals (~10 G: `/var/lib/docker`,
  `/data/mysql`, old `docker/*` bind dirs) + dangling volumes `38a0ee…`, `n8n_data`.

## Open questions / decisions needed
- Workstation Syncthing topology (above).
- restic: H100 over NFS or SMB, mount path, credentials.
- WI-4 stays deferred (re-confirmed this session).

## Files the next session must read first
- docs/ai/plans/2026-05-29-hub-migration-and-resilience.md
- docs/ai/CURRENT_TASK.md, docs/ai/DECISIONS.md, src/obsidian_inbox_watcher/main.py

## Notes / gotchas discovered
- **Hub deployment needs NO sudo:** `enable-linger` worked without it, and
  `systemctl --user` works over SSH with `XDG_RUNTIME_DIR=/run/user/$(id -u)`.
- The GitHub repo is **private** and the hub has no creds → deploy by transferring
  the repo from the workstation, not `git clone`. Future hub updates need a PAT /
  deploy key, or another tarball push.
- **Workstation WSL networking** often falls back to `networkingMode None` (no net
  in WSL → cannot push from WSL); fix with `wsl --shutdown` then restart.
- Hub access: a local SSH shortcut script → `ssh <hub-user>@<hub-ip>`.
- Hub env paths (absolute, systemd doesn't expand `~`): see deploy/README.md hub section.
