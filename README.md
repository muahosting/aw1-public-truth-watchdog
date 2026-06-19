# AW1 GitHub External Public Truth Watchdog

This package creates the second independent external vantage required by AW1's public truth gate. It must run on a GitHub-hosted runner, not on the AW1 GPU node and not on the chat node.

The package does not depend on the production AW1 directory being a Git worktree.

## Files

- `.github/workflows/aw1-public-truth-watchdog.yml`: scheduled/manual GitHub Actions workflow.
- `scripts/check_public_truth.py`: public HTTPS checker run by GitHub Actions.
- `results/aw1_github_public_truth_result.sample.json`: contract example.
- `docs/aw1_github_public_truth_result.json`: placeholder for GitHub Pages. It is intentionally `FAIL` until the workflow replaces it.

## What The Workflow Checks

The GitHub-hosted runner fetches these public HTTPS URLs with no-cache headers:

- `https://aw1.awai.vn/log/latest.json`
- `https://aw1.awai.vn/log/`
- `https://aw1.awai.vn/log/model_improvement_queue_public.json`
- `https://chat.awai.vn/log/latest.json`

It writes `aw1_github_public_truth_result.json` containing:

- `vantage_id=external_github_actions`
- runner/network fields: `network`, `runner_os`, `run_id`, `repository`
- `fetched_at`, `generated_at`
- per URL: `status_code`, `generated_at`, `cache_control`, `etag`, `last_modified`, `body_hash`, `elapsed_ms`
- AW1 verdict fields: `effective_verdict`, `latest_effective_verdict`, `latest_verdict`, `stale_latest`
- queue fields: `queue_item_count`, `model_improvement_candidate_count`
- chat fields: `verdict`, `render_result`
- top-level `pass`, `verdict`, `fail_reason`

## Deploy In A Separate GitHub Repo

1. Create a new GitHub repository, for example `aw1-public-truth-watchdog`.
2. Copy this directory's contents to that repository root:

   ```bash
   cp -a ops/aw1-public-truth-watchdog-github/. /path/to/aw1-public-truth-watchdog/
   ```

3. Commit and push:

   ```bash
   cd /path/to/aw1-public-truth-watchdog
   git init
   git add .
   git commit -m "Add AW1 public truth watchdog"
   git branch -M main
   git remote add origin git@github.com:<owner>/<repo>.git
   git push -u origin main
   ```

4. In GitHub, enable Actions for the repo.
5. Run **AW1 Public Truth Watchdog** manually once from the Actions tab.
6. Keep the schedule enabled. The default schedule is every 30 minutes.

## Publish The Result JSON

Preferred: GitHub Pages.

1. In the GitHub repo, open **Settings -> Pages**.
2. Set source to **Deploy from a branch**.
3. Select branch `main`, folder `/docs`.
4. After the workflow runs, the stable URL is:

   ```text
   https://<owner>.github.io/<repo>/aw1_github_public_truth_result.json
   ```

Alternative: raw.githubusercontent.com.

The workflow also commits the same JSON to `results/`:

```text
https://raw.githubusercontent.com/<owner>/<repo>/main/results/aw1_github_public_truth_result.json
```

Raw URLs can be cached by GitHub/CDN; GitHub Pages is preferred for a stable public endpoint.

## Configure AW1 To Read The GitHub Vantage

On AW1, set the URL for the watchdog process environment or one-shot shell:

```bash
export AW1_GITHUB_WATCHDOG_RESULT_URL="https://<owner>.github.io/<repo>/aw1_github_public_truth_result.json"
export AW1_GITHUB_WATCHDOG_TTL_SECONDS=3600
```

Then run:

```bash
cd /srv/sieutocviet-ai/current
scripts/aw1-external-public-truth-watchdog
/usr/local/bin/aw1-public-log-index
```

Expected PASS requires:

- `external_jina_reader` PASS
- `external_github_actions` PASS
- AW1 latest `PASS`
- `stale_latest=false`
- queue count `0`
- model improvement candidate count `0`
- chat latest `PASS`
- chat `render_result=PASS`
- no `PASS_WITH_NEWER_RUNTIME_LOG`

If the GitHub JSON is missing, stale, invalid, or reports FAIL, AW1 must remain BLOCKED/DEGRADED and Phase 2 must not open.

## Local Dry Run

From the GitHub repo checkout:

```bash
python3 -m py_compile scripts/check_public_truth.py
python3 scripts/check_public_truth.py || true
cat results/aw1_github_public_truth_result.json
```

The script may exit non-zero when AW1 public truth is currently blocked. That is expected and should not be forced to PASS.

## Disable / Rollback

To disable the GitHub vantage on AW1:

```bash
unset AW1_GITHUB_WATCHDOG_RESULT_URL
unset AW1_GITHUB_WATCHDOG_RESULT_PATH
scripts/aw1-external-public-truth-watchdog || true
/usr/local/bin/aw1-public-log-index
```

To remove the GitHub repo integration, disable the workflow in GitHub Actions or delete the repository. AW1 will correctly return to `external_vantage_count=1/2` and keep Phase 2 blocked.
