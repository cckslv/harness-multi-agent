# 🏗️ Harness Engineer — 架构设计文档 v2

> Agent = Model + Harness  
> 模型决定上限，Harness 决定下限

---

## 一、项目定位

站在 4 个标杆仓库的肩膀上，结合 workflow_engine 体系，构建**确定性、可审计、可恢复**的 AI Agent 工程化管控系统。

**参考源：**
- `coleam00/harness-engineering-demo` — PIV 循环 + Hook 自动化
- `watsonctl/agent-harness` — 纠错注册表 + Session 协议 + Execution Lanes
- `MattMagg/agent-harness` — 原则 + 跨域不变量
- `jonzarecki/harness-engineering-skill` — Skill 驱动 + Verification Loops

---

## 二、项目结构

```
harness-engineer/
│
├── ARCHITECTURE.md                    # 本文件
├── AGENTS.md                          # 根治理契约（≤100行，目录式）
│
├── .claude/
│   ├── settings.json                  # Hook 接线
│   │
│   ├── agents/                        # 多角色 Agent 定义
│   │   ├── planner.md                 # 只做方案，不写代码
│   │   ├── executor.md                # 只做实现，不扩范围
│   │   ├── reviewer.md                # 只审 diff，不修代码
│   │   └── verifier.md                # 只验结果，不偷偷改
│   │
│   ├── skills/                        # PIV 标准操作手册
│   │   ├── cognitive-routing/SKILL.md  # 🆕 认知路由层
│   │   ├── plan/SKILL.md
│   │   ├── implement/SKILL.md
│   │   ├── validate/SKILL.md
│   │   └── review/SKILL.md
│   │
│   ├── context/                       # 按需加载（渐进披露）
│   │   ├── architecture.md
│   │   ├── testing.md
│   │   └── security.md
│   │
│   ├── hooks/                         # 自动触发
│   │   ├── post_edit_lint.py
│   │   ├── stop_validate.py
│   │   └── security_guard.py
│   │
│   └── rules/                         # 项目级规则（按技术栈）
│       ├── python-backend.md
│       ├── react-frontend.md
│       └── commit-convention.md
│
├── spec/
│   ├── SPEC.template.md
│   └── prd.template.json
│
├── registry/
│   └── CORRECTIONS.md                 # 纠错注册表（append-only）
│
├── gates/
│   ├── build_gates.py                 # 编译 + 测试 + lint
│   ├── baseline_compare.py            # 基线对比
│   └── quality_score.py               # 重构评分
│
├── persistence/
│   ├── schema.sql                     # Postgres 持久化层
│   └── db_config.py
│
├── mcps/
│   ├── github.mcp.json
│   ├── postgres.mcp.json
│   ├── codebase-search.mcp.json
│   └── audit_log.jsonl               # 🆕 MCP 调用审计（虬 5️⃣）
│
├── workflow_engine/                   # 核心引擎
│   ├── task.py                        # Task.from_legacy（已有）
│   ├── session.py                     # WorkflowSession（已有）
│   ├── guardrails.py                  # run_output_guardrails（已有）
│   ├── handoff.py                     # create_handoff（已有）
│   ├── cognitive_router.py            # 🆕 认知路由层（CR-001~005）
│   │
│   ├── policy/                        # 🆕 控制面（虬 1️⃣）
│   │   ├── lane_selector.py           # 确定性 Lane 决策
│   │   ├── risk_score.py              # 风险评分
│   │   └── context_pack.py            # 上下文打包
│   │
│   ├── recovery/                      # 🆕 失败恢复（虬 2️⃣）
│   │   ├── failure_classifier.py      # 失败类型分类
│   │   ├── retry_policy.py            # 重试策略
│   │   └── rollback_plan.py           # 回滚方案
│   │
│   ├── contract.py                    # 🆕 权限隔离（虬 3️⃣）
│   ├── state_machine.py               # 🆕 状态机约束（虬 4️⃣）
│   ├── events.py                      # 🆕 事件系统（虬 7️⃣）
│   └── lanes.py                       # 🆕 Lane 规则化定义（虬 6️⃣）
│
├── plans/                             # /plan 输出
└── reports/                           # /implement + /review 输出
```

---

## 三、认知层：Cognitive Router

### 核心原则
> 任务进入系统后，禁止直接执行。必须先翻译意图 → 检索知识 → 复用模式。

### 执行链路

