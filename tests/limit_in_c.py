"""effluent-09 争用红测（race_limit_create）：两路会话同口抢建超限批。

裁决：
- 同排放口建批必须串行抢同一把口锁 outfall:{id}，后到会话干净失败（409），
  并在 contention_log 只记争用痕（争用失败），不得抛 5xx；
- 口限禁入优先：抢到锁的一路也必须被口限裁决拒收，正式册零增；
- 全程结束口锁释放归零，不留僵尸锁。

为什么这样构造：SQLite 每个连接有独立隐式事务，HTTP 两路同时首抢时，
先到者在请求收尾即释放口锁，后到者可在写锁清空后插入成功，黑盒压不出
完整临界区交叠。因此确定性复现分两层：
1. 单元层直接对 require_lock 做并发首抢，专打 SELECT-then-INSERT 的
   TOCTOU——旧实现双双 INSERT 撞主键冒泡 500，原子实现干净 409；
2. 端到端层模拟一路在途持锁、第二路同口抢建的真实争用场景。
"""
from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

import locks as locks_mod
from app import app
from db import connect, init_db

PERMIT = "DP-2026-E01"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "limit_c.db")
    init_db()
    c = TestClient(app)
    tok = c.post(
        "/api/login", json={"username": "admin", "password": "admin123"}
    ).json()["token"]
    c.headers.update({"Authorization": "Bearer " + tok})
    return c


def _login_client(username: str, password: str) -> TestClient:
    c = TestClient(app)
    tok = c.post(
        "/api/login", json={"username": username, "password": password}
    ).json()["token"]
    c.headers.update({"Authorization": "Bearer " + tok})
    return c


def _formal_count() -> int:
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) c FROM sample_batches").fetchone()["c"]


def _over_limit_payload(code: str, outfall_id: int) -> dict:
    return {
        "outfall_id": outfall_id,
        "permit_ref": PERMIT,
        "sample_code": code,
        "flow_m3h": 2100,
        "metrics": {"cod": 66.0, "nh3n": 3.0, "tp": 0.2},
    }


def test_concurrent_first_acquire_is_atomic(tmp_path, monkeypatch):
    """并发首抢同一把口锁：只许一路成功，败方干净 409 且留争用痕。"""
    monkeypatch.setattr("db.DB_PATH", tmp_path / "limit_c_unit.db")
    init_db()
    lock_key = "outfall:race-first"
    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def acquire(holder: str) -> None:
        with connect() as conn:
            try:
                barrier.wait()
                locks_mod.require_lock(conn, lock_key, holder)
                conn.commit()
            except Exception as exc:  # 500 型 IntegrityError 会在这里现形
                errors.append(exc)
                conn.rollback()

    t1 = threading.Thread(target=acquire, args=("admin",))
    t2 = threading.Thread(target=acquire, args=("writer",))
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)

    assert len(errors) == 1
    loser = errors[0]
    # 旧 SELECT-then-INSERT 实现抛裸 IntegrityError（500）；原子实现抛 409
    assert getattr(loser, "status_code", None) == 409, repr(loser)
    assert "锁被占用" in str(loser)

    with connect() as conn:
        holders = [r["holder"] for r in conn.execute(
            "SELECT holder FROM effluent_locks WHERE lock_key=?", (lock_key,)
        ).fetchall()]
        contention = conn.execute(
            "SELECT * FROM contention_log WHERE lock_key=?", (lock_key,)
        ).fetchall()
    assert holders == ["admin"] or holders == ["writer"]
    assert len(contention) == 1
    assert contention[0]["action"] == "争用失败"


def test_race_limit_create_two_sessions_same_outfall(client: TestClient):
    """一路在途持锁，第二路同口抢建超限批：409 争用失败且零批。"""
    outfall = next(
        x
        for x in client.get("/api/outfalls").json()["items"]
        if x["outfall_code"] == "OF-E1-A"
    )
    lock_key = f"outfall:{outfall['id']}"
    base_formal = _formal_count()
    base_contention = len(client.get("/api/locks").json()["contention"])

    # 会话 A 在途持有口锁（模拟一路建批尚未走完临界区）
    with connect() as held:
        locks_mod.require_lock(held, lock_key, "admin-A-inflight")
        held.commit()

        writer = _login_client("writer", "writer123")
        resp = writer.post(
            "/api/samples",
            json=_over_limit_payload("SM-LIM-C-LOSER", outfall["id"]),
        )
        # 后到者干净 409，而不是 5xx，也不是假绿 200
        assert resp.status_code == 409
        assert "锁" in resp.json()["detail"]

    # 正式册零增：败方一个批都没建出
    assert _formal_count() == base_formal
    codes = [s["sample_code"] for s in client.get("/api/samples").json()["items"]]
    assert "SM-LIM-C-LOSER" not in codes

    contention = client.get("/api/locks").json()["contention"]
    assert len(contention) == base_contention + 1
    row = contention[0]
    assert row["action"] == "争用失败"
    assert row["lock_key"] == lock_key
    assert row["actor"] == "writer"


def test_lock_winner_still_rejected_by_outfall_limit(client: TestClient):
    """抢到口锁的一路建超限批，仍被口限禁入 400 拒收，正式册零增、锁释放。"""
    outfall = next(
        x
        for x in client.get("/api/outfalls").json()["items"]
        if x["outfall_code"] == "OF-E1-A"
    )
    base_formal = _formal_count()

    resp = client.post(
        "/api/samples",
        json=_over_limit_payload("SM-LIM-C-WINNER", outfall["id"]),
    )
    assert resp.status_code == 400
    assert "口限" in resp.json()["detail"]

    assert _formal_count() == base_formal
    # 拒收后 finally 释放口锁，无僵尸持有人
    assert client.get("/api/locks").json()["locks"] == []
    holds = client.get("/api/exceeds").json()["items"]
    assert all(h["sample_code"] != "SM-LIM-C-WINNER" for h in holds)
