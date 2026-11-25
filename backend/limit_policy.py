"""口限禁入裁决（effluent-09）——全仓唯一口限口径出处。

当班封死的裁决口径：
1. 采样入库、超标挂起、对账剔除、页面红灯告警只能使用排放口本口限值
   （outfalls.cod_limit / nh3n_limit / tp_limit），严禁与许可帽
   （discharge_permits.*_cap）混用；许可帽只用于对账的账实匹配。
2. 任一指标实测值严格大于本口限值即判超口限（贴线 == 限值为合规）。
3. 超口限批不得进入正式采样册：采样服务原子拒收（正式行零增、挂起行零增），
   对账服务剔除其流量与明细，不允许折中（影子批/先入后驳均禁止）。
4. 任何偏离本口径的改动按偏航处理：记“口限禁入偏航”并拒写。
"""
from __future__ import annotations

from metrics_math import METRIC_KEYS, METRIC_LABELS, as_float_map, first_exceed

# 审计/前端统一使用的裁决标记，禁止各处自造字符串
LIMIT_REJECT_ACTION = "sample_limit_reject"
LIMIT_REJECT_REASON = "口限禁入"
LIMIT_DEVIATION_REASON = "口限禁入偏航"


def outfall_limits(outfall_row) -> dict[str, float]:
    """从排放口行取本口限值——口限口径的唯一取数方式。"""
    return {
        "cod": float(outfall_row["cod_limit"]),
        "nh3n": float(outfall_row["nh3n_limit"]),
        "tp": float(outfall_row["tp_limit"]),
    }


def judge_outfall_limit(metrics: dict, limits: dict) -> dict:
    """返回口限裁决结果。exceeded=True 即超口限，必须禁入正式册。"""
    label, measured, limit_value = first_exceed(metrics, limits)
    return {
        "exceeded": label is not None,
        "exceed_metric": label,
        "measured": float(measured),
        "limit_value": float(limit_value),
    }


def reject_detail(verdict: dict, outfall_code: str) -> str:
    return (
        f"{LIMIT_REJECT_REASON}：{outfall_code} {verdict['exceed_metric']} "
        f"实测 {verdict['measured']} 超口限 {verdict['limit_value']}，正式批原子拒收"
    )


def row_is_over_outfall_limit(metrics: dict, limits: dict) -> bool:
    """对账/页面批量复用时的布尔裁决，与 judge_outfall_limit 同源。"""
    return judge_outfall_limit(as_float_map(metrics), limits)["exceeded"]


def alarm_for_outfall(latest_metrics: dict | None, limits: dict) -> dict:
    """页面红灯/告警条同源裁决：最新批超本口限即红灯。"""
    if not latest_metrics:
        return {"limit_alarm": False, "latest_cod": None, "alarm_metric": None}
    metrics = as_float_map(latest_metrics)
    verdict = judge_outfall_limit(metrics, limits)
    return {
        "limit_alarm": verdict["exceeded"],
        "latest_cod": metrics["cod"],
        "alarm_metric": verdict["exceed_metric"],
    }


__all__ = [
    "METRIC_KEYS",
    "METRIC_LABELS",
    "LIMIT_REJECT_ACTION",
    "LIMIT_REJECT_REASON",
    "LIMIT_DEVIATION_REASON",
    "outfall_limits",
    "judge_outfall_limit",
    "reject_detail",
    "row_is_over_outfall_limit",
    "alarm_for_outfall",
]
