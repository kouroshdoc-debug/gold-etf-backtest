"""Frozen-parameter validation of V2/V3 on independent gold ETFs."""
import json
from pathlib import Path

import pandas as pd

from backtest import metrics, trade_log


def evaluate(df, version, cfg):
    backtest = cfg["backtest"]
    validation = cfg["validation"]
    frozen = validation["frozen_parameters"]
    acceptance = validation["acceptance"]
    cost = backtest["one_way_cost"]
    kwargs = {
        "thr": frozen["rsi_threshold"],
        "trend": frozen["trend_window"],
        "dev": frozen["v5_last_close_deviation"],
        "cost": cost,
    }
    full_trades = trade_log(df, version, **kwargs)
    full = metrics(full_trades, (len(df) - 1) / 252, df, cost)
    cut = int(len(df) * (1 - backtest["oos_fraction"]))
    oos_trades = trade_log(df, version, start=cut, **kwargs)
    oos_df = df.iloc[cut:].reset_index(drop=True)
    if not oos_trades.empty:
        oos_trades = oos_trades.copy()
        oos_trades["entry_i"] -= cut
        oos_trades["exit_i"] -= cut
    oos = metrics(oos_trades, max((len(oos_df) - 1) / 252, 1 / 252), oos_df, cost)
    checks = {
        "full_sample_trades": full["trades"] >= acceptance["minimum_full_sample_trades"],
        "full_sample_return": full["total_return"] > acceptance["minimum_total_return"],
        "full_sample_profit_factor": full["profit_factor"] > acceptance["minimum_profit_factor"],
        "full_sample_drawdown": full["max_drawdown"] > acceptance["maximum_drawdown_floor"],
        "oos_trades": oos["trades"] >= acceptance["minimum_oos_trades"],
        "oos_return": oos["total_return"] > acceptance["minimum_total_return"],
        "oos_profit_factor": oos["profit_factor"] > acceptance["minimum_profit_factor"],
        "oos_drawdown": oos["max_drawdown"] > acceptance["maximum_drawdown_floor"],
    }
    return full, oos, checks


def main():
    cfg = json.loads(Path("config.json").read_text(encoding="utf-8"))
    manifest_path = Path("results/validation_data_manifest.json")
    provenance = {x["symbol"]: x for x in json.loads(manifest_path.read_text(encoding="utf-8"))}
    rows = []
    for instrument in cfg["validation"]["instruments"]:
        if provenance[instrument["symbol"]].get("status") != "available":
            continue
        df = pd.read_csv(instrument["output"])
        for version in cfg["validation"]["frozen_versions"]:
            full, oos, checks = evaluate(df, version, cfg)
            rows.append({
                "symbol": instrument["symbol"], "inscode": instrument["inscode"], "version": version,
                "data_source": provenance[instrument["symbol"]]["source"],
                "data_first": int(df.date.iloc[0]), "data_last": int(df.date.iloc[-1]),
                **{f"full_{k}": v for k, v in full.items()},
                **{f"oos_{k}": v for k, v in oos.items()},
                **{f"check_{k}": v for k, v in checks.items()},
                "accepted": all(checks.values()),
            })
    result = pd.DataFrame(rows)
    Path("results").mkdir(exist_ok=True)
    result.to_csv("results/multi_asset_validation.csv", index=False)
    configured = len(cfg["validation"]["instruments"])
    evaluated = result["symbol"].nunique() if not result.empty else 0
    coverage = {
        "configured_instruments": configured,
        "evaluated_instruments": int(evaluated),
        "coverage_complete": evaluated == configured,
        "missing_instruments": [s for s, item in provenance.items() if item.get("status") != "available"],
    }
    Path("results/validation_coverage.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = [
        "# Frozen multi-ETF validation",
        "",
        "V2/V3 use the original RSI(2)<10 entries and SMA5 exits. No parameter was selected on validation ETFs.",
        "A pass requires every pre-registered full-sample and OOS gate in `config.json`.",
        "Third-party mirrors are pinned and disclosed; they are not represented as a direct official download.",
        f"Coverage: {evaluated}/{configured}; missing instruments: {', '.join(coverage['missing_instruments']) or 'none'}.",
        "",
        "```csv",
        result.to_csv(index=False) if not result.empty else "no evaluated instruments",
        "```",
    ]
    Path("results/multi_asset_validation.md").write_text("\n".join(report), encoding="utf-8")
    print(result.to_string(index=False))


if __name__ == "__main__":
    main()
