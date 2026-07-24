# RepairScope-Bench

这是一个评测 Agent 在“前序操作已经产生真实影响、后续操作失败”之后，能否选择合理恢复范围的可执行原型。

例如，Agent 已经订好机票和酒店，随后租车失败。它既不能机械地取消所有订单，也不能默认只重试租车：预算、退款规则、时间兼容性和替代资源可能要求它保留、修改或替换不同的已有承诺。

当前版本是 **v0.2 研究原型**，包含 4 个反事实家族、16 个任务。所有模型从同一个失败状态开始，但仍须实际调用查询、取消、预订、修改、完成或报告不可行等工具。

## 当前评测什么

> 在已有有效承诺的统一失败状态下，Agent 能否完成目标，同时避免不必要地破坏已有承诺和制造可客观核算的额外损失？

四个任务家族分别来自旅行套餐、目的地变更、行程缩短和办公设备兼容性。每个家族只改变少量事实，使最优恢复范围在“保留、修改、替换、不可行”之间发生变化。

本版本不评测失败前的规划与执行质量；它是一条条件式恢复赛道。以后可以在其上增加端到端赛道。

## “额外损失”怎样客观计算

评测器不把不同经济概念用人工权重混成一个分数，而是分别记三本账：

1. `lifecycle_cost`：任务全生命周期中，服务商最终保留的净现金；
2. `recovery_loss`：恢复动作造成的不可回收损失，包括取消旧承诺后无法退回的金额、恢复期间买入又取消且无法退款的金额，以及原地修改产生的正向净现金支出；
3. `financial_regret`：Agent 的全生命周期成本与同一失败状态下最低可行成本之差。

主指标 `extra_loss` 等于 Agent 的 `recovery_loss` 减去可行方案中的最小值。它来自确定的价格、退款和修改现金流，不需要人工打分。

满足硬约束后，当前任务按下列字典序选择 gold：

```text
(recovery_loss,
 mutated_prior_commitments,
 lifecycle_cost,
 state_changing_actions)
```

这表示：先避免不可回收的恢复损失；损失相同时少动已有承诺；范围相同时选择成本更低的方案；最后减少有副作用的操作数。这里没有可调权重。公开任务 JSON 不含 gold；评测专用结果单独存放在 `data/gold/pilot.json`，模型提示由字段白名单生成，不会看到答案。

## 主要指标

- `Goal Pass@1`：最终硬约束和终止方式是否正确；
- `Optimal Repair Rate`：是否达到完整字典序最优；
- `Extra Loss`：相对最小恢复损失多损失了多少；
- `Financial Regret`：相对最低可行全生命周期成本多花了多少；
- `Scope Distance`：对旧承诺的保留、修改、替换、取消结果与最近 gold 的距离；
- `Over-repair / Under-repair`：是否多改了应保留的承诺，或漏改了必须处理的承诺；
- `Correct Infeasibility`：确实无解时，能否在不先破坏失败状态的前提下报告不可行。

## 安装与校验

```powershell
python -m pip install -e .
python scripts/build_pilot.py
repairscope validate data/pilot
python -m unittest discover -s tests -v
repairscope run-baselines data/pilot
```

当前回归结果为：oracle 16/16 成功且最优；其他规则基线故意不能覆盖全部反事实。这些数字是实现校验，不是语言模型实验结果。

## 直接接入四类模型

```powershell
# GPT：OpenAI Responses API
$env:OPENAI_API_KEY="..."
repairscope run-suite data/pilot --provider openai --model gpt-5.6-sol `
  --output-dir results/gpt

# Claude：Anthropic Messages API
$env:ANTHROPIC_API_KEY="..."
repairscope run-suite data/pilot --provider anthropic --model YOUR_CLAUDE_MODEL `
  --output-dir results/claude

# Qwen：DashScope OpenAI-compatible API
$env:DASHSCOPE_API_KEY="..."
repairscope run-suite data/pilot --provider qwen --model qwen3.7-plus `
  --output-dir results/qwen

# DeepSeek：OpenAI-compatible API
$env:DEEPSEEK_API_KEY="..."
repairscope run-suite data/pilot --provider deepseek --model deepseek-chat `
  --output-dir results/deepseek
```

模型名必须显式填写，避免供应商更新默认别名后实验无法复现。每个任务的完整轨迹写入 `runs.jsonl`，聚合结果写入 `summary.json`。密钥只从环境变量读取，不进入日志。

更多细节见 [英文 README](README.md)、[数据卡](docs/DATA_CARD.md) 和 [评测协议](docs/EVALUATION.md)。
