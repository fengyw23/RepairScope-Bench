# RepairScope-Bench

RepairScope-Bench 用于评测：多步任务已经产生若干持久外部承诺，随后某个操作失败时，Agent 能否自行查询环境、找到满足剩余目标的修复方案，并尽量减少恢复动作造成的额外不可逆损失。

例如，Agent 已经订好机票和酒店，预订车辆时发现原车辆无库存。正确行为不一定是只换车，也不一定是撤销全部订单。Agent 需要查询当前订单、车辆库存、酒店退款政策、修改报价和总支出，再决定保留、修改或替换哪些承诺。

当前版本是 **v0.3.2 研究原型**，包含4个反事实家族、16个任务。所有模型从同一个失败状态开始。该版本用于验证评测协议和运行环境，尚不足以支撑排行榜结论。

## 核心评测问题

> 在已有有效承诺的统一失败状态下，Agent 能否通过工具自行发现恢复条件，完成剩余目标，并选择额外不可逆损失最小的恢复方案？

该协议具有五个关键特征：

1. 所有模型从完全相同的失败状态开始；
2. 取消、预订和修改会真实改变可执行环境中的持久状态；
3. 初始文本只给出原始失败调用，不总结替代方案、退款政策或可行性；
4. Agent 必须通过定向工具查询承诺、退款、库存、修改报价、兼容性和当前成本；
5. 隐藏求解器枚举可行方案，并接受完整目标上并列最优的所有轨迹。

本版本不评测失败前的自主规划和执行，而是隔离评测失败后的恢复能力。

## 任务家族

| 家族 | 统一失败边界 | 不同环境事实导致的结果 |
|---|---|---|
| 丹佛旅行套餐 | 机票和酒店已确认，租车失败 | 只补订车辆、更换酒店、修改航班、不可行 |
| 目的地变更 | SFO 航班已确认，新酒店售罄 | 更换酒店、保留旧酒店、选择另一家酒店、不可行 |
| 缩短行程 | 酒店晚数已调整，租车日期修改失败 | 保留多一天租车、更换车辆、原地修改、不可行 |
| 办公设备 | 笔记本和显示器已下单，扩展坞订单因不兼容作废 | 补订扩展坞、更换电脑和扩展坞、选择通用扩展坞、不可行 |

同一家族的不同变体使用相同的用户目标形式和相同的原始失败信息。决定答案的退款、库存、兼容性与修改规则只能通过工具发现。

## 客观损失

评测器维护三个可审计账本：

- `lifecycle_cost`：任务全生命周期中服务商最终保留的现金；
- `recovery_loss`：取消既有承诺造成的未退款损失、恢复期间买入后又取消的未退款支出，以及原地修改产生的正向净现金支出；
- `financial_regret`：Agent 的全生命周期成本与相同失败状态下最低可行成本之差。

主指标 `extra_loss` 为 Agent 的 `recovery_loss` 减去隐藏 oracle 计算出的最小可行 `recovery_loss`。满足硬约束后，当前任务使用以下字典序目标：

```text
(recovery_loss,
 lifecycle_cost,
 mutated_prior_commitments,
 state_changing_actions)
```

因此，若更换一个可全额退款的旧承诺不会产生不可逆损失，并且能降低总成本，
更换方案优于保留方案；只有损失和总成本都相同时，才优先少改已有承诺。

## Agent 可使用的工具

```text
list_commitments()
get_commitment_details(commitment_id)
get_cancellation_quote(commitment_id)
search_options(slot)
get_modification_quote(commitment_id, to_option_id)
check_compatibility(left_option_id, right_option_id)
get_cost_summary()
cancel(commitment_id)
book(option_id)
modify(commitment_id, to_option_id)
finish()
report_infeasible(reason)
```

读取工具被有意拆开：列出承诺不会同时泄露退款和修改规则；搜索只返回指定类别中当前可用的候选项；退款与修改信息必须针对具体承诺查询。评测约束、gold 和 oracle 轨迹不会出现在模型上下文中。

## 安装与验证

```powershell
python -m pip install -e .
python scripts/build_pilot.py
repairscope validate data/pilot
python -m unittest discover -s tests -v
repairscope run-baselines data/pilot
```

## 接入模型

```powershell
# OpenAI
$env:OPENAI_API_KEY="..."
repairscope run-suite data/pilot --provider openai --model YOUR_MODEL `
  --output-dir results/openai

# Anthropic
$env:ANTHROPIC_API_KEY="..."
repairscope run-suite data/pilot --provider anthropic --model YOUR_MODEL `
  --output-dir results/anthropic

# Qwen
$env:DASHSCOPE_API_KEY="..."
repairscope run-suite data/pilot --provider qwen --model YOUR_MODEL `
  --output-dir results/qwen

# DeepSeek
$env:DEEPSEEK_API_KEY="..."
repairscope run-suite data/pilot --provider deepseek --model YOUR_MODEL `
  --output-dir results/deepseek
```

模型名称必须显式指定。每次运行的完整输入、模型输出、工具调用、工具结果和评分写入 `runs.jsonl`，汇总结果写入 `summary.json`。密钥只从环境变量读取，不写入运行记录。

更多细节见 [数据说明](docs/DATA_CARD.md)、[评测协议](docs/EVALUATION.md) 和 [研究定位](docs/RESEARCH_STORY.md)。
