# 异常预警

> 客流骤降/差评激增/核销异常 → 即时推送

工作流 `wf-local-daily-anomaly`　·　归属 门店经营日报分析师　·　触发 事件（指标越界）　·　
复杂度 S　·　阶段 P0

## 调用链

- `异常检测`（anomaly-detect）

## 文档

- [`WORKFLOW.md`](WORKFLOW.md) — 完整编排、闸门、降级与验收标准
- [`tests/cases.yaml`](tests/cases.yaml) — 端到端 / 闸门 / 降级用例

## 一句话试用

```text
帮我跑 门店经营日报分析师 的「异常预警」：<你的输入>
```
