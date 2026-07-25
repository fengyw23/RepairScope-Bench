# RepairScope-Bench v2.0 严格试点

## 当前状态

v2.0 开发轨包含 12 个基础情境、24 道可执行任务。每个情境构成一对
严格的单事实反事实任务。它是正式扩充 160 题之前的质量试点，不替换
已冻结的 v1.1。

## 双层经济评价

`Scope Non-Dominated Pass` 根据失败边界与最终有效承诺之间的必要变化，
计算恢复范围本身的规范经济结果。中途购买后又取消、重复修改等无效绕路
不进入这一层。

`Realized Non-Dominated Pass` 根据模型真实执行产生的完整交易账本判分，
所有多余购买、取消和合同费用都会保留。

因此结果分成：

```text
Goal Pass
  → Scope Non-Dominated Pass
  → Realized Non-Dominated Pass
```

范围通过但真实执行未通过，表示 Agent 选择了合理的保留/撤销范围，但
执行过程造成了额外浪费。取消一个原有承诺再重新购买仍属于范围变化，不会
被错误归为单纯执行浪费。

## 双 Oracle

Oracle A 不调用运行时工具，穷举保留的已有承诺与可购买选项组合，独立检查
硬目标、兼容关系、合同、退款和 Pareto frontier。

Oracle B 将 Oracle A 声称可行的每个终态使用模型可见的公开工具真实重放，
由运行时交易账本重新计算经济结果。某个终态不可达或两个 frontier 不一致
时，该题不能进入数据集。

双 Oracle 用于构建和验证 computational ground truth。正式模型实验直接
读取冻结 gold，不会每次重新进行完整搜索。

## 严格反事实

每对任务必须满足：

- 权威数据中只有一个源字段发生变化；
- 模型必须主动调用指定查询工具才能看到该事实；
- 其他状态、请求、库存和前序轨迹完全相同；
- 两个版本的可接受恢复范围集合没有交集；
- 固定使用同一个恢复范围不可能同时通过两个版本。

私有 gold 保存变化字段的 JSON Pointer、揭示工具、记录 ID 和预期范围。
评分器记录 Agent 是否在第一次写操作前查询了这一事实。

## 怎样积累难题设计经验

每题保存三类信息：

1. `reasoning_signature`：多跳传播、阈值、部分数量、桥接修复等多标签；
2. `complexity_profile`：承诺数、候选数、关键事实数、依赖深度、可行范围
   数、frontier 大小、最少修改数和机制交互数；
3. `empirical_difficulty`：任务冻结后，使用校准模型运行结果拟合 Rasch
   难度，并保存锚定题。

`C1–C4` 只表示自动计算的构造复杂度，不再冒充模型实测难度。

`data/v2/mechanism_cards.json` 保存可复用的因果结构、必查证据和常见错误；
`data/v2/coverage_matrix.json` 记录“推理机制 × 领域 × 构造复杂度”的覆盖。
后续扩充优先补空缺单元，而不是复制并换名已有模板。

## 使用

```powershell
python scripts/build_v2_pilot.py
repairscope validate data/v2/pilot
repairscope run-baselines data/v2/pilot
repairscope run-suite data/v2/pilot <模型参数> --output-dir results/v2
repairscope calibrate-difficulty results/v2/runs.jsonl --version v2-calibration-1
```

当前自动验证包括双 Oracle 一致、单源事实变化、反事实 gold 不相交、变化
事实可查询、角色词泄漏为零、ID/顺序置换不改变 Oracle、经济诱导方案和
弱基线通过率门槛。

准确的数据分布与当前限制见
[DATA_CARD_V2_PILOT.md](DATA_CARD_V2_PILOT.md)。
