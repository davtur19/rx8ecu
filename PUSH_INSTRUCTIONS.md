# Pushing to GitHub

Run these from this repo on a machine with your GitHub login.

The push is done by the **repo owner** on a machine that has his GitHub
credentials. This working machine can't push: it has no credentials beyond the
stored PAT, its `https_proxy` is currently down, and the repo must stay
open-source — so the publish is the owner's to make.

Repo: **github.com/davtur19/rx8ecu** — **already exists** and is **public**. Its
only content is a LICENSE "Initial commit" on branch `master` (unrelated
history; default branch is `master`). The local repo is the **AGPL-3.0** public
release of the RX-8 PCM reverse-engineering project: the byte-exact reassembly
pipeline for the 9 public stock ROMs, tools, annotated sources, verified C
lifts, docs — everything needed to reproduce it. Nothing has been pushed yet;
`origin` is already set to `https://github.com/davtur19/rx8ecu.git` (fetch+push).

## 0. Preflight — all must be true before pushing

```bash
# a) remote points at the right repo (fetch AND push)
git remote -v        # expect origin -> https://github.com/davtur19/rx8ecu.git (fetch+push)

# b) working tree clean
git status           # expect "nothing to commit, working tree clean"

# c) MANIFEST regenerated — matches the tracked tree (count from the MANIFEST header)
git ls-files | wc -l               # expect: matches the count stated in MANIFEST.md
[ "$(git ls-files | wc -l)" = "$(grep -oE '[0-9]+ entries' MANIFEST.md | head -1 | grep -oE '[0-9]+')" ] \
  && echo "MANIFEST OK ($(git ls-files | wc -l) entries)"
#    note: the MANIFEST header states "**N entries, ...**"; the check above is
#    dynamic — it fails unless git ls-files | wc -l == the count in the header.
#    if stale: regenerate MANIFEST.md from `git ls-files`, commit, re-check

# d) byte-exact rebuild of all 9 public stock ROMs (~a few minutes)
make verify-all      # expect 9/9 BYTE-EXACT

# e) privacy sweep — 0 genuine leaks (only legit PRIVATE/policy mentions remain)
git grep -E '[REDACTED]|[REDACTED]|[REDACTED]|[REDACTED]|\.i64|\.gar'
```

If anything above fails, stop: fix it, commit, and re-run the checklist.

## 1. Credentials

Already configured on the owner machine: the global credential helper is set
(`git config --global credential.helper store`) with a github.com entry in
`~/.git-credentials` — a PAT with full access to this repo only. Confirm it
works:

```bash
git ls-remote https://github.com/davtur19/rx8ecu.git   # prints refs, no prompt
```

If a broken proxy is set in the shell, bypass it:

```bash
git -c http.proxy= -c https.proxy= ls-remote https://github.com/davtur19/rx8ecu.git
# or: unset https_proxy http_proxy all_proxy, then the plain command above
```

(Alternative check: `printf 'protocol=https\nhost=github.com\n\n' | git credential fill`
should echo the stored username/password without prompting.)

## 2. Push `main`

The repo is already on branch `main`; the `-M` below is a no-op safety net. If
Git identity is not configured on the owner machine, set it per-command:

```bash
git branch -M main
git -c user.name=davtur19 -c user.email=davtur19@users.noreply.github.com \
    push -u origin main
```

(If identity is already configured there: `git push -u origin main`.)

Proxy-bypass variant (if the environment still has the broken proxy):

```bash
git -c http.proxy= -c https.proxy= push -u origin main
```

## 3. Fix the GitHub default branch

GitHub's default branch is still `master` (the LICENSE-only "Initial commit" —
unrelated history), so the repo page would render that LICENSE, not the README.
Switch the default to `main`:

```bash
gh repo edit davtur19/rx8ecu --default-branch main
```

Then deal with `master` — two options:

- **Delete it (recommended):** `git push origin :master`. Clean — `master`
  carries nothing `main` doesn't already have. The LICENSE is identical (it
  ships in the repo root on `main`; verify with `git ls-tree main LICENSE`), so
  nothing is lost.
- **Archive it:** `git push origin master:master-license-archive`. Keeps the
  original "Initial commit" around under a descriptive name if you ever want
  the provenance. Downside: one extra branch in the listing to explain.

## 4. Post-push verification

```bash
git ls-remote origin   # main present; master removed (or renamed)
```

Then open https://github.com/davtur19/rx8ecu and confirm:

- the **README renders** on the repo page (default branch is now `main`),
- the license is detected as **AGPL-3.0**,
- the gitignored/excluded private content is **absent** from the file listing:
  modded/tuned images, the [REDACTED] dump, `.i64`/`.gar` project files,
  `[REDACTED]/` — spot-check a few directories on the page.

## DO NOT

- **Never push the excluded private content** — no modded tunes, no [REDACTED]
  dump, no `.i64`/`.gar` project files, no `[REDACTED]/`. They are
  git-ignored on purpose (see `.gitignore`) and stay local forever.
- **Keep the repo public under AGPL-3.0** — owner policy: it *must* stay open
  forever. Don't make it private, don't relicense.
- **Never rotate/regenerate the GitHub token without re-storing it** — the
  `~/.git-credentials` entry must be refreshed to match, or the next
  credential-helper lookup fails.
