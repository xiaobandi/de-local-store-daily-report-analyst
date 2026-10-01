# 日报生成

> 数据 → 一句话结论+三个关键数+一个行动建议

工作流 `wf-local-daily-report`　·　归属 门店经营日报分析师　·　触发 定时（每日 22:00）　·　
复杂度 S　·　阶段 P0

## 调用链

- `简报生成`（brief-generator）

## 文档

- [`WORKFLOW.md`](WORKFLOW.md) — 完整编排、闸门、降级与验收标准
- [`tests/cases.yaml`](tests/cases.yaml) — 端到端 / 闸门 / 降级用例

## 一句话试用

```text
帮我跑 门店经营日报分析师 的「日报生成」：<你的输入>
```
