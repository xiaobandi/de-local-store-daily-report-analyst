# 本地绑定 · 数据对接（`data-ingest-adapter`）

> 本能力**不在本仓交付 SKILL.md**。它属于「有意不公共化」的一族，
> 契约在 `agent-skills-core@v1.0.0/specs/data-ingest-adapter.md`，
> 实现留在本仓的连接器绑定层（`connectors/bindings.yaml`）。

## 为什么本仓不存正文

报告明确"数据采集连接器族不公共化为 SKILL"——开源侧只发 Spec + Mock + 权限声明

如果本仓复制一份正文，就等于把"适配 N 个平台"的分支逻辑落成静态文本，
平台接口一变就要改 N 处，且无法测试。**适配留连接器，SKILL 只处理"拿到数据之后做什么"。**

## 本仓必须满足的绑定要求

| 项 | 要求 | 本仓落点 |
|---|---|---|
| 数据源 | 按 `connectors/bindings.yaml` 声明的来源采集 | `connectors/bindings.yaml` |
| 归一化 | 输出统一结构 `{source, collected_at, items[]}` | 连接器适配层 |
| 脱敏 | 命中 PII 先脱敏再入库 | `kb/schema.yaml` 的 `pii_policy` |
| 降级 | 连接器不可用时走 Mock 并标注 | `connectors/bindings.yaml` 的 `mock_fallback` |

## 被哪些工作流使用

- `wf-local-daily-collect`（数据采集）
