"""排放许可与采样对账证明。"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user
from limit_policy import (
    LIMIT_REJECT_REASON,
    judge_outfall_limit,
    outfall_limits,
)
from validators import validate_permit_match

router = APIRouter(tags=["reconcile"])


@router.get("/api/reconcile")
def reconcile_all(authorization: AuthHeader = None):
    require_user(authorization)
    from db import connect

    with connect() as conn:
        rows = conn.execute(
            "SELECT permit_code FROM discharge_permits ORDER BY permit_code"
        ).fetchall()
        return {"items": [_reconcile_permit(conn, r["permit_code"]) for r in rows]}


@router.get("/api/reconcile/{permit_code}")
def reconcile_one(permit_code: str, authorization: AuthHeader = None):
    require_user(authorization)
    from db import connect

    with connect() as conn:
        if not conn.execute(
            "SELECT id FROM discharge_permits WHERE permit_code=?", (permit_code,)
        ).fetchone():
            raise HTTPException(404, "许可不存在")
        return _reconcile_permit(conn, permit_code)


def _reconcile_permit(conn, permit_code: str) -> dict:
    permit = conn.execute(
        "SELECT * FROM discharge_permits WHERE permit_code=?", (permit_code,)
    ).fetchone()
    # 联排放口取本口限值：对账剔除与采样口限裁决必须同源，
    # 不得用许可帽（permit.*_cap）替代口限比较。
    rows = conn.execute(
        """SELECT s.sample_code, s.flow_m3h, s.metrics, s.status, s.generation,
                  s.outfall_id, o.outfall_code, o.cod_limit, o.nh3n_limit, o.tp_limit
           FROM sample_batches s
           JOIN outfalls o ON o.id=s.outfall_id
           WHERE s.permit_ref=? AND s.status NOT IN ('作废')
           ORDER BY s.id""",
        (permit_code,),
    ).fetchall()
    if not rows:
        return {
            "permit_code": permit_code,
            "balanced": False,
            "reason": "无采样批次",
            "samples": [],
            "excluded_samples": [],
            "total_flow_m3h": 0.0,
        }
    caps = {
        "cod": permit["cod_cap"],
        "nh3n": permit["nh3n_cap"],
        "tp": permit["tp_cap"],
    }
    details = []
    excluded = []
    total_flow = 0.0
    all_ok = True
    for s in rows:
        metrics = json.loads(s["metrics"] or "{}")
        verdict = judge_outfall_limit(metrics, outfall_limits(s))
        if verdict["exceeded"]:
            # 超口限批剔除：不进对账明细、不累计流量，只留口限禁入痕
            excluded.append(
                {
                    "sample_code": s["sample_code"],
                    "outfall_code": s["outfall_code"],
                    "reason": LIMIT_REJECT_REASON,
                    "exceed_metric": verdict["exceed_metric"],
                    "measured": verdict["measured"],
                    "limit_value": verdict["limit_value"],
                    "flow_m3h": s["flow_m3h"],
                }
            )
            continue
        ok = validate_permit_match(
            caps, metrics, float(s["flow_m3h"]), float(permit["quota_m3d"])
        )
        if not ok:
            all_ok = False
        total_flow += float(s["flow_m3h"])
        details.append(
            {
                "sample_code": s["sample_code"],
                "status": s["status"],
                "generation": s["generation"],
                "metrics": metrics,
                "flow_m3h": s["flow_m3h"],
                "matched": ok,
            }
        )
    seal_rows = conn.execute(
        """SELECT d.seal_ref, d.sample_generation, s.sample_code
           FROM discharge_seals d JOIN sample_batches s ON s.id=d.sample_id
           WHERE s.permit_ref=?""",
        (permit_code,),
    ).fetchall()
    return {
        "permit_code": permit_code,
        "quota_m3d": permit["quota_m3d"],
        "caps": caps,
        "balanced": all_ok,
        "proof_ready": all_ok and len(seal_rows) >= 1,
        "seal_count": len(seal_rows),
        "samples": details,
        "excluded_samples": excluded,
        "excluded_count": len(excluded),
        "total_flow_m3h": total_flow,
        "seals": [dict(x) for x in seal_rows],
    }


@router.get("/api/proof/sample/{sample_code}")
def proof_sample(sample_code: str, authorization: AuthHeader = None):
    require_user(authorization)
    from db import connect

    with connect() as conn:
        sample = conn.execute(
            "SELECT * FROM sample_batches WHERE sample_code=?", (sample_code,)
        ).fetchone()
        if not sample:
            raise HTTPException(404, "采样不存在")
        holds = conn.execute(
            "SELECT * FROM exceed_holds WHERE sample_id=?", (sample["id"],)
        ).fetchall()
        releases = conn.execute(
            "SELECT * FROM discharge_releases WHERE sample_id=?", (sample["id"],)
        ).fetchall()
        seals = conn.execute(
            "SELECT * FROM discharge_seals WHERE sample_id=?", (sample["id"],)
        ).fetchall()
        open_holds = [h for h in holds if h["status"] == "开放"]
        closed = [h for h in holds if h["status"] == "已关闭"]
        return {
            "sample_code": sample_code,
            "status": sample["status"],
            "generation": sample["generation"],
            "released": any(r["status"] == "已准排" for r in releases),
            "sealed": any(s["status"] == "已封批" for s in seals),
            "exceed_closed": len(open_holds) == 0 and (len(closed) > 0 or sample["status"] != "旁路挂起"),
            "holds": [dict(h) for h in holds],
            "releases": [dict(r) for r in releases],
            "seals": [dict(s) for s in seals],
        }
