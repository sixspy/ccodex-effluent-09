"""排放批争用锁。"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user, require_writer
from db import connect, now_iso, write_audit

router = APIRouter(tags=["locks"])


def _log_contention(conn, lock_key: str, holder: str, detail: str) -> None:
    conn.execute(
        """INSERT INTO contention_log(lock_key,actor,action,detail,created_at)
           VALUES (?,?,?,?,?)""",
        (lock_key, holder, "争用失败", detail, now_iso()),
    )


def require_lock(conn, lock_key: str, holder: str) -> None:
    """原子抢锁：同口两路并发首抢只有一路能 INSERT 成功。

    旧实现先 SELECT 再 INSERT 存在 TOCTOU，并发首抢会让两路都判定无锁、
    第二路撞 PRIMARY KEY 抛 500。改为单条原子 INSERT，占用冲突与
    SQLITE_BUSY 一律按争用失败处理（409 + contention_log 争用痕）。
    """
    try:
        conn.execute(
            "INSERT INTO effluent_locks(lock_key,holder,acquired_at) VALUES (?,?,?)",
            (lock_key, holder, now_iso()),
        )
        return
    except sqlite3.IntegrityError:
        row = conn.execute(
            "SELECT holder FROM effluent_locks WHERE lock_key=?", (lock_key,)
        ).fetchone()
        owner = row["holder"] if row else "未知持有人"
    except sqlite3.OperationalError as exc:  # 写锁排队超时同样按争用裁决
        owner = f"写锁忙({exc})"
    _log_contention(conn, lock_key, holder, f"持有人={owner}")
    # 争用痕必须先落库再抛错，否则连接回滚会把痕迹一并抹掉
    conn.commit()
    raise HTTPException(409, f"锁被占用：{lock_key} 持有人 {owner}")


def release(conn, lock_key: str, holder: str) -> None:
    conn.execute(
        "DELETE FROM effluent_locks WHERE lock_key=? AND holder=?",
        (lock_key, holder),
    )


@router.get("/api/locks")
def list_locks(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        locks = [dict(r) for r in conn.execute("SELECT * FROM effluent_locks").fetchall()]
        logs = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM contention_log ORDER BY id DESC LIMIT 50"
            ).fetchall()
        ]
        return {"locks": locks, "contention": logs}


@router.post("/api/locks/acquire")
def acquire(lock_key: str, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        require_lock(conn, lock_key, user)
        write_audit(conn, user, "lock_acquire", lock_key, {})
        conn.commit()
        return {"ok": True, "lock_key": lock_key, "holder": user}


@router.post("/api/locks/release")
def release_api(lock_key: str, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        release(conn, lock_key, user)
        write_audit(conn, user, "lock_release", lock_key, {})
        conn.commit()
        return {"ok": True}
