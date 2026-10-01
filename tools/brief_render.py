#!/usr/bin/env python3
"""简报 / 周报 / 战报 / 月报骨架渲染（零依赖）。

把结构化数据渲染成固定骨架，保证同一员工的输出格式永远可预测。
模型只负责把「数据 → 结构化 JSON」，排版由本脚本保证一致。

v2 修订（2026-09）
------------------
v1 有两处会让产出自相矛盾（实测抓到，见 reports/real-run 相关记录）：
  1. **表头打架**：`TEMPLATES["brief"]` 写「风险与阻塞」，而渲染函数给
     `risks` 字段写「风险 / 问题」；同一份产出里同一类内容出现两个不同表头，
     下游按表头解析会漏项。
  2. **重复空占位**：`sections[1:]` 会先把「风险与阻塞」渲染成空占位，随后
     `risks` 段又渲染一次真实内容 —— 同一标题出现两遍，且空占位留在文末。
v2 起改为**单一 section 规格驱动**：每个 section 只渲染一次，顺序固定；
有数据填数据，无数据才写占位；输入 JSON 的键名保持不变（向后兼容）。

用法:
    python3 brief_render.py --kind weekly --file metrics.json --title "本周复盘" -o out.md
    echo '{"rows":[["访问","1.2万"]]}' | python3 brief_render.py --kind brief

输入 JSON 支持的键（均可缺省）：
    summary / rows / highlights / risks / actions / coord
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# 每个 kind 的 section 规格：顺序即产出顺序，header 唯一。
# type: text=一句话/一段话; table=两列表格; list=无序列表
#
# 覆盖性约束：四种 kind 都必须覆盖 summary / rows / highlights / risks / actions
# 这五个输入键，否则调用方传进来的数据会被**静默丢弃**（v2 首版就漏了 brief 的
# highlights，示例里的「高光 / 亮点」整段消失——见 reports/real-run 记录）。
KIND_SECTIONS: dict[str, list[dict]] = {
    "brief": [
        {"key": "summary", "type": "text", "header": "一句话结论"},
        {"key": "rows", "type": "table", "header": "关键数据"},
        {"key": "highlights", "type": "list", "header": "高光 / 亮点"},
        {"key": "risks", "type": "list", "header": "风险与阻塞"},
        {"key": "actions", "type": "list", "header": "下一步动作"},
    ],
    "weekly": [
        {"key": "summary", "type": "text", "header": "一句话结论"},
        {"key": "highlights", "type": "list", "header": "本周完成"},
        {"key": "rows", "type": "table", "header": "数据表现"},
        {"key": "risks", "type": "list", "header": "问题与根因"},
        {"key": "actions", "type": "list", "header": "下周计划"},
        {"key": "coord", "type": "list", "header": "需要协调"},
    ],
    "battle": [
        {"key": "summary", "type": "text", "header": "战果总览"},
        {"key": "rows", "type": "table", "header": "渠道拆解"},
        {"key": "highlights", "type": "list", "header": "高光内容"},
        {"key": "risks", "type": "list", "header": "失手复盘"},
        {"key": "actions", "type": "list", "header": "下轮调整"},
    ],
    "monthly": [
        {"key": "summary", "type": "text", "header": "月度概览"},
        {"key": "rows", "type": "table", "header": "趋势与拐点"},
        {"key": "highlights", "type": "list", "header": "结构拆解"},
        {"key": "risks", "type": "list", "header": "经验沉淀"},
        {"key": "actions", "type": "list", "header": "下月目标"},
    ],
}

# 所有 kind 都必须覆盖的输入键（防止新增/修改 kind 时把数据丢掉）
REQUIRED_KEYS = ("summary", "rows", "highlights", "risks", "actions")

# 向后兼容：旧调用方可能读 TEMPLATES[kind] 拿章节名列表
TEMPLATES = {k: [s["header"] for s in secs] for k, secs in KIND_SECTIONS.items()}

PLACEHOLDER = "<!-- 待填：由分析者补齐，勿留空提交 -->"


def render(kind: str, data: dict, title: str) -> str:
    sections = KIND_SECTIONS.get(kind) or KIND_SECTIONS["brief"]
    out: list[str] = [f"# {title or kind}", f"\n> 生成日期：{date.today().isoformat()}　格式：{kind}\n"]

    missing: list[str] = []
    for sec in sections:
        key, typ, header = sec["key"], sec["type"], sec["header"]
        val = data.get(key)

        if typ == "text":
            if val:
                out.append(f"**{header}**：{val}\n")
            else:
                out.append(f"**{header}**：{PLACEHOLDER}\n")
                missing.append(header)

        elif typ == "table":
            if val:
                out.append(f"## {header}\n")
                out.append("| 指标 | 数值 |")
                out.append("|---|---|")
                for row in val:
                    k, v = (list(row) + ["", ""])[:2]
                    out.append(f"| {k} | {v} |")
                out.append("")
            else:
                out.append(f"## {header}\n")
                out.append(f"{PLACEHOLDER}\n")
                missing.append(header)

        elif typ == "list":
            out.append(f"## {header}\n")
            if val:
                for item in val:
                    out.append(f"- {item}")
                out.append("")
            else:
                out.append(f"{PLACEHOLDER}\n")
                missing.append(header)

    if missing:
        out.append(f"> 待补章节（{len(missing)} 项）：{'、'.join(missing)}。"
                   f"本节据此判定为「未完成」，不得直接上报。\n")

    return "\n".join(out)


def _selftest() -> int:
    """内嵌回归自测：核心断言是「每个章节只渲染一次」「不留重复空占位」。"""
    checks: list[tuple[str, bool, str]] = []

    def ck(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    def header_forms(kind: str) -> list[str]:
        """章节在正文里的实际标题形式（text 型是加粗行，其余是 ## 标题）。

        注意不能直接数裸表头名：末尾「待补章节」汇总行会合理地复述表头名，
        那不是重复渲染。真正的不变量是「章节标题形式只出现一次」。
        """
        out = []
        for s in KIND_SECTIONS[kind]:
            out.append(f"**{s['header']}**" if s["type"] == "text" else f"## {s['header']}")
        return out

    # 1) 有数据时：章节标题唯一、无重复空占位
    full = {
        "summary": "本周跑通首单",
        "rows": [["曝光", "5.2万"], ["成交", "43"]],
        "highlights": ["首单来自小红书"],
        "risks": ["供应链到货延迟"],
        "actions": ["与供应商确认交期"],
    }
    doc = render("brief", full, "本周复盘")
    for form in header_forms("brief"):
        ck(f"brief 章节标题「{form}」只出现一次", doc.count(form) == 1,
           f"出现 {doc.count(form)} 次")
    ck("brief 有数据时不出现待填占位", PLACEHOLDER not in doc, "仍有占位")
    ck("brief 不出现 v1 的冲突表头「风险 / 问题」", "风险 / 问题" not in doc)
    ck("brief 不出现 v1 的冲突表头「建议动作」", "建议动作" not in doc)
    # 覆盖性：五个输入键都必须被渲染出来，不能静默丢弃
    for key in REQUIRED_KEYS:
        val = full[key]
        probe = val[0][0] if key == "rows" else (val if isinstance(val, str) else val[0])
        ck(f"brief 渲染了输入键 {key}", str(probe) in doc, f"缺失 {probe!r}")

    # 2) 无数据时：章节标题仍只出现一次，且逐条登记待补
    empty = render("brief", {}, "空简报")
    for form in header_forms("brief"):
        ck(f"brief 空数据章节标题「{form}」只出现一次", empty.count(form) == 1,
           f"出现 {empty.count(form)} 次")
    ck("空数据时给出待补章节汇总", "待补章节" in empty)
    ck("空数据时待补项数正确（brief 共 5 节）",
       f"待补章节（{len(KIND_SECTIONS['brief'])} 项）" in empty,
       f"应为 {len(KIND_SECTIONS['brief'])} 项")

    # 3) 每种 kind 都能渲染，且章节标题唯一
    for kind in KIND_SECTIONS:
        d = render(kind, {"summary": "s", "rows": [["a", "b"]],
                          "highlights": ["h"], "risks": ["r"],
                          "actions": ["a"], "coord": ["c"]}, kind)
        bad = [f for f in header_forms(kind) if d.count(f) != 1]
        ck(f"{kind} 渲染成功且章节标题唯一", not bad, f"异常 {bad}")
        # 覆盖性：不允许有 kind 把五个必备键漏掉
        keys = {s["key"] for s in KIND_SECTIONS[kind]}
        missing = [k for k in REQUIRED_KEYS if k not in keys]
        ck(f"{kind} 覆盖全部必备输入键", not missing, f"缺失 {missing}")
        for probe in ("s", "a", "h", "r"):
            ck(f"{kind} 渲染了 {probe!r} 对应章节", probe in d)

    # 4) 有数据的章节不再出现占位（v1 的缺陷：占位与真实内容重复渲染）
    tail = render("brief", {"risks": ["有风险"]}, "t")
    seg = tail.split("## 风险与阻塞")[1].split("##")[0]
    ck("有数据的章节不再出现占位", PLACEHOLDER not in seg)

    # 5) 未知 kind 回退到 brief，不抛异常
    ck("未知 kind 回退 brief", render("unknown-kind", {}, "t").count("**一句话结论**") == 1)

    # 6) rows 畸形行容错
    ck("rows 畸形行不抛异常", "| a |  |" in render("brief", {"rows": [["a"]]}, "t"))

    fails = [(n, d) for n, ok, d in checks if not ok]
    for n, ok, d in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {n}" + (f" —— {d}" if not ok and d else ""))
    print(f"brief_render 自测：{len(checks) - len(fails)}/{len(checks)} 通过")
    return 1 if fails else 0


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()

    ap = argparse.ArgumentParser(description="简报/周报/战报/月报骨架渲染")
    ap.add_argument("--kind", default="brief", choices=sorted(KIND_SECTIONS))
    ap.add_argument("--file", help="结构化数据 JSON；缺省从 stdin")
    ap.add_argument("--title", default="")
    ap.add_argument("-o", "--out", help="输出文件；缺省打印到 stdout")
    args = ap.parse_args()

    raw = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        print(f"错误：输入不是合法 JSON —— {exc}", file=sys.stderr)
        return 2

    text = render(args.kind, data, args.title)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"已生成 {args.out}（{len(text)} 字符）")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
