"""effluent-09 红测乙（limit_in_b）：对账不得累计超口限流量。

口径裁决（与红测甲同源）：
- 对账侧识别超限必须复用排放口本口限值（first_exceed + outfalls 限值），
  不得只拿许可帽 compare_to_caps 充当口限比较；
- 超口限批剔除出对账累计：不进 samples 明细、不计入累计流量；
- 合规批仍正常参与对账，证明链不受影响。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import app
from db import init_db

PERMIT = "DP-2026-E01"
OVER_CODE = "SM-OF-E1-A-002"  # 夹具预置：COD58 > OF-E1-A 口限50，旁路挂起


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "limit_b.db")
    init_db()
    c = TestClient(app)
    tok = c.post(
        "/api/login", json={"username": "admin", "password": "admin123"}
    ).json()["token"]
    c.headers.update({"Authorization": "Bearer " + tok})
    return c


def test_reconcile_excludes_over_limit_sample_and_its_flow(client: TestClient):
    data = client.get(f"/api/reconcile/{PERMIT}").json()
    codes = [s["sample_code"] for s in data["samples"]]

    # 超口限批不得进入对账明细
    assert OVER_CODE not in codes

    # 剔除明细须说明裁决来源是口限禁入，而不是静默丢数
    excluded = data["excluded_samples"]
    hit = next(x for x in excluded if x["sample_code"] == OVER_CODE)
    assert hit["reason"] == "口限禁入"
    assert hit["exceed_metric"] == "COD"
    assert hit["measured"] == 58.0
    assert hit["limit_value"] == 50.0

    # 合规批仍参与对账
    assert "SM-OF-E1-A-001" in codes
    assert "SM-OF-E1-B-001" in codes


def test_reconcile_flow_total_drops_over_limit_volume(client: TestClient):
    data = client.get(f"/api/reconcile/{PERMIT}").json()

    # 仅合规批流量：2800 + 1200 = 4000（超限批 2900 必须剔除）
    assert data["total_flow_m3h"] == 4000.0
    detail_flows = sum(s["flow_m3h"] for s in data["samples"])
    assert detail_flows == 4000.0

    all_rows = client.get("/api/reconcile").json()["items"]
    e01 = next(x for x in all_rows if x["permit_code"] == PERMIT)
    assert e01["total_flow_m3h"] == 4000.0
    assert OVER_CODE not in [s["sample_code"] for s in e01["samples"]]


def test_new_over_limit_rejection_never_reaches_reconcile(client: TestClient):
    """采样拒写与对账剔除联动：被拒批在任何对账口径下都不可见。"""
    outfalls = client.get("/api/outfalls").json()["items"]
    of = next(x for x in outfalls if x["outfall_code"] == "OF-E1-A")
    resp = client.post(
        "/api/samples",
        json={
            "outfall_id": of["id"],
            "permit_ref": PERMIT,
            "sample_code": "SM-LIM-B-REJECT",
            "flow_m3h": 2300,
            "metrics": {"cod": 71.0, "nh3n": 2.0, "tp": 0.1},
        },
    )
    assert resp.status_code == 400

    data = client.get(f"/api/reconcile/{PERMIT}").json()
    all_codes = [s["sample_code"] for s in data["samples"]] + [
        x["sample_code"] for x in data["excluded_samples"]
    ]
    assert "SM-LIM-B-REJECT" not in all_codes
