# RepairScope-Bench

**当工具 Agent 已经产生真实外部承诺、随后执行受阻时，它能否完成剩余目标，
同时避免选择一个在经济上被其他方案严格支配的恢复范围？**

RepairScope-Bench v0.6 是一个从统一失败状态开始的恢复能力评测。构建器先通过
真实工具创建机票、酒店、订单、保修与服务合同，并把结果持久化到
STATE-Bench 的领域数据库；随后只改变一个库存、兼容性或合同事实，实际执行一次
失败调用，并保存带 SHA-256 的权威快照。每个模型都从该快照的独立副本开始。

模型看不到“应该保留或撤销哪些订单”，也看不到总损失或标准答案。它只能看到：

- 自然语言用户请求；
- 精简的前序成功工具轨迹；
- 最新一次失败结果；
- 查询订单、政策、库存、兼容性以及执行修改的普通领域工具。

[Data Card](docs/DATA_CARD.md) · [评测协议](docs/EVALUATION.md) ·
[论文故事线](docs/RESEARCH_STORY.md) · [模型接入](docs/PROVIDERS.md)

## v0.6 的关键变化

- **真实领域状态。** 旅行任务直接实例化 STATE-Bench 的
  `TravelEnvironment`，采购任务实例化 `CustomerSupportEnvironment`；
  依赖固定在提交 `4efcbf2d4fe60df04878859b692d9391f3d5b33a`。
- **可验证的失败边界。** 每项前序承诺都能追溯到一次成功写操作；最后一次调用
  确实失败；状态、轨迹和交易账本均可重放。
- **不泄露答案。** 工具只给出单个订单、退款预览、合同条款和产品事实，没有
  全局损失汇总、隐藏目标函数、`finish()` 或额外 mutation budget。
- **客观多目标判分。** 先检查全部硬目标，再比较不可逆损失与恢复期净支出。
  不设置人工效用权重，所有 Pareto 非支配结果均接受。
- **单事实反事实。** 每个任务家族有四个独立快照，只改变一个退款事实或一个
  套餐/许可证条款，并要求 Pareto 最优恢复范围随之翻转。
- **双 Oracle 校验。** 有界语义状态搜索和独立候选范围枚举必须给出相同的
  可行范围及 Pareto 前沿，否则任务不能发布。

## 数据集

默认数据集包含 24 个独立失败状态：

| 领域 | 家族 | 失败前已经生效 | 失败操作 |
|---|---|---|---|
| 旅行 | 上海会议晚餐 | 航班、酒店、接送、会议票 | 餐厅预订 |
| 旅行 | 目的地联动安排 | 已改目的地的航班、酒店、地面交通、票务 | 新酒店预订 |
| 旅行 | 缩短行程 | 航班、酒店、租车、活动票 | 日期联动替换 |
| 售后采购 | 放射科工作站 | 电脑、显示器、保修、软件 | 扩展坞购买 |
| 售后采购 | 诊所冷链设备 | 冷柜、传感器、网关、服务、安装 | 电池购买 |
| 售后采购 | 影像制作套件 | 相机、存储、镜头、保障、软件 | 配件购买 |

每个家族包含 `refund-low`、`refund-full`、`penalty-none` 和
`penalty-high` 四个变体。每题有三种可执行的语义恢复范围，既有局部修复，也有
跨订单替换；其中至少一个能够完成目标的方案会被另一个方案在经济上严格支配。

本版本只评测失败后的恢复阶段，不声称覆盖失败前的规划质量。

## 客观判分原则

对每个满足硬目标的终态计算：

```text
irreversible_loss =
    取消费、修改费和不可退款金额
  + 返利或许可证追回
  + 恢复过程中买入后又浪费的商品

net_recovery_outlay =
    失败边界之后的新增付款、费用和结算
  - 失败边界之后收到的退款与补偿
```

如果方案 A 在两项上都不比 B 差，并且至少一项严格更好，则 A 支配 B。所有
非支配方案都算正确；更改多少已有承诺、调用多少工具只作为诊断，不决定主通过率。

主指标包括 Goal Pass@1/Pass^5、Non-Dominated Repair
Pass@1/Pass^5、Dominated Repair Rate、两类经济 regret，以及
over-repair、under-repair、工具错误和轮次耗尽。

若模型找到比已知前沿更好的可行方案，该运行标记为 `oracle_violation`，不惩罚
模型，并从正式汇总中排除该题。

## 安装、验证和测试

需要 Python 3.12+ 和 Git。

```bash
python -m pip install -e .
python scripts/build_v06.py
repairscope validate data/v06
repairscope run-baselines data/v06
python -m unittest discover -s tests -v
```

当前 24 题的确定性基线结果：

| 基线 | Goal Pass | Non-Dominated Repair Pass |
|---|---:|---:|
| 不修复 | 0 / 24 | 0 / 24 |
| 只修失败部分 | 24 / 24 | 12 / 24 |
| 依赖闭包修复 | 24 / 24 | 12 / 24 |
| 全部撤销重做 | 24 / 24 | 0 / 24 |
| 只看最终标价 | 24 / 24 | 12 / 24 |
| 只最大化毛退款 | 24 / 24 | 0 / 24 |
| Pareto Oracle | 24 / 24 | 24 / 24 |

这正是评测希望区分的现象：Agent 可以把任务做完，却仍然选择了一个客观次优的
恢复范围。

## 运行模型

```bash
repairscope run-suite data/v06 --provider openai \
  --model YOUR_MODEL_ID --repeats 5 --output-dir results/openai

repairscope run-suite data/v06 --provider anthropic \
  --model YOUR_MODEL_ID --repeats 5 --output-dir results/anthropic

repairscope run-suite data/v06 --provider qwen \
  --model YOUR_MODEL_ID --repeats 5 --output-dir results/qwen

repairscope run-suite data/v06 --provider deepseek \
  --model YOUR_MODEL_ID --repeats 5 --output-dir results/deepseek
```

每题最多 15 个模型轮次。模型可以自然停止；评测直接读取最终数据库状态，不要求
调用 `finish()`。

## 仓库结构

```text
data/v06/                     v0.6 公开任务与失败快照
data/gold/v06.json            仅评测器使用的 Pareto 前沿与重放轨迹
data/legacy/v0.5/             归档的 v0.4/v0.5 数据与 gold
scripts/build_v06.py          确定性失败边界构建器
src/repairscope_bench/        adapter、约束、Oracle、评测器和运行框架
tests/                        单元、集成、重放与协议测试
```

## 创新边界

本文不宣称首次提出“部分回退”。可辩护的贡献是：在已执行且持久存在的外部承诺、
可查询的政策与可审计的经济后果下，系统评测语言 Agent 是否会完成目标，却选择
一个被其他可行恢复方案客观支配的修复范围。