```
User Input
    │
    ▼
┌─ CognitiveRouter.process() ──────────────────┐
│  CR-001: 结构化意图（自然语言 → YAML）        │
│  CR-002: 翻译查询（意图 → 检索字段）          │
│  CR-003: 检索知识（Contract → Memory →        │
│           Lessons → Skills → Patterns）       │
│  CR-004: 匹配模式（已有模式 / 需新建）        │
│  CR-005: 经验沉淀（新规则 / 教训 / 记忆）      │
└───────────────────────────────────────────────┘
    │ intent + pattern
    ▼
┌─ LaneSelector.select_lane() ──────────────────┐
│  （原有逻辑，接收认知层输出的意图和模式）       │
└───────────────────────────────────────────────┘
    │ lane number
    ▼
Execute
```

### 模块

```
workflow_engine/cognitive_router.py    # 引擎实现
.claude/skills/cognitive-routing/SKILL.md  # Agent 指令
```

### 五条认知规则

| 规则 | 名称 | 含义 |
|---|---|---|
| CR-001 | Intent First | 禁止直接执行，必须先结构化意图 |
| CR-002 | Translate Before Search | 用户自然语言不能直接作为检索条件 |
| CR-003 | Reuse Before Create | 优先复用已有方案，禁止重复设计 |
| CR-004 | Pattern-Oriented Execution | 执行前必须回答"是否存在成熟模式" |
| CR-005 | Experience Accumulation | 执行后判断是否产生新经验/规则 |

### 意图 → 模式 → Lane 映射

| 意图 | 模式 | 推荐 Lane |
|---|---|---|
| debug | diagnosing_bugs | 2（Full PIV） |
| feature | piv_flow | 2（Full PIV） |
| test | tdd_loop | 2（Full PIV） |
| refactor | codebase_design | 2（Full PIV） |
| explore | explore_pattern | 1（Explore） |
| setup | setup_pattern | 0（Direct） |
| review | review_pattern | 4（Strict Verify） |
| unknown | — | 1（Explore） |

---

## 四、控制面：Lane Selector（虬 1️⃣）

### 核心原则
> Lane 选择必须是 **deterministic function**，不是 prompt 行为。

### 模块

```
workflow_engine/policy/
├── lane_selector.py    # 唯一决策入口
├── risk_score.py       # 输入 → 风险评分
└── context_pack.py     # 按 Lane 打包上下文
```

### Lane Selector 决策函数

```python
def select_lane(task, constraints, session_history) -> int:
    """
    输入：任务、约束、历史会话
    输出：Lane 0~4（唯一、确定性结果）
    """
    risk = calc_risk_score(task, constraints)
    scope = classify_scope(task)
    has_plan = bool(session_history.get("plan_path"))

    if scope == Scope.HOTFIX and risk < 3:
        return Lane.DIRECT           # 0
    if scope == Scope.UNKNOWN or not has_plan:
        return Lane.EXPLORE          # 1
    if scope == Scope.MULTI_STORY:
        if can_parallelize(task):
            return Lane.PARALLEL     # 3
        return Lane.FULL_PIV         # 2（默认）
    if risk >= 7:
        return Lane.STRICT_VERIFY    # 4
    return Lane.FULL_PIV             # 2（默认）
```

### Lane 标准化定义（虬 6️⃣）

| Lane | 名称 | 触发条件 | 流程 |
|---|---|---|---|
| 0 | Direct | hotfix，风险<3 | 直接改 → lint → commit |
| 1 | Explore | 结构不明确 | 探索 → 出地图 → 选 Lane |
| 2 | Full PIV | **默认** | Plan → Implement → Validate → Review |
| 3 | Parallel | 独立子问题，可并行 | 分片 → 并行执行 → 汇合 |
| 4 | Strict Verify | 高风险，多依赖 | PIV + 持续验证循环 |

---

## 五、失败恢复系统（虬 2️⃣）

### 模块

```
workflow_engine/recovery/
├── failure_classifier.py   # 失败 → 分类
├── retry_policy.py          # 重试策略（退避/上限/信号）
└── rollback_plan.py         # 回滚方案
```

### 失败分类与行为

```python
class FailureType(Enum):
    LINT_FAIL       = "lint_fail"        # → auto-fix or retry (max 3)
    TEST_FAIL       = "test_fail"        # → executor 修复 (max 2)
    TYPE_CHECK_FAIL = "type_check_fail"  # → executor 修复
    DESIGN_MISMATCH = "design_mismatch"  # → 回退 planner
    GATE_FAIL       = "gate_fail"        # → freeze + 报告
    CI_FAIL         = "ci_fail"          # → freeze PR + retry executor
    TIMEOUT         = "timeout"          # → 记录 + 人工介入
```

### 重试策略

```python
@dataclass
class RetryPolicy:
    max_retries: int = 3
    backoff_base: float = 2.0       # 指数退避基数（秒）
    escalate_after: int = 2         # 超过此次数 → 升级到人工
    auto_fix_types: tuple = (FailureType.LINT_FAIL,)
```

---

## 六、权限隔离（虬 3️⃣）

