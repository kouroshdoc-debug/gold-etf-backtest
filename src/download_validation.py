"""Download independent ETF histories, preferring live TSETMC over a pinned mirror."""
import json
import os
import subprocess
from pathlib import Path

import pandas as pd

from download_tsetmc import clean, fetch


def get_json(url):
    headers = ["-H", "Accept: application/vnd.github+json"]
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers += ["-H", f"Authorization: Bearer {token}"]
    command = ["curl", "-fsSL", "--connect-timeout", "10", "--max-time", "60", *headers, url]
    result = subprocess.run(command, capture_output=True, text=True, timeout=70)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"curl exit {result.returncode}")
    return json.loads(result.stdout)


def from_pinned_mirror(spec):
    mirror = spec["mirror"]
    owner_repo = mirror["repository"]
    commit = mirror["commit"]
    directory = mirror["directory"]
    listing_url = f"https://api.github.com/repos/{owner_repo}/contents/{directory}?ref={commit}"
    listing = get_json(listing_url)
    names = sorted(item["name"] for item in listing if item["type"] == "file" and item["name"].endswith(".json"))
    if not names:
        raise ValueError(f"no monthly JSON files in {owner_repo}/{directory}@{commit}")
    records = []
    metadata = []
    for name in names:
        url = f"https://raw.githubusercontent.com/{owner_repo}/{commit}/{directory}/{name}"
        payload = get_json(url)
        if str(payload.get("ins_code")) != str(spec["inscode"]):
            raise ValueError(f"inscode mismatch in {name}")
        if payload.get("source") != "TSETMC":
            raise ValueError(f"unexpected source in {name}: {payload.get('source')}")
        records.extend(payload.get("records", []))
        metadata.append((name, payload.get("record_count"), len(payload.get("records", []))))
    if any(expected != actual for _, expected, actual in metadata):
        raise ValueError("mirror partition record_count mismatch")
    raw = pd.DataFrame(records).rename(columns={
        "date": "dEven", "open": "pFirst", "high": "pMax", "low": "pMin",
        "last": "pLast", "close": "pClosing", "volume": "qTotTran5J",
        "value": "qTotCap", "trades": "zTotTran",
    })
    return clean(raw), {
        "source": "TSETMC-via-pinned-third-party-mirror",
        "repository": owner_repo,
        "commit": commit,
        "partitions": len(names),
    }


def from_official_snapshot(spec):
    path = Path(spec["official_snapshot"])
    parts = sorted(path.parent.glob(path.name + ".part-*"))
    if path.exists():
        text = path.read_text(encoding="utf-8")
        files = [str(path)]
    elif parts:
        text = "".join(item.read_text(encoding="utf-8") for item in parts)
        files = [str(item) for item in parts]
    else:
        raise FileNotFoundError(f"official snapshot not found: {path} or {path}.part-*")
    payload = json.loads(text)
    rows = payload.get("closingPriceDaily", payload if isinstance(payload, list) else [])
    if not rows:
        raise ValueError(f"official snapshot is empty: {path}")
    codes = {str(row.get("insCode")) for row in rows if row.get("insCode") is not None}
    if codes and codes != {str(spec["inscode"])}:
        raise ValueError(f"official snapshot inscode mismatch: expected {spec['inscode']}, found {sorted(codes)}")
    return clean(pd.DataFrame(rows)), {
        "source": "TSETMC-official-snapshot",
        "snapshot_files": files,
    }


def main():
    cfg = json.loads(Path("config.json").read_text(encoding="utf-8"))
    manifest = []
    for spec in cfg["validation"]["instruments"]:
        errors = []
        try:
            data = clean(fetch(spec["inscode"]))
            provenance = {"source": "TSETMC-live"}
        except Exception as exc:
            print(f"{spec['symbol']}: live TSETMC unavailable: {exc}")
            errors.append(f"live: {type(exc).__name__}: {exc}")
            try:
                data, provenance = from_official_snapshot(spec)
            except Exception as snapshot_exc:
                errors.append(f"official_snapshot: {type(snapshot_exc).__name__}: {snapshot_exc}")
                if "mirror" in spec:
                    try:
                        data, provenance = from_pinned_mirror(spec)
                    except Exception as mirror_exc:
                        errors.append(f"mirror: {type(mirror_exc).__name__}: {mirror_exc}")
                        data = None
                else:
                    data = None
        if data is None:
            manifest.append({
                "symbol": spec["symbol"], "inscode": spec["inscode"],
                "path": spec["output"], "status": "missing", "errors": errors,
            })
            print(f"{spec['symbol']}: no auditable history available; recorded as missing")
            continue
        output = Path(spec["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        data.to_csv(output, index=False)
        manifest.append({
            "symbol": spec["symbol"], "inscode": spec["inscode"], "path": str(output),
            "status": "available",
            "rows": len(data), "first": int(data.date.iloc[0]), "last": int(data.date.iloc[-1]),
            **provenance,
        })
    Path("results").mkdir(exist_ok=True)
    Path("results/validation_data_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
