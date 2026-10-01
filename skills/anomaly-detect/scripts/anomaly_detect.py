#!/usr/bin/env python3
"""经营指标异常检测（零依赖）。

对一组时间序列做「偏离基线 / 环比突变 / 连续趋势」三类检测，
输出可解释的异常点与预警等级，作为日报、周报、运营中台三处共用底座。

v2 修订（2026-09）
------------------
v1 的 `detect()` **只评估序列最后一个点**（`base = values[:-1]`，`last = values[-1]`）。
实测中把整整 12 期序列喂进去，中段埋的脏数据（第 8 期）完全抓不到，
输出「命中 0 条 / 全部正常」——比漏报更危险的是给出「正常」的错觉
（见 reports/real-run/de-local-store-daily-report-analyst）。

v2 起改为**全序列滑动窗口 + 双门槛判定**，三次踩坑过程一并记录：
  坑 1（v1）：只判末点，中段脏数据完全看不见。
  坑 2：改成逐点均值+标准差后，一条平稳上涨的正常序列被误报 3 个 P0/P1
        —— 短窗口下「趋势」本身就会让最新点显得巨大。
  坑 3：改用中位数+MAD 仍不从根本解决，因为 4 点基线配上涨趋势时
        MAD 也极小，偏离倍数照样虚高。
  最终口径：**幅度门槛 + 稳健 z 门槛必须同时满足**才算「偏离基线」。
    - 幅度门槛：相对前 window 期中位数的百分比偏离 ≥ `--pct`（默认 20%）
      —— 直接对齐业务语义（曝光骤降/差评激增），缓慢增长永不触发；
    - 统计门槛：稳健 z（中位数 + MAD）≥ `--k`（默认 2.0）
      —— 避免在本身波动很大的序列上因小波动误报。
  实测复查：干净序列（剔除 W34）命中 0 条；含 W34 脏数据时精确命中第 8 期。

其余：
  - 环比突变逐点检查；若**前一期本身已被判为异常**，该环比明确标注
    「不可直接解读」（否则脏数据回弹会产出 +1690222% 这类无意义数值）；
  - 连续趋势按「极大单调段」报告（每段只报一次，且要求连续 ≥ 4 期）；
  - 支持带期标签的输入，产出里直接写期名（如「W34」）而非下标。

用法:
    python3 anomaly_detect.py --file metrics.json --metric 营业额
    echo '{"营业额": [1200,1250,1180,3000]}' | python3 anomaly_detect.py --json
    python3 anomaly_detect.py --file metrics.json --window 6 --k 2.5 --pct 15

输入 JSON 支持三种形态：
    {"指标名": [数值, ...]}
    [{"metric": "...", "values": [...]}, ...]
    {"指标名": {"values": [...], "periods": ["W27", "W28", ...]}}
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

MIN_WINDOW = 3        # 基线至少要 3 期才谈得上「中位数与离散度」（并保证 4 点序列可检）
RUN_MIN = 4           # 连续趋势至少 4 期才报
MOM_THRESHOLD = 30.0  # 环比突变阈值（%）
PCT_THRESHOLD = 20.0  # 相对基线的幅度门槛（%）
# MAD → 标准差的一致性系数（正态分布下 σ ≈ 1.4826 × MAD）
MAD_TO_SIGMA = 1.4826


def _label(periods: list[str] | None, i: int) -> str:
    if periods and i < len(periods):
        return f"第 {i + 1} 期（{periods[i]}）"
    return f"第 {i + 1} 期"


def _robust_sigma(base: list[float]) -> tuple[float, float]:
    """返回 (中位数, 稳健标准差)。全部相同时退化为 0。"""
    med = st.median(base)
    mad = st.median([abs(x - med) for x in base])
    return med, mad * MAD_TO_SIGMA


def detect(values: list[float], periods: list[str] | None = None,
           k: float = 2.0, window: int = 6, pct: float = PCT_THRESHOLD) -> list[dict]:
    """全序列扫描。返回按位置排序的异常列表。

    「偏离基线」= 幅度门槛（|偏离%| >= pct）**且** 统计门槛（|稳健 z| >= k）。
    """
    n = len(values)
    if n < MIN_WINDOW + 1:
        return []
    out: list[dict] = []

    for i in range(MIN_WINDOW, n):
        lo = max(0, i - window)
        base = values[lo:i]
        if len(base) < MIN_WINDOW:
            continue
        med, sigma = _robust_sigma(base)

        if med:
            dev_pct = (values[i] - med) / abs(med) * 100
        else:
            dev_pct = 0.0 if values[i] == 0 else float("inf")

        # 幅度门槛不达标 → 直接跳过（缓慢增长/正常波动永不触发）
        if abs(dev_pct) < pct:
            continue

        if sigma > 0:
            z: float | None = (values[i] - med) / sigma
        else:
            # 基线完全一致：凡有幅度偏离即视为远超离散度
            z = None if values[i] != med else 0.0

        if z is not None and abs(z) < k:
            continue

        severe = abs(dev_pct) >= 50 or (z is not None and abs(z) >= 3)
        ztxt = "远超基线离散度" if z is None else f"{abs(round(z, 2))} 倍稳健标准差"
        out.append({
            "index": i,
            "period": _label(periods, i),
            "type": "偏离基线",
            "level": "P0" if severe else "P1",
            "value": values[i],
            "baseline": round(med, 2),
            "dev_pct": round(dev_pct, 1),
            "z": None if z is None else round(z, 2),
            "note": f"{_label(periods, i)} 值 {values[i]} 相对前 {len(base)} 期"
                    f"基线中位数 {round(med, 2)} 偏离 {round(dev_pct, 1)}%，{ztxt}",
        })

    anomalous = {a["index"] for a in out}

    # 2) 逐点「环比突变」；前一期本身异常时明确标注不可解读
    for i in range(1, n):
        prev = values[i - 1]
        if not prev:
            continue
        mom = (values[i] - prev) / abs(prev) * 100
        if abs(mom) >= MOM_THRESHOLD:
            artifact = (i - 1) in anomalous
            out.append({
                "index": i,
                "period": _label(periods, i),
                "type": "环比突变",
                "level": "P2" if artifact else ("P0" if abs(mom) >= 50 else "P1"),
                "value": values[i],
                "mom_pct": round(mom, 1),
                "artifact": artifact,
                "note": (f"{_label(periods, i)} 环比 {'涨' if mom > 0 else '跌'} {abs(round(mom, 1))}%"
                         + ("（前一期已判为异常点，该环比不可直接解读，须先核对前一期数据）"
                            if artifact else "")),
            })

    # 3) 连续趋势：按极大单调段报告，每段一次，且要求连续 >= RUN_MIN 期
    run_start = 0
    run_dir = 0  # 1 升 / -1 降 / 0 平
    for i in range(1, n):
        d = 1 if values[i] > values[i - 1] else (-1 if values[i] < values[i - 1] else 0)
        if d == run_dir and d != 0:
            continue
        if run_dir != 0 and i - run_start >= RUN_MIN:
            end = i - 1
            out.append({
                "index": end,
                "period": _label(periods, end),
                "type": "连续趋势",
                "level": "P2",
                "value": values[end],
                "note": f"{_label(periods, run_start)} 起连续 {i - run_start} 期"
                        f"{'上升' if run_dir > 0 else '下降'}，关注是否形成拐点",
            })
        run_start = i - 1
        run_dir = d
    if run_dir != 0 and n - run_start >= RUN_MIN:
        end = n - 1
        out.append({
            "index": end,
            "period": _label(periods, end),
            "type": "连续趋势",
            "level": "P2",
            "value": values[end],
            "note": f"{_label(periods, run_start)} 起连续 {n - run_start} 期"
                    f"{'上升' if run_dir > 0 else '下降'}，关注是否形成拐点",
        })

    out.sort(key=lambda a: (a["index"], a["type"]))
    return out


def _normalize(data) -> dict[str, dict]:
    """统一成 {指标名: {"values": [...], "periods": [...]|None}}。"""
    series: dict[str, dict] = {}
    if isinstance(data, list):
        for d in data:
            series[d["metric"]] = {"values": d["values"], "periods": d.get("periods")}
    else:
        for name, v in data.items():
            if isinstance(v, dict):
                series[name] = {"values": v.get("values", []), "periods": v.get("periods")}
            else:
                series[name] = {"values": v, "periods": None}
    return series


def _selftest() -> int:
    """内嵌回归自测：核心断言是「中段异常必须抓到」「正常波动不得误报」。"""
    checks: list[tuple[str, bool, str]] = []

    def ck(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    PERIODS = [f"W{i}" for i in range(27, 39)]
    DIRTY = [42100, 44800, 46200, 45900, 48600, 51200, 49800, 3.1, 52400, 54100, 53600, 55200]
    CLEAN = [42100, 44800, 46200, 45900, 48600, 51200, 49800, 52400, 54100, 53600, 55200]

    # 1) 中段（第 8 期）脏数据必须命中 —— 这是 v1 最严重的漏报
    hits = detect(DIRTY, PERIODS)
    idx = {a["index"] for a in hits}
    ck("含 W34 时命中第 8 期（index=7）", 7 in idx, f"命中 {sorted(idx)}")
    ck("第 8 期判为 P0",
       any(a["index"] == 7 and a["level"] == "P0" for a in hits))
    ck("产出里写明期名 W34",
       any(a["index"] == 7 and "W34" in a["period"] for a in hits))

    # 2) 干净序列不得误报（v1 改滑窗后的中间版本会误报 W31/W32）
    clean_hits = detect(CLEAN, PERIODS[:11])
    ck("干净序列 0 命中", not clean_hits, f"误报 {[(a['index'], a['type']) for a in clean_hits]}")

    # 3) 末点异常（v1 唯一能抓的场景，不得退化）
    tail = detect([1200, 1250, 1180, 3000])
    ck("4 点序列末点异常可检", any(a["index"] == 3 for a in tail),
       f"命中 {[a['index'] for a in tail]}")

    # 4) 脏数据回弹的环比必须标注「不可直接解读」
    rebound = [a for a in hits if a["index"] == 8 and a["type"] == "环比突变"]
    ck("W35 回弹环比被标注 artifact",
       bool(rebound) and all(a.get("artifact") for a in rebound))
    ck("artifact 环比降级为 P2", all(a["level"] == "P2" for a in rebound))
    ck("artifact 环比提示核对前一期",
       all("不可直接解读" in a["note"] for a in rebound))

    # 5) 缓慢单调上涨不得触发「偏离基线」（幅度门槛的作用）
    slow = [100, 105, 110, 115, 120, 126, 132, 139, 146, 153, 161]
    slow_hits = [a for a in detect(slow) if a["type"] == "偏离基线"]
    ck("缓慢上涨不触发偏离基线", not slow_hits,
       f"误报 {[(a['index'], a.get('dev_pct')) for a in slow_hits]}")

    # 6) 短序列直接返回空，不抛异常
    ck("3 点序列返回空", detect([1, 2, 3]) == [])
    ck("空序列返回空", detect([]) == [])

    # 7) 三种输入形态都能解析
    ck("dict[str, list] 形态", _normalize({"a": [1, 2, 3]})["a"]["values"] == [1, 2, 3])
    ck("list[dict] 形态",
       _normalize([{"metric": "a", "values": [1, 2]}])["a"]["values"] == [1, 2])
    ck("dict[str, dict] 形态",
       _normalize({"a": {"values": [1], "periods": ["W1"]}})["a"]["periods"] == ["W1"])

    fails = [(n, d) for n, ok, d in checks if not ok]
    for n, ok, d in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {n}" + (f" —— {d}" if not ok and d else ""))
    print(f"anomaly_detect 自测：{len(checks) - len(fails)}/{len(checks)} 通过")
    return 1 if fails else 0


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()

    ap = argparse.ArgumentParser(description="经营指标异常检测（全序列）")
    ap.add_argument("--file", help="指标 JSON；缺省 stdin")
    ap.add_argument("--metric", help="只检某个指标")
    ap.add_argument("--k", type=float, default=2.0, help="稳健 z 门槛（MAD 倍数）")
    ap.add_argument("--window", type=int, default=6, help="基线回看期数（滑动窗口大小）")
    ap.add_argument("--pct", type=float, default=PCT_THRESHOLD,
                    help="相对基线的幅度门槛（%%），默认 %(default)s")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    raw = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        print(f"错误：输入不是合法 JSON —— {exc}", file=sys.stderr)
        return 2

    series = _normalize(data)
    if args.metric:
        series = {k: v for k, v in series.items() if k == args.metric}
        if not series:
            print(f"错误：未找到指标 {args.metric}", file=sys.stderr)
            return 2

    report: dict[str, list[dict]] = {}
    for name, spec in series.items():
        report[name] = detect([float(v) for v in spec["values"]],
                              spec.get("periods"), args.k, args.window, args.pct)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        total = sum(len(v) for v in report.values())
        points = sum(len({a["index"] for a in v}) for v in report.values())
        print(f"异常检测（全序列扫描；基线=前 {args.window} 期中位数+MAD，"
              f"双门槛：幅度≥{args.pct}% 且 z≥{args.k}）："
              f"{len(report)} 个指标，命中 {total} 条，涉及 {points} 个时间点")
        for name, items in report.items():
            print(f"\n【{name}】")
            if not items:
                print("  正常，无异常")
            for it in items:
                print(f"  [{it['level']}] {it['type']} — {it['note']}")
    return 1 if sum(len(v) for v in report.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