### 核心原则
> Prompt 约束 ≠ 安全控制。必须 tool-level enforce。

### contract.py — 角色权限矩阵

```python
ROLE_PERMISSIONS = {
    "planner": {
        "read":  ["*"],                              # 全仓库可读
        "write": ["plans/*", "spec/*", "reports/*"], # 只能写方案和规格
        "deny":  ["*.py", "*.ts", "*.tsx", "*.sql"], # 不能写代码
        "mcp":   ["postgres", "github"],             # 可查数据、读 PR
    },
    "executor": {
        "read":  ["*"],
        "write": ["app/**", "tests/**", "gates/**"],
        "deny":  ["spec/*", "plans/*"],              # 不能改需求和方案
        "mcp":   ["postgres", "codebase-search"],
    },
    "reviewer": {
        "read":  ["*"],
        "write": [],                                  # 完全不写
        "deny":  ["*"],
        "mcp":   ["codebase-search", "github"],
    },
    "verifier": {
        "read":  ["*"],
        "write": ["reports/*"],
        "deny":  ["app/**", "spec/*", "plans/*"],     # 什么都不改
        "mcp":   ["postgres"],
    },
}
```

### Enforce 机制

- **PreToolUse Hook** 拦截所有 Write/Edit/Bash 操作
- 根据当前 Agent 角色匹配权限矩阵
- 命中 `deny` → 返回 `permissionDecision: deny` + 原因
- 审计日志写入 `mcps/audit_log.jsonl`

---

## 七、状态机约束（虬 4️⃣）

### 模块

```
workflow_engine/state_machine.py
```

### 合法状态流转

```
pending ──→ planning ──→ planned
                            │
                            ▼
                       implementing ──→ implemented
                            │                │
                            ▼                ▼
                       validating      failed ──→ retrying ──→ planning
                            │
                            ▼
                       validated
                            │
                            ▼
                       reviewing ──→ done
                            │
                            ▼
                       rejected ──→ planning
```

### 强制规则

```python
VALID_TRANSITIONS = {
    "pending":      {"planning"},
    "planning":     {"planned", "failed"},
    "planned":      {"implementing"},
    "implementing": {"implemented", "failed"},
    "implemented":  {"validating"},
    "validating":   {"validated", "failed"},
    "validated":    {"reviewing"},
    "reviewing":    {"done", "rejected"},
    "rejected":     {"planning"},
    "failed":       {"retrying"},
    "retrying":     {"planning", "implementing", "validating"},
    "done":         set(),                    # 终态
}
```

### 状态更新入口（唯一）

```python
def transition(from_status: str, to_status: str) -> bool:
    if to_status not in VALID_TRANSITIONS.get(from_status, set()):
        raise InvalidTransitionError(
            f"Illegal transition: {from_status} → {to_status}"
        )
    # 写入 DB + 发射事件
    db.update_story(story_id, status=to_status)
    events.emit(StatusChanged(story_id, from_status, to_status))
    return True
```

---

## 八、MCP 调用审计（虬 5️⃣）

### 审计日志格式（JSONL）

```json
{"agent":"executor","tool":"github.create_pr","input":{"title":"...","base":"main"},"output":"pr_123","session_id":"abc-123","timestamp":"2026-06-20T10:30:00Z"}
{"agent":"verifier","tool":"postgres.query","input":"SELECT * FROM sessions WHERE id='abc-123'","output":"{'status':'active'}","session_id":"abc-123","timestamp":"2026-06-20T10:30:05Z"}
```

### 作用
- 出问题时可追溯"哪个 Agent 在什么时间做了什么"
- PR 责任清晰
- 防"黑盒行为"

---

## 九、事件系统（虬 7️⃣）

### 模块

```
workflow_engine/events.py
```

### 事件类型

```python
class EventType(Enum):
    STORY_STARTED    = "story_started"
    PLAN_GENERATED   = "plan_generated"
    CODE_COMMITTED   = "code_committed"
    GATE_EXECUTED    = "gate_executed"
    GATE_PASSED      = "gate_passed"
    GATE_FAILED      = "gate_failed"
    PR_CREATED       = "pr_created"
    STATUS_CHANGED   = "status_changed"
    RECOVERY_STARTED = "recovery_started"
    RECOVERY_DONE    = "recovery_done"
    SESSION_ENDED    = "session_ended"
```

### 订阅者

| 事件 | 触发的动作 |
|---|---|
| STORY_STARTED | 状态机 transition(pending→planning) |
| GATE_FAILED | recovery 模块介入 |
| PR_CREATED | 飞书通知 @凡哥 |
| SESSION_ENDED | 写入 CORRECTIONS_REGISTRY |

---

## 十、持久化层

### Postgres 表（5 张）

