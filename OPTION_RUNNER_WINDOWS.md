# Windows self-hosted runner for option snapshots

GitHub-hosted runners cannot currently reach the official TSETMC/TSE option
endpoints. The scheduled `Lotus option forward snapshots` workflow therefore
runs real capture only on a Windows self-hosted runner. It never converts
Last/Close into executable Bid/Ask and remains research-only.

## One-time setup

1. Open this repository on GitHub and go to **Settings → Actions → Runners**.
2. Choose **New self-hosted runner → Windows → x64**.
3. In an empty permanent folder such as `C:\actions-runner`, run the exact
   download, configure and service commands GitHub displays. The registration
   token is short-lived; do not commit or share it.
4. When `config.cmd` asks for labels, keep the default labels
   `self-hosted`, `Windows`, and `X64`.
5. Install the runner as a Windows service (`.\svc.cmd install`, then
   `.\svc.cmd start`)
   from an Administrator terminal so scheduled runs work while GitHub Desktop
   is closed.
6. Confirm the runner shows **Idle** on the GitHub Runners page.

## Verification

Open **Actions → Lotus option forward snapshots → Run workflow** and select
`self-hosted-windows`. A valid run must:

- create `results/option_snapshot_status.json` with status `CAPTURED`;
- append at least one genuine two-sided Bid/Ask row;
- upload the status artifact; and
- commit only `data/option_snapshots_gated.csv`.

If TSETMC is unavailable locally, the job fails closed and writes no fabricated
quote. The `github-hosted-diagnostic` option is only a connectivity diagnostic.
It can finish successfully with status `SOURCE_UNAVAILABLE`; this is not a
successful market-data capture.
