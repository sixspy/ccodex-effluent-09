"""effluent-09 红测甲（limit_in_a）：COD 超排放口口限必须原子拒收，正式册零增。

口径裁决（题面甲路径，当班封死）：
- 采样入库只能用排放口本口限值（outfalls.cod_limit 等）裁定，不得与许可帽混用；
- 任一指标超口限 => 正式采样行零增、超标挂起行零增，整笔原子拒收；
- 拒收裁决写入审计说明（口限禁入），不允许只亮红灯动画；
- 合规批与贴线批（测值==限值）仍正常入库。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import app
from db import init_db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "limit_a.db")
    init_db()
    c = TestClient(app)
    tok = c.post(
        "/api/login", json={"username": "admin", "password": "admin123"}
    ).json()["token"]
    c.headers.update({"Authorization": "Bearer " + tok})
    return c


def _of_e1_a(client: TestClient) -> dict:
    rows = client.get("/api/outfalls").json()["items"]
    return next(x for x in rows if x["outfall_code"] == "OF-E1-A")


def test_over_limit_cod_atomically_rejected_zero_formal_row(client: TestClient):
    outfall = _of_e1_a(client)
    assert outfall["cod_limit"] == 50

    before_samples = client.get("/api/samples").json()["items"]
    before_holds = client.get("/api/exceeds").json()["items"]

    resp = client.post(
        "/api/samples",
        json={
            "outfall_id": outfall["id"],
            "permit_ref": "DP-2026-E01",
            "sample_code": "SM-LIM-A-001",
            "flow_m3h": 2000,
            "metrics": {"cod": 62.0, "nh3n": 3.0, "tp": 0.2},
        },
    )
    # 甲路径：超口限 => 业务拒收，而不是建出正式批
    assert resp.status_code == 400
    assert "口限" in resp.json()["detail"]

    after_samples = client.get("/api/samples").json()["items"]
    after_holds = client.get("/api/exceeds").json()["items"]

    # 正式采样册零增
    assert len(after_samples) == len(before_samples)
    assert all(s["sample_code"] != "SM-LIM-A-001" for s in after_samples)
    # 原子拒收：不得留影子超标挂起行
    assert len(after_holds) == len(before_holds)
    assert all(h["sample_code"] != "SM-LIM-A-001" for h in after_holds)

    # 裁决说明落审计，口限禁入当班封死
    trail = client.get("/api/audit").json()["items"]
    marks = [
        x
        for x in trail
        if x["action"] == "sample_limit_reject" and "口限禁入" in (x["payload"] or "")
    ]
    assert marks, "超口限拒收必须写入口限禁入审计裁决"
    assert any("OF-E1-A" in (x["target"] or "") for x in marks)


def test_boundary_value_equal_to_limit_still_admitted(client: TestClient):
    outfall = _of_e1_a(client)
    resp = client.post(
        "/api/samples",
        json={
            "outfall_id": outfall["id"],
            "permit_ref": "DP-2026-E01",
            "sample_code": "SM-LIM-A-EDGE",
            "flow_m3h": 1800,
            "metrics": {"cod": 50.0, "nh3n": 5.0, "tp": 0.5},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["exceed"] is False
    assert resp.json()["status"] == "已裁定"


def test_compliant_batch_still_enters_formal_register(client: TestClient):
    outfall = _of_e1_a(client)
    resp = client.post(
        "/api/samples",
        json={
            "outfall_id": outfall["id"],
            "permit_ref": "DP-2026-E01",
            "sample_code": "SM-LIM-A-OK",
            "flow_m3h": 1900,
            "metrics": {"cod": 42.0, "nh3n": 3.2, "tp": 0.28},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "已裁定"
    codes = [s["sample_code"] for s in client.get("/api/samples").json()["items"]]
    assert "SM-LIM-A-OK" in codes


def test_outfall_and_plant_alarm_share_same_limit_source(client: TestClient):
    """排放口页红灯与处理厂页告警条必须同源于口限比较，限值字段一致。"""
    outfalls = client.get("/api/outfalls").json()["items"]
    red = next(x for x in outfalls if x["outfall_code"] == "OF-E1-A")
    green = next(x for x in outfalls if x["outfall_code"] == "OF-N3-A")

    # 预置夹具：OF-E1-A 最新批 COD58 > 口限50；OF-N3-A 最新批 COD24 <= 口限30
    assert red["limit_alarm"] is True
    assert red["latest_cod"] == 58.0
    assert red["cod_limit"] == 50.0
    assert green["limit_alarm"] is False

    plant_id = red["plant_id"]
    detail = client.get(f"/api/plants/{plant_id}").json()
    plant_row = next(o for o in detail["outfalls"] if o["outfall_code"] == "OF-E1-A")
    # 处理厂页告警条与排放口页限值字段、告警裁决完全同源
    assert plant_row["cod_limit"] == red["cod_limit"]
    assert plant_row["limit_alarm"] == red["limit_alarm"]
    assert plant_row["latest_cod"] == red["latest_cod"]
