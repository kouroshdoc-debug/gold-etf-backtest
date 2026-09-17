import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from backtest import equity_curve
from multi_asset_validation import evaluate
from download_validation import from_official_snapshot
from promotion_gate import assess
from robustness import load_historical_cash


def test_validation_parameters_are_frozen_to_baseline():
    cfg=json.loads(Path("config.json").read_text(encoding="utf-8"))
    assert cfg["validation"]["frozen_versions"] == ["V2", "V3"]
    assert cfg["validation"]["frozen_parameters"] == {
        "rsi_threshold": 10, "trend_window": 200, "v5_last_close_deviation": -0.002
    }


def test_historical_cash_alignment_and_compounding(tmp_path):
    path=tmp_path/"rates.csv"
    path.write_text("date,annual_rate\n20240101,0.21\n20240103,0.30\n",encoding="utf-8")
    rates=load_historical_cash(path,[20240101,20240102,20240103])
    assert rates.tolist() == [0.21,0.21,0.30]
    df=pd.DataFrame({"close":[100,100,100]})
    curve=equity_curve(df,pd.DataFrame(),0,cash_annual_rate=rates)
    expected=np.prod((1+rates.to_numpy())**(1/252))
    assert curve.iloc[-1] == pytest.approx(expected)


def test_cash_rate_rejects_lookback_gap(tmp_path):
    path=tmp_path/"rates.csv"
    path.write_text("date,annual_rate\n20240102,0.21\n",encoding="utf-8")
    with pytest.raises(ValueError,match="start on/before"):
        load_historical_cash(path,[20240101,20240102])


def test_validation_evaluator_does_not_search_parameters():
    n=700
    close=1000+np.arange(n)*2+35*np.sin(np.arange(n)/8)
    df=pd.DataFrame({
        "date":pd.date_range("2020-01-01",periods=n).strftime("%Y%m%d").astype(int),
        "open":close,"high":close*1.01,"low":close*.99,"last":close,"close":close,
        "volume":1,"value":1,"trades":1,"last_close_deviation":0,
    })
    cfg=json.loads(Path("config.json").read_text(encoding="utf-8"))
    full,oos,checks=evaluate(df,"V2",cfg)
    assert set(checks) == {"full_sample_trades","full_sample_return","full_sample_profit_factor","full_sample_drawdown","oos_trades","oos_return","oos_profit_factor","oos_drawdown"}
    assert full["trades"] >= 0 and oos["trades"] >= 0


def test_official_snapshot_rejects_wrong_inscode(tmp_path):
    path=tmp_path/"gohar.json"
    path.write_text(json.dumps({"closingPriceDaily":[{"insCode":999,"dEven":20240101}]}),encoding="utf-8")
    with pytest.raises(ValueError,match="inscode mismatch"):
        from_official_snapshot({"official_snapshot":str(path),"inscode":"123"})


def test_promotion_gate_fails_closed_with_one_mirrored_fund():
    cfg=json.loads(Path("config.json").read_text(encoding="utf-8"))
    manifest=[{"symbol":"عیار","status":"available","source":"TSETMC-via-pinned-third-party-mirror"}]
    validation=pd.DataFrame([{"symbol":"عیار","version":"V2","accepted":True},{"symbol":"عیار","version":"V3","accepted":True}])
    forward=[{"version":"V2","data_fresh":True,"next_open_action":"CASH"},{"version":"V3","data_fresh":True,"next_open_action":"HOLD"}]
    result=assess(cfg,manifest,validation,forward)
    assert {row["status"] for row in result} == {"RESEARCH_ONLY"}
    assert all(row["execution_authorized"] is False for row in result)
    assert all(row["accepted_official_funds"] == [] for row in result)
