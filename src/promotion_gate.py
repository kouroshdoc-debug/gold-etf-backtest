"""Fail-closed promotion gate from research to shadow/paper monitoring."""
import json
from pathlib import Path

import pandas as pd


OFFICIAL_SOURCES = {"TSETMC-live", "TSETMC-official-snapshot"}


def assess(cfg, manifest, validation, forward_rows):
    rules = cfg["validation"]
    required = int(rules["minimum_independent_funds_for_paper"])
    require_official = bool(rules["require_official_data_for_paper"])
    available = {item["symbol"]: item for item in manifest if item.get("status") == "available"}
    fresh = all(bool(row["data_fresh"]) for row in forward_rows if row["version"] in rules["frozen_versions"])
    output = []
    for version in rules["frozen_versions"]:
        subset = validation[validation["version"] == version] if not validation.empty else validation
        accepted = subset[subset["accepted"].astype(str).str.lower() == "true"] if not subset.empty else subset
        accepted_symbols = sorted(accepted["symbol"].unique().tolist()) if not accepted.empty else []
        official_symbols = sorted(
            symbol for symbol in accepted_symbols if available.get(symbol, {}).get("source") in OFFICIAL_SOURCES
        )
        checks = {
            "primary_data_fresh": fresh,
            "minimum_independent_funds": len(accepted_symbols) >= required,
            "official_data_requirement": (len(official_symbols) >= required) if require_official else True,
            "all_configured_funds_evaluated": len(available) == len(rules["instruments"]),
        }
        if not fresh:
            status = "STALE_DATA"
        elif all(checks.values()):
            status = "PAPER_WATCH_CANDIDATE"
        else:
            status = "RESEARCH_ONLY"
        signal = next(row for row in forward_rows if row["version"] == version)
        output.append({
            "version": version,
            "status": status,
            "execution_authorized": False,
            "mode": "SHADOW_ONLY" if status != "PAPER_WATCH_CANDIDATE" else "PAPER_ONLY",
            "primary_next_open_action": signal["next_open_action"],
            "accepted_independent_funds": accepted_symbols,
            "accepted_official_funds": official_symbols,
            "required_independent_funds": required,
            "checks": checks,
        })
    return output


def main():
    cfg = json.loads(Path("config.json").read_text(encoding="utf-8"))
    manifest = json.loads(Path("results/validation_data_manifest.json").read_text(encoding="utf-8"))
    validation_path = Path("results/multi_asset_validation.csv")
    validation = pd.read_csv(validation_path) if validation_path.exists() and validation_path.stat().st_size else pd.DataFrame()
    forward_rows = json.loads(Path("results/forward_signal.json").read_text(encoding="utf-8"))
    result = assess(cfg, manifest, validation, forward_rows)
    Path("results/promotion_gate.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    flat = []
    for row in result:
        flat.append({
            "version": row["version"], "status": row["status"], "mode": row["mode"],
            "execution_authorized": row["execution_authorized"],
            "primary_next_open_action": row["primary_next_open_action"],
            "accepted_funds": len(row["accepted_independent_funds"]),
            "accepted_official_funds": len(row["accepted_official_funds"]),
            "required_funds": row["required_independent_funds"],
        })
    pd.DataFrame(flat).to_csv("results/paper_watchlist.csv", index=False)
    print(pd.DataFrame(flat).to_string(index=False))


if __name__ == "__main__":
    main()
