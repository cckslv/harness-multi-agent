# Harness Engineer — 领域术语表

> 凡哥项目。Agent 工程化管控系统（Harness = Model + Runtime 中的 Runtime）。
> 每个术语只有一个权威定义。写代码、写文档、Agent 间通信统一用这些词。

---

## 核心实体

### PRD

工作规格文档（Work Specification）。一个 PRD 是一组相关 Story 的容器——不限于"产品需求"，修 Bug、重构、加功能都可以写成一个 PRD。对应文件：`spec/prd.template.json`。

**关系**：1 PRD → N Stories
**注意**：PRD 这个名字来自传统产品管理，但在 Harness 里它是纯技术概念——任何需要拆分为多个 Story 的工作都可以用一个 PRD 来承载。

### Story

PIV 流水线中的最小执行单元。一个 Story 经过状态机完整流转：pending → planning → planned → implementing → implemented → validating → validated → reviewing → done。

**关系**：N Stories → 1 PRD（通过 `stories.prd_key` 关联）
**代码**：`state_machine.py` → `StoryStatus`

### Task

Lane Selector 的原始输入。尚未分类、尚未拆分的用户请求。经过 Cognitive Router 和 Lane Selector 处理后，转化为 1~N 个 Story。

**代码**：`policy/lane_selector.py` → `TaskProfile`
**与 Story 的区别**：Task 是入口形态，Story 是执行形态。不要混用。

### Session

一次 Claude Code 对话窗口。一个 Session 可以处理多个 Story，但同一时刻只能有一个 `current_story`。Session 有自己的生命周期状态机（active → paused → completed/failed）。

**代码**：`state_machine.py` → `SessionStatus`
**与 Story 的关系**：1 Session 包含 N Stories（逐个处理），通过 `sessions.current_story` 指向当前处理的 Story。

### Handoff

结构化上下文交接协议。将当前会话的关键信息（前置任务、约束、参考文件、当前状态）打包为交接文档，供下一个 Session 或另一个 Agent 无缝接续。

**原则**：交接即协议——每次收到任务，先确认 Handoff 上下文。
**代码**：`workflow_engine/handoff.py` → `create_handoff()`
**与 Session 的关系**：Handoff 是 Session 之间的桥梁。一个 Session 通过 Handoff 将上下文传递给下一个 Session。

---

## 执行体系

### Lane

执行通道（0~4），由 Lane Selector 确定性决策。Lane 不是 prompt 行为——相同输入必然产生相同 Lane。

| Lane | 名称 | 含义 |
|:---|:---|:---|
| 0 | Direct | 直接执行（hotfix，低风险） |
| 1 | Explore | 先探索，再决策 |
| 2 | Full PIV | Plan → Implement → Validate → Review |
| 3 | Parallel | 拆分后并行执行 |
| 4 | Strict Verify | 持续验证循环（高风险） |

**代码**：`lanes.py` → `Lane`、`policy/lane_selector.py` → `select_lane()`

### PIV

Plan → Implement → Validate → Review 的标准执行循环。Lane 2 的默认流程，是 Harness 的核心工作流。

### Validate

PIV 的第三个阶段。在此阶段依次运行所有已配置的 Gate。**全部 Gate 通过 → validated；任一 Gate 失败 → recovery 模块介入。**

**与 Gate 的关系**：Validate 是阶段，Gate 是阶段内的具体检查项（lint gate、test gate、type check gate）。一个 Validate 包含 N 个 Gate。

### Gate

门禁检查——Validate 阶段内的单个自动化验证项。每个 Gate 独立执行，独立失败。当前已定义的 Gate：lint gate（ruff）、test gate（pytest/vitest）、type check gate（mypy/tsc）。

**代码**：`recovery/failure_classifier.py` → `FailureType`（`LINT_FAIL`、`TEST_FAIL`、`TYPE_CHECK_FAIL`、`GATE_FAIL`）
**通过标准**：全过才过（不是加权评分）。`gates/quality_score.py` 预留了评分接口，但当前未启用。

### Cognitive Route

认知路由。所有任务进入系统后的第一步：Intent → Translate → Search → Pattern → Execute。五条规则（CR-001 ~ CR-005），由 `cognitive_router.py` 实现。

---

## 规则与记忆

### Correction

纠错注册表中的一条记录。是 Pitfall 和 Constraint 的父概念。存储在 `registry/CORRECTIONS.md`（append-only）和数据库 `corrections` 表中。

### Pitfall

已知错误记录（"我们犯过这个错"）。过去时——记录错误现象、原因和正确做法。编号 P-XXX。

**示例**：P-001（加 MCP 前没搜 Windows 兼容性）

### Constraint

行为约束规则（"以后必须这样做"）。将来时——定义 Agent 的行为边界，绑定到所有未来执行。编号 C-XXX。

**关系**：Pitfall 和 Constraint 都是 Correction。Pitfall 是"记住踩过的坑"，Constraint 是"扎下的篱笆"。

### Contract Rule

合约规则——Agent 不可违反的行为边界。存储在 `registry/rules.md`，是所有知识检索的最高优先级（CR-003 优先级 0）。编号 R-C-XXX。

**区别于 Constraint**：Contract Rule 更基础（如"找不到就说不知道"），Constraint 更具体（如"executor 不能修改 spec/"）。两者都绑定行为，但 Contract Rule 是全局铁律，Constraint 按项目/范围。

---

## 角色

| 角色 | 职责 | 能写什么 | 不能写什么 |
|:---|:---|:---|:---|
| planner | 只做方案 | plans/, spec/, reports/ | *.py, *.ts, *.sql |
| executor | 只做实现 | app/, tests/, gates/ | spec/, plans/ |
| reviewer | 只审 diff | 无 | 一切 |
| verifier | 只验结果 | reports/ | app/, spec/, plans/ |

**代码**：`contract.py` → `AgentRole`、`ROLE_PERMISSIONS`

---

## 避免混用

| 不要这么说 | 应该说 | 原因 |
|:---|:---|:---|
| "这个 Task"（指 PIV 中的执行单元） | "这个 Story" | Task 是 Lane Selector 的输入，Story 是 PIV 的执行单元 |
| "一个 Session 就是一次 /implement" | "一个 Session 可以包含多个 Story" | Session = 对话窗口，不是单个执行动作 |
| "写一条 Correction"（分不清类型时） | "写一条 Pitfall" 或 "加一条 Constraint" | 明确是记录错误还是定义约束 |
| "这个 Bug"（在 Lane Selector 语境下） | "这个 Hotfix" | Hotfix 是 Lane 0 触发条件中的 Scope 类型 |
| "交给 Agent 做" | "executor 做"（或 planner/reviewer/verifier） | Agent 是统称，角色是具体职位 |
| "PRD 写完了"（指 PRD 这个词本身是产品需求） | "工作规格写完了" | PRD 在 Harness 里是技术容器，不止产品需求 |
| "Validate 挂了"（分不清哪个 Gate） | "lint gate 挂了" 或 "test gate 挂了" | Validate 是阶段，Gate 是具体检查项 |
| "刚才的对话"（指 Session 间的上下文传递） | "上一个 Handoff" | Handoff 是 Session 之间的正式交接协议 |
