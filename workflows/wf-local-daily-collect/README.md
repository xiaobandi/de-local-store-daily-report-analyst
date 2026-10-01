# 数据采集

> 营收/客流/团购核销/差评数据归集

工作流 `wf-local-daily-collect`　·　归属 门店经营日报分析师　·　触发 定时（每日 21:30）　·　
复杂度 M（Mock 期手工填报代替）　·　阶段 P0

## 调用链

- `数据对接`（data-ingest-adapter）

## 文档

- [`WORKFLOW.md`](WORKFLOW.md) — 完整编排、闸门、降级与验收标准
- [`tests/cases.yaml`](tests/cases.yaml) — 端到端 / 闸门 / 降级用例

## 一句话试用

```text
帮我跑 门店经营日报分析师 的「数据采集」：<你的输入>
```
