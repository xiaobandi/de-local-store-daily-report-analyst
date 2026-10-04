# 周建议 · 速查

| 项 | 内容 |
|---|---|
| slug | `wf-local-daily-weekly-advice` |
| 层级 | L2-workflow |
| 归属 | 门店经营日报分析师（`de-local-store-daily-report-analyst`） |
| 复杂度 / 阶段 | S / P1 |
| 能力族 | — |
| 定义出处 | — |
| 复用情况 | — |

## 调用的 SKILL

| 技能 | slug | 来源 |
|---|---|---|
| 简报生成 | `brief-generator` | agent-skills-core |
| 异常检测 | `anomaly-detect` | 本仓 |

## 字段

| 项 | 内容 |
|---|---|
| 必需输入 | 本工作流的起始材料（见 `SKILL.md`「执行步骤」第 1 步）；用户身份与目标平台/渠道 |
| 可选输入 | 历史产出；账号人设；渠道规则；上一周期的数据 |
| 产出 | 下周一个重点动作 |
| 脚本 | 无 |
