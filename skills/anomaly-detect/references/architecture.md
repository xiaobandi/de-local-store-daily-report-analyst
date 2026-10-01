# 能力与字段速查

技能：`anomaly-detect`（L1 原子技能）

## 元信息

| 字段 | 值 |
|---|---|
| 技能 ID | `skill_anomaly_detect` |
| 目录 | `skills/anomaly-detect` |
| 复杂度 | S |
| 阶段 | P0 |
| 可见性 | platform_shared |
| 版本 | v1.0.0 |
| 许可 | MIT |
| 验证等级 | A（自带脚本 `anomaly_detect.py`，已用真实夹具执行并抓取 stdout/stderr/退出码） |

## 输入契约

- **必填**：指标时间序列数据
- **可选**：业务基线
- **可选**：已知的活动日历

## 脚本清单

| 脚本 | 用途 | 调用方式 |
|---|---|---|
| `scripts/anomaly_detect.py` | 确定性执行逻辑 | `python3 scripts/anomaly_detect.py` |

真实调用：

```bash
python3 scripts/anomaly_detect.py --file examples/input/metrics.json
```

## 质量门

- 所有异常都给了业务解释字段（哪怕是'待查'）
- 区分噪声与真异常

## 已知陷阱

- 异常检测的第一大坑是把促销当成异常——必须先排除已知活动日
- 样本少于 4 期无法判断基线，需告知用户

## 边界

- 只做检测与解释，不做自动执行动作