| 表 | 用途 | 关键字段 |
|---|---|---|
| `sessions` | 会话历史 | project_id, lane, status, current_story, timestamps |
| `stories` | PRD 故事执行状态 | prd_key, status(受状态机约束), failed_reason, agent |
| `corrections` | 纠错注册表（append-only） | type(pitfall/constraint), code, scope |
| `constraints` | 项目约束规则 | category, rule_text, is_hard, source |
| `gate_results` | 门禁执行结果 | gate_name, result, baseline_delta, session FK |

---

## 十一、MCP 层

| MCP | 解决的问题 | 配置 |
|---|---|---|
| **GitHub** | PR/Issue/分支操作 | `@modelcontextprotocol/server-github` |
| **Postgres** | Agent 直接查询运行状态 | `@modelcontextprotocol/server-postgres` |
| **codebase-search** | AST 级符号导航 | FastMCP，自建 `codebase_search.py` |

---

## 十二、完整执行链路（Lane 2 示例）

```
用户: "实现用户登录功能"
          │
          ▼
   ┌─ lane_selector(task, constraints, history) ─┐
   │  risk=4, scope=MULTI_STORY, no parallel     │
   │  → Lane 2 (Full PIV)                        │
   └──────────────────────────────────────────────┘
          │
          ▼
   ┌─ /plan ────────────────────────────────────┐
   │  agent: planner                            │
   │  reads: AGENTS.md, context/auth.md         │
   │  writes: plans/login-plan.md               │
   │  events: PLAN_GENERATED                    │
   │  state: pending → planning → planned       │
   └─────────────────────────────────────────────┘
          │
          ▼
   ┌─ /implement ───────────────────────────────┐
   │  agent: executor                           │
   │  reads: plans/login-plan.md                │
   │  per-task: edit → lint → test → next       │
   │  state: planned → implementing             │
   │  if gate fail → failure_classifier → retry │
   │  state: implementing → implemented         │
   └─────────────────────────────────────────────┘
          │
          ▼
   ┌─ /validate ────────────────────────────────┐
   │  agent: verifier                           │
   │  runs: ruff + mypy + pytest + tsc + vitest │
   │  writes: gate_results (DB)                 │
   │  if all pass → validated                   │
   │  if fail → recovery 模块介入               │
   └─────────────────────────────────────────────┘
          │
          ▼
   ┌─ /review ──────────────────────────────────┐
   │  agent: reviewer                           │
   │  reads: diff via GitHub MCP                │
   │  checks: naming, patterns, auth, security  │
   │  writes: reports/login-review.md           │
   │  state: validated → reviewing → done       │
   └─────────────────────────────────────────────┘
          │
          ▼
   ┌─ 归档 ─────────────────────────────────────┐
   │  GitHub MCP: 创建分支 + Push + PR          │
   │  飞书 MCP: @凡哥 "登录功能已就绪，待审阅"   │
   │  Corrections: 记录本次踩坑（如有）         │
   │  events: SESSION_ENDED                     │
   └─────────────────────────────────────────────┘
```

---

## 十三、MVP 实施路径

### 第一阶段：P0 模块（控制面）

| 顺序 | 模块 | 为什么先做 |
|---|---|---|
| 1 | `state_machine.py` | 没有它，状态数据不可信 |
| 2 | `contract.py` | 没有它，Agent 可以越权 |
| 3 | `policy/lane_selector.py` | 没有它，执行路径不确定 |

### 第二阶段：Lane 2 闭环

| 步骤 | 内容 |
|---|---|
| 选项目 | 从现有项目（如 ai-agent）中选一个真实故事 |
| 写 SPEC | 用 SPEC.template.md 写出需求 |
| /plan | planner Agent 产出实施计划 |
| /implement | executor Agent 逐步实现 + 每步验证 |
| /validate | verifier Agent 跑全部门禁 |
| /review | reviewer Agent 审 diff + 出报告 |

### 第三阶段：P1 模块（恢复 + 审计）

| 模块 | 内容 |
|---|---|
| `recovery/` | failure_classifier + retry_policy + rollback |
| `mcps/audit_log.jsonl` | MCP 调用审计 |
| `events.py` | 事件系统 |

---

## 附录：四仓库对照速查

| 维度 | coleam00 | watsonctl | MattMagg | jonzarecki |
|---|---|---|---|---|
| 核心机制 | PIV + Hooks | Corrections + Lanes | Principles + Invariants | Skills + Debug |
| 我们借鉴 | PIV 流程、Hook、context/ | Registry、Session 协议、Lanes | 7 原则、不变量 | Skill 格式、失败诊断表 |
| 关键数据点 | CLAUDE.md≤100行 | 5 级 Lane | 6 跨域不变量 | 83%→96% |
