"""
Cognitive Router — 认知路由层。

Harness 的基础认知流程：任务进入系统后，先翻译意图、检索知识、复用模式，
再进入 Lane Selector 决定执行通道。

核心规则（CR-001 ~ CR-007）：
- CR-001: Intent First        —— 禁止直接执行，必须先结构化意图
- CR-002: Translate First     —— 用户自然语言不能直接作为检索条件
- CR-003: Reuse First         —— 优先复用已有方案，禁止重复设计
- CR-004: Pattern First       —— 执行前必须回答"这个需求是否有成熟模式"
- CR-005: Accumulate          —— 执行后判断是否产生新经验/规则/模式
- CR-006: Search Before Design —— 新领域必须搜索外部参考，禁止从零推导设计方案
- CR-007: Pattern Registration —— 外部学到的有效模式必须沉淀回 Harness

与 Lane Selector 的关系：
    Request → CognitiveRouter → LaneSelector → Execute
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── 基础类型 ──────────────────────────────

class TaskIntent(Enum):
    """任务意图分类。"""
    DEBUG = "debug"                   # 调试/修复
    FEATURE = "feature"               # 新功能开发
    REFACTOR = "refactor"             # 重构
    EXPLORE = "explore"               # 探索/理解代码
    SETUP = "setup"                   # 环境/配置初始化
    DOCUMENT = "document"             # 文档生成
    REVIEW = "review"                 # 代码审查
    TEST = "test"                     # 测试编写
    UNKNOWN = "unknown"               # 无法分类


class TaskDomain(Enum):
    """任务领域。"""
    BACKEND = "backend"
    FRONTEND = "frontend"
    DATABASE = "database"
    DEVOPS = "devops"
    SECURITY = "security"
    AI_AGENT = "ai_agent"
    DOCUMENTATION = "documentation"
    GENERAL = "general"


class KnowledgeSource(Enum):
    """知识来源，按 CR-003 优先级排列。"""
    CONTRACT_RULES = 0    # 合约规则（最高优先级）
    PROJECT_MEMORY = 1    # 项目记忆
    LESSONS_LEARNED = 2   # 经验教训
    SKILLS = 3            # 已定义 Skill
    WORKFLOW_PATTERNS = 4 # 工作流模式
    EXTERNAL = 5          # 外部知识（最后手段）


class PatternMatch(Enum):
    """模式匹配结果。"""
    EXACT = "exact"           # 精确匹配，直接复用
    ADAPTABLE = "adaptable"   # 可用已有模式，需适配
    NEW = "new"               # 无已有模式，需新建
    UNCERTAIN = "uncertain"   # 信息不足，需先探索


# ── 数据结构 ──────────────────────────────

@dataclass
class IntentResult:
    """CR-001 输出：结构化意图。"""
    user_input: str
    intent: TaskIntent
    task_type: str                  # 具体任务类型标签
    domain: TaskDomain
    keywords: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    expected_output: list[str] = field(default_factory=list)
    confidence: float = 1.0         # 分类置信度 0~1

    def to_dict(self) -> dict:
        return {
            "intent": self.intent.value,
            "task_type": self.task_type,
            "domain": self.domain.value,
            "keywords": self.keywords,
            "constraints": self.constraints,
            "expected_output": self.expected_output,
        }

    def to_yaml(self) -> str:
        """输出 YAML 格式（供 Prompt 使用）。"""
        lines = [
            f"intent: {self.intent.value}",
            f"task_type: {self.task_type}",
            f"domain: {self.domain.value}",
            f"keywords:",
        ]
        for k in self.keywords:
            lines.append(f"  - {k}")
        lines.append(f"constraints:")
        for c in self.constraints:
            lines.append(f"  - {c}")
        lines.append(f"expected_output:")
        for e in self.expected_output:
            lines.append(f"  - {e}")
        return "\n".join(lines)


@dataclass
class QueryFields:
    """CR-002 输出：检索字段。"""
    keywords: list[str]
    domains: list[KnowledgeSource]
    task_type: str = ""
    constraints: list[str] = field(default_factory=list)


@dataclass
class KnowledgeResult:
    """CR-003 输出：检索结果。"""
    source: KnowledgeSource
    matches: list[str]              # 匹配到的规则/经验/模式标识
    suggestions: list[str] = field(default_factory=list)
    searched: bool = False


@dataclass
class PatternResult:
    """CR-004 输出：模式匹配结果。"""
    match: PatternMatch
    pattern_name: str = ""          # 匹配到的模式名
    confidence: float = 0.0
    recommended_lane: Optional[int] = None  # 建议的 Lane
    reasoning: str = ""
    needs_validation: bool = False   # 新模式需验证
    should_register: bool = False    # 是否应注册新模式


@dataclass
class NoveltyCheck:
    """CR-006 输入/输出：新领域检测。"""
    is_new_domain: bool = False
    reasons: list[str] = field(default_factory=list)
    # 新领域信号：项目类型/技术栈/平台/框架/工具链/业务领域
    signals: list[str] = field(default_factory=list)
    suggested_keywords: list[str] = field(default_factory=list)
    # 外部搜索结果
    external_refs_found: bool = False
    external_refs_count: int = 0
    external_patterns: list[str] = field(default_factory=list)


@dataclass
class AccumulateAction:
    """CR-005 输出：经验沉淀行动。"""
    action_type: str                # "lesson" | "rule" | "pattern" | "memory"
    title: str
    content: str
    target_file: str = ""           # 建议写入的文件路径
    priority: str = "normal"        # "high" | "normal" | "low"


@dataclass
class CognitiveResult:
    """完整认知路由结果。"""
    intent: IntentResult
    query: QueryFields
    knowledge: KnowledgeResult
    pattern: PatternResult
    novelty: NoveltyCheck = field(default_factory=NoveltyCheck)
    accumulate_actions: list[AccumulateAction] = field(default_factory=list)

    def summary(self) -> str:
        """单行摘要。"""
        parts = [f"Intent: {self.intent.intent.value}/{self.intent.domain.value}"]
        if self.novelty.is_new_domain:
            parts.append(f"🆕 新领域(signals={self.novelty.signals})")
        parts.append(f"Pattern: {self.pattern.match.value}")
        if self.pattern.recommended_lane:
            parts.append(f"Lane {self.pattern.recommended_lane}")
        return " → ".join(parts)


# ── 认知路由器 ────────────────────────────

class CognitiveRouter:
    """
    认知路由器——Harness 的基础认知层。

    使用方式：
        cr = CognitiveRouter()
        result = cr.process("帮我让CC学习一个PPT模板")
        # result.intent → IntentResult
        # result.pattern → PatternResult
        # result.accumulate_actions → list[AccumulateAction]
    """

    # ── CR-001: 意图分类 ────────────────

    # 关键词 → (意图, 领域) 映射表
    _INTENT_SIGNALS: dict[str, tuple[TaskIntent, TaskDomain]] = {
        # 调试类
        "bug": (TaskIntent.DEBUG, TaskDomain.GENERAL),
        "报错": (TaskIntent.DEBUG, TaskDomain.GENERAL),
        "挂了": (TaskIntent.DEBUG, TaskDomain.GENERAL),
        "修": (TaskIntent.DEBUG, TaskDomain.GENERAL),
        "调试": (TaskIntent.DEBUG, TaskDomain.GENERAL),
        "排查": (TaskIntent.DEBUG, TaskDomain.GENERAL),
        "解": (TaskIntent.DEBUG, TaskDomain.GENERAL),
        "不出": (TaskIntent.DEBUG, TaskDomain.GENERAL),
        "异常": (TaskIntent.DEBUG, TaskDomain.GENERAL),
        # 功能类
        "功能": (TaskIntent.FEATURE, TaskDomain.GENERAL),
        "新": (TaskIntent.FEATURE, TaskDomain.GENERAL),
        "加一": (TaskIntent.FEATURE, TaskDomain.GENERAL),
        "实现": (TaskIntent.FEATURE, TaskDomain.GENERAL),
        "开发": (TaskIntent.FEATURE, TaskDomain.GENERAL),
        "添加": (TaskIntent.FEATURE, TaskDomain.GENERAL),
        "增加": (TaskIntent.FEATURE, TaskDomain.GENERAL),
        "帮我写": (TaskIntent.FEATURE, TaskDomain.GENERAL),
        "帮我做": (TaskIntent.FEATURE, TaskDomain.GENERAL),
        "创建": (TaskIntent.FEATURE, TaskDomain.GENERAL),
        "建一个": (TaskIntent.FEATURE, TaskDomain.GENERAL),
        "学习": (TaskIntent.FEATURE, TaskDomain.AI_AGENT),
        "生成": (TaskIntent.FEATURE, TaskDomain.GENERAL),
        # 审查类
        # 重构类
        "重构": (TaskIntent.REFACTOR, TaskDomain.GENERAL),
        "优化": (TaskIntent.REFACTOR, TaskDomain.GENERAL),
        "改": (TaskIntent.REFACTOR, TaskDomain.GENERAL),
        "调整": (TaskIntent.REFACTOR, TaskDomain.GENERAL),
        "改善": (TaskIntent.REFACTOR, TaskDomain.GENERAL),
        # 探索类
        "找": (TaskIntent.EXPLORE, TaskDomain.GENERAL),
        "查": (TaskIntent.EXPLORE, TaskDomain.GENERAL),
        "看看": (TaskIntent.EXPLORE, TaskDomain.GENERAL),
        "了解": (TaskIntent.EXPLORE, TaskDomain.GENERAL),
        "解释": (TaskIntent.EXPLORE, TaskDomain.GENERAL),
        # 测试类
        "测试": (TaskIntent.TEST, TaskDomain.GENERAL),
        "用例": (TaskIntent.TEST, TaskDomain.GENERAL),
        "test": (TaskIntent.TEST, TaskDomain.GENERAL),
        "spec": (TaskIntent.TEST, TaskDomain.GENERAL),
        # 文档类
        "文档": (TaskIntent.DOCUMENT, TaskDomain.DOCUMENTATION),
        "readme": (TaskIntent.DOCUMENT, TaskDomain.DOCUMENTATION),
        "说明": (TaskIntent.DOCUMENT, TaskDomain.DOCUMENTATION),
        # 配置类
        "安装": (TaskIntent.SETUP, TaskDomain.DEVOPS),
        "配置": (TaskIntent.SETUP, TaskDomain.DEVOPS),
        "部署": (TaskIntent.SETUP, TaskDomain.DEVOPS),
        "初始化": (TaskIntent.SETUP, TaskDomain.DEVOPS),
        # 审查类
        "审查": (TaskIntent.REVIEW, TaskDomain.GENERAL),
        "review": (TaskIntent.REVIEW, TaskDomain.GENERAL),
    }

    # 领域信号词
    _DOMAIN_SIGNALS: dict[str, TaskDomain] = {
        "数据库": TaskDomain.DATABASE,
        "数据库": TaskDomain.DATABASE,
        "sql": TaskDomain.DATABASE,
        "postgres": TaskDomain.DATABASE,
        "前端": TaskDomain.FRONTEND,
        "页面": TaskDomain.FRONTEND,
        "ui": TaskDomain.FRONTEND,
        "组件": TaskDomain.FRONTEND,
        "react": TaskDomain.FRONTEND,
        "登录": TaskDomain.BACKEND,
        "注册": TaskDomain.BACKEND,
        "api": TaskDomain.BACKEND,
        "接口": TaskDomain.BACKEND,
        "服务": TaskDomain.BACKEND,
        "fastapi": TaskDomain.BACKEND,
        "agent": TaskDomain.AI_AGENT,
        "mcp": TaskDomain.AI_AGENT,
        "skill": TaskDomain.AI_AGENT,
        "harness": TaskDomain.AI_AGENT,
        "workflow": TaskDomain.AI_AGENT,
        "安全": TaskDomain.SECURITY,
        "认证": TaskDomain.SECURITY,
        "权限": TaskDomain.SECURITY,
        "docker": TaskDomain.DEVOPS,
        "ci": TaskDomain.DEVOPS,
        "部署": TaskDomain.DEVOPS,
    }

    def analyze_intent(self, user_input: str) -> IntentResult:
        """
        CR-001: Intent First

        将用户自然语言输入转换为结构化意图。
        禁止直接执行——必须经过此步骤。

        Args:
            user_input: 用户原始输入

        Returns:
            IntentResult: 结构化意图
        """
        text_lower = user_input.lower()

        # 1. 匹配意图信号
        best_intent = TaskIntent.UNKNOWN
        best_domain = TaskDomain.GENERAL
        best_task_type = ""

        for keyword, (intent, domain) in self._INTENT_SIGNALS.items():
            if keyword in text_lower:
                best_intent = intent
                best_domain = domain
                best_task_type = keyword
                break  # 第一个匹配为准

        # 2. 匹配领域信号（可能覆盖默认领域）
        for keyword, domain in self._DOMAIN_SIGNALS.items():
            if keyword in text_lower:
                best_domain = domain
                break

        # 3. 提取关键词
        keywords = [w for w in text_lower.replace("，", " ").replace("。", " ").split()
                    if len(w) >= 2 and w not in {"帮我", "一个", "这个", "那个", "一下"}]

        # 4. 提取约束
        constraints = []
        if "不能" in text_lower or "不要" in text_lower:
            constraints.append("explicit_deny_detected")
        if "必须" in text_lower:
            constraints.append("hard_requirement_detected")

        # 5. 拆解预期输出
        expected_output = []
        if best_intent == TaskIntent.FEATURE:
            expected_output.append("working_code")
        if best_intent == TaskIntent.DEBUG:
            expected_output.append("bug_fix")
            expected_output.append("regression_test")
        if "ppt" in text_lower or "模板" in text_lower:
            expected_output.append("design_pattern")
            expected_output.append("style_library_entry")

        # 6. 置信度
        confidence = 0.8 if best_intent != TaskIntent.UNKNOWN else 0.3

        return IntentResult(
            user_input=user_input,
            intent=best_intent,
            task_type=best_task_type,
            domain=best_domain,
            keywords=keywords[:8],
            constraints=constraints,
            expected_output=expected_output,
            confidence=confidence,
        )

    # ── CR-002: 翻译查询 ────────────────

    def translate_query(self, intent: IntentResult) -> QueryFields:
        """
        CR-002: Translate Before Search

        将结构化意图转换为检索字段。
        用户自然语言不能直接作为检索条件。

        Args:
            intent: CR-001 输出的结构化意图

        Returns:
            QueryFields: 可用于检索的字段
        """
        # 按优先级排列知识源
        domains = [
            KnowledgeSource.CONTRACT_RULES,
            KnowledgeSource.PROJECT_MEMORY,
            KnowledgeSource.LESSONS_LEARNED,
            KnowledgeSource.SKILLS,
            KnowledgeSource.WORKFLOW_PATTERNS,
        ]
        # 只在需要外部信息时加 external
        if intent.confidence < 0.6 or intent.intent == TaskIntent.UNKNOWN:
            domains.append(KnowledgeSource.EXTERNAL)

        return QueryFields(
            keywords=intent.keywords,
            domains=domains,
            task_type=intent.task_type,
            constraints=list(intent.constraints),
        )

    # ── CR-003: 检索知识 ────────────────

    def search_knowledge(self, query: QueryFields) -> KnowledgeResult:
        """
        CR-003: Reuse Before Create

        按 CR-003 定义的优先级检索已有知识：
        Contract Rules → Project Memory → Lessons → Skills → Patterns → External

        当前为确定性检索（基于本地文件）。未来可扩展为向量检索。

        Args:
            query: CR-002 输出的检索字段

        Returns:
            KnowledgeResult: 检索结果
        """
        matches = []
        suggestions = []

        # 这里返回知识源列表，由 Agent 实际读取文件
        # 确定性部分：指出应该查什么
        suggestions.append("Check registry/rules.md for Contract Rules")
        suggestions.append("Check memory/ for project memory files")
        suggestions.append("Check registry/CORRECTIONS.md for known pitfalls")
        suggestions.append("Check .claude/skills/ for applicable skills")

        # 根据领域给出更具体建议
        if query.task_type:
            suggestions.append(f"Search skills with keyword: {query.task_type}")

        return KnowledgeResult(
            source=KnowledgeSource.CONTRACT_RULES if query.domains else KnowledgeSource.EXTERNAL,
            matches=matches,
            suggestions=suggestions,
            searched=True,
        )

    # ── CR-004: 模式匹配 ────────────────

    def match_pattern(self,
                      intent: IntentResult,
                      knowledge: KnowledgeResult) -> PatternResult:
        """
        CR-004: Pattern-Oriented Execution

        根据意图和已有知识，判断是否存在成熟处理模式。

        Args:
            intent: CR-001 输出
            knowledge: CR-003 输出

        Returns:
            PatternResult: 包含匹配结果和推荐 Lane
        """
        # 已知模式映射
        known_patterns = {
            TaskIntent.DEBUG: ("diagnosing_bugs", PatternMatch.EXACT, 2),
            TaskIntent.FEATURE: ("piv_flow", PatternMatch.ADAPTABLE, 2),
            TaskIntent.TEST: ("tdd_loop", PatternMatch.EXACT, 2),
            TaskIntent.REFACTOR: ("codebase_design", PatternMatch.ADAPTABLE, 2),
            TaskIntent.EXPLORE: ("explore_pattern", PatternMatch.EXACT, 1),
            TaskIntent.SETUP: ("setup_pattern", PatternMatch.ADAPTABLE, 0),
            TaskIntent.DOCUMENT: ("doc_generation", PatternMatch.ADAPTABLE, 2),
            TaskIntent.REVIEW: ("review_pattern", PatternMatch.EXACT, 4),
        }

        if intent.intent in known_patterns:
            name, match, lane = known_patterns[intent.intent]
            return PatternResult(
                match=match,
                pattern_name=name,
                confidence=0.85,
                recommended_lane=lane,
                reasoning=f"Known pattern '{name}' for intent '{intent.intent.value}'",
            )

        # 未知意图 → 需要探索
        if intent.intent == TaskIntent.UNKNOWN:
            return PatternResult(
                match=PatternMatch.UNCERTAIN,
                pattern_name="",
                confidence=0.1,
                recommended_lane=1,
                reasoning="Unknown intent — recommend explore lane",
            )

        # 低置信度 → 先探索
        if intent.confidence < 0.5:
            return PatternResult(
                match=PatternMatch.UNCERTAIN,
                pattern_name="",
                confidence=0.3,
                recommended_lane=1,
                reasoning=f"Low confidence ({intent.confidence:.0%}) — recommend explore first",
            )

        # 无已知模式 → 需新建
        return PatternResult(
            match=PatternMatch.NEW,
            pattern_name="",
            confidence=0.0,
            recommended_lane=2,
            reasoning="No known pattern — will create new",
            needs_validation=True,
            should_register=True,
        )

    # ── 新领域信号 ─────────────────────

    # 触发 CR-006 的领域关键词映射
    _NOVELTY_SIGNALS: dict[str, str] = {
        # 项目类型
        "浏览器插件": "new_project_type",
        "浏览器扩展": "new_project_type",
        "chrome extension": "new_project_type",
        "油猴脚本": "new_project_type",
        "tampermonkey": "new_project_type",
        "userscript": "new_project_type",
        "小程序": "new_project_type",
        "electron": "new_project_type",
        "tauri": "new_project_type",
        "移动端": "new_project_type",
        "app": "new_project_type",
        # 技术栈
        "rust": "new_tech_stack",
        "go": "new_tech_stack",
        "vue": "new_tech_stack",
        "angular": "new_tech_stack",
        "flutter": "new_tech_stack",
        "swift": "new_tech_stack",
        "kotlin": "new_tech_stack",
        # 平台
        "超星": "new_platform",
        "智慧树": "new_platform",
        "mooc": "new_platform",
        "微信": "new_platform",
        "飞书": "new_platform",
        # 业务领域
        "刷课": "new_domain",
        "答题": "new_domain",
        "网课": "new_domain",
        "自动化": "new_domain",
    }

    def check_novelty(self, intent: IntentResult) -> NoveltyCheck:
        """
        CR-006 前序步骤：检测是否进入新领域。

        满足任一信号即触发：
        - 新项目类型
        - 新技术栈
        - 新平台
        - 新框架
        - 新工具链
        - 新业务领域

        Returns:
            NoveltyCheck: 包含是否为新领域及原因
        """
        text_lower = intent.user_input.lower()
        signals = []
        reasons = []

        for keyword, signal_type in self._NOVELTY_SIGNALS.items():
            if keyword in text_lower:
                if signal_type not in signals:
                    signals.append(signal_type)
                reasons.append(f"关键词 '{keyword}' 触发 {signal_type}")

        # 意图低置信度也可能意味着新领域
        if intent.confidence < 0.5 and not signals:
            signals.append("low_confidence")
            reasons.append("意图分类置信度低，可能为不熟悉领域")

        return NoveltyCheck(
            is_new_domain=len(signals) > 0,
            reasons=reasons,
            signals=signals,
            suggested_keywords=intent.keywords,
        )

    # ── CR-006: Search Before Design ────

    def search_before_design(self,
                             intent: IntentResult,
                             novelty: NoveltyCheck) -> NoveltyCheck:
        """
        CR-006: Search Before Design

        进入新领域时，必须先搜索外部成熟方案，再从已有方案中提取模式。
        禁止从零推导设计。

        执行流程：
            识别新领域信号
            ↓
            搜索外部成熟方案（WebSearch / GreasyFork / GitHub）
            ↓
            分析 2~3 个参考实现
            ↓
            提取共性模式
            ↓
            形成设计方案

        失败路径：
            未找到成熟方案 → 明确标记为 "推导设计，风险较高"

        Args:
            intent: CR-001 输出
            novelty: check_novelty() 输出

        Returns:
            NoveltyCheck: 更新后的新领域检测结果（含外部搜索结果）
        """
        if not novelty.is_new_domain:
            return novelty

        # 构建搜索建议
        search_hints = []

        # 项目类型 → 搜索平台
        if "new_project_type" in novelty.signals:
            search_hints.append("GreasyFork (如果涉及浏览器脚本)")
            search_hints.append("GitHub 搜索相关项目名")

        # 技术栈 → 官方文档 + 最佳实践
        if "new_tech_stack" in novelty.signals:
            search_hints.append("官方文档")
            search_hints.append("awesome-<tech> 仓库")

        # 新平台 → 开发者文档 + 社区
        if "new_platform" in novelty.signals:
            search_hints.append("平台 API 文档")
            search_hints.append("平台相关开源项目")

        # 新业务领域 → 搜索已有工具
        if "new_domain" in novelty.signals:
            search_hints.append("搜索同领域成熟工具/脚本")
            search_hints.append("GreasyFork/GitHub 按功能关键词搜索")

        # 更新建议关键词
        novelty.suggested_keywords = intent.keywords + [
            "开源", "脚本", "插件", "github", "greasyfork"
        ]

        return novelty

    def register_search_outcome(self,
                                 novelty: NoveltyCheck,
                                 found: bool,
                                 count: int = 0,
                                 patterns: list[str] = []) -> NoveltyCheck:
        """记录外部搜索结果到 NoveltyCheck。"""
        novelty.external_refs_found = found
        novelty.external_refs_count = count
        novelty.external_patterns = patterns
        return novelty

    # ── CR-007: Pattern Registration ────

    def register_pattern(self,
                         pattern_name: str,
                         source: str,
                         validated: bool = False) -> AccumulateAction:
        """
        CR-007: Pattern Registration

        将外部学到的有效模式沉淀回 Harness。

        闭环：
            外部模式
            ↓
            验证有效
            ↓
            写入 Lessons / REFERENCE_SCRIPTS.md
            ↓
            必要时升级为 Rule

        Args:
            pattern_name: 模式名称
            source: 来源（如 "GreasyFork/超星学习通小助手"）
            validated: 是否已在实际使用中验证

        Returns:
            AccumulateAction: 建议的写入操作
        """
        priority = "high" if validated else "normal"
        return AccumulateAction(
            action_type="pattern",
            title=f"External Pattern: {pattern_name}",
            content=(
                f"来源: {source}\n"
                f"已验证: {'是' if validated else '否（待实战验证）'}\n"
                f"建议写入: memory/ 或 registry/CORRECTIONS.md Lessons 区"
            ),
            target_file="memory/",
            priority=priority,
        )

    # ── CR-005: 经验沉淀 ────────────────

    def accumulate_experience(self,
                              intent: IntentResult,
                              pattern: PatternResult,
                              outcome: str = "",
                              surprises: list[str] = []) -> list[AccumulateAction]:
        """
        CR-005: Experience Accumulation

        执行结束后判断是否需要沉淀新经验/规则/模式。

        Args:
            intent: 原始意图
            pattern: 模式匹配结果
            outcome: 执行结果描述
            surprises: 意外发现列表

        Returns:
            list[AccumulateAction]: 建议的写入操作
        """
        actions = []

        # 新模式 → 注册
        if pattern.should_register and pattern.match == PatternMatch.NEW:
            actions.append(AccumulateAction(
                action_type="pattern",
                title=f"New Pattern: {intent.task_type or intent.intent.value}",
                content=f"Intent={intent.intent.value}, Domain={intent.domain.value}, Outcome={outcome}",
                target_file="workflow_engine/cognitive_router.py → known_patterns",
                priority="high",
            ))

        # 有意外 → 写教训
        if surprises:
            for s in surprises:
                actions.append(AccumulateAction(
                    action_type="lesson",
                    title=s[:60],
                    content=s,
                    target_file="registry/CORRECTIONS.md",
                    priority="high",
                ))

        # 低置信度任务 → 记录
        if intent.confidence < 0.5:
            actions.append(AccumulateAction(
                action_type="memory",
                title=f"Low Confidence Intent: {intent.user_input[:50]}",
                content=f"User input generated low confidence ({intent.confidence:.0%}). "
                        f"Consider adding more intent signals.",
                target_file="memory/",
                priority="low",
            ))

        return actions

    # ── 主流程 ─────────────────────────

    def process(self,
                user_input: str,
                outcome: str = "",
                surprises: list[str] = [],
                external_refs: list[str] = []) -> CognitiveResult:
        """
        完整认知路由流程：CR-001 → CR-006 → CR-002 → CR-003 → CR-004 → CR-005/CR-007

        CR-006 插入在意图识别之后、知识检索之前：
        新领域 → 必须先搜索外部参考，再做内部检索和模式匹配。

        Args:
            user_input: 用户原始输入
            outcome: 执行结果（回填时使用）
            surprises: 意外发现（回填时使用）
            external_refs: 已找到的外部参考列表（Agent 回填）

        Returns:
            CognitiveResult: 完整认知路由结果
        """
        intent = self.analyze_intent(user_input)         # CR-001
        novelty = self.check_novelty(intent)              # 新领域检测
        novelty = self.search_before_design(intent, novelty)  # CR-006
        query = self.translate_query(intent)              # CR-002
        knowledge = self.search_knowledge(query)          # CR-003
        pattern = self.match_pattern(intent, knowledge)   # CR-004

        # 如果 Agent 已经搜索了外部参考，记录结果
        if external_refs:
            novelty = self.register_search_outcome(
                novelty, found=True,
                count=len(external_refs),
                patterns=external_refs,
            )

        actions = self.accumulate_experience(intent, pattern, outcome, surprises)  # CR-005

        # CR-007: 新领域且有外部参考 → 建议沉淀
        if novelty.is_new_domain and novelty.external_refs_found:
            for p in novelty.external_patterns:
                actions.append(self.register_pattern(
                    pattern_name=p,
                    source=f"外部参考 ({novelty.signals[0]})",
                    validated=bool(outcome and outcome.startswith('success')),
                ))

        return CognitiveResult(
            intent=intent,
            query=query,
            knowledge=knowledge,
            pattern=pattern,
            novelty=novelty,
            accumulate_actions=actions,
        )


# ── 便捷函数 ──────────────────────────────

_default_router = CognitiveRouter()


def route_intent(user_input: str) -> CognitiveResult:
    """便捷函数：完整认知路由。"""
    return _default_router.process(user_input)


def quick_classify(user_input: str) -> str:
    """便捷函数：快速分类，返回单行摘要。"""
    result = _default_router.process(user_input)
    return result.summary()


# ── 自测 ──────────────────────────────────

if __name__ == "__main__":
    cr = CognitiveRouter()

    test_cases = [
        ("帮我调试登录功能", TaskIntent.DEBUG, TaskDomain.BACKEND, False),
        ("帮我让CC学习一个PPT模板", TaskIntent.FEATURE, TaskDomain.AI_AGENT, False),
        ("重构一下用户认证模块", TaskIntent.REFACTOR, TaskDomain.SECURITY, False),
        ("看看数据库里有什么", TaskIntent.EXPLORE, TaskDomain.DATABASE, False),
        ("给这个接口写测试", TaskIntent.TEST, TaskDomain.BACKEND, False),
        ("部署到生产环境", TaskIntent.SETUP, TaskDomain.DEVOPS, False),
        ("莫名其妙的东西", TaskIntent.UNKNOWN, TaskDomain.GENERAL, False),
        # CR-006 测试：新领域（意图可能 UNKNOWN，但应触发新领域检测）
        ("帮我写一个超星刷课答题的油猴脚本", TaskIntent.FEATURE, TaskDomain.GENERAL, True),
        ("帮我做一个浏览器插件自动答题", TaskIntent.FEATURE, TaskDomain.GENERAL, True),
    ]

    errors = 0
    for user_input, expected_intent, expected_domain, expect_novelty in test_cases:
        result = cr.process(user_input)
        intent_ok = result.intent.intent == expected_intent
        domain_ok = result.intent.domain == expected_domain
        novelty_ok = result.novelty.is_new_domain == expect_novelty
        status = "PASS" if (intent_ok and domain_ok and novelty_ok) else "FAIL"
        if status == "FAIL":
            errors += 1

        print(f"[{status}] \"{user_input}\"")
        print(f"       → intent={result.intent.intent.value} (want {expected_intent.value})"
              f" | domain={result.intent.domain.value} (want {expected_domain.value})")
        if result.novelty.is_new_domain:
            print(f"       → [NEW DOMAIN] signals={result.novelty.signals}")
        print(f"       → pattern={result.pattern.match.value}"
              f" | lane={result.pattern.recommended_lane}"
              f" | actions={len(result.accumulate_actions)}")
        print()

    # 测试 YAML 输出
    result = cr.process("帮我让CC学习一个PPT模板")
    print("─ YAML Output ─")
    print(result.intent.to_yaml())
    print()

    # 测试便捷函数
    summary = quick_classify("修复登录bug")
    print(f"Quick classify: {summary}")

    if errors == 0:
        print(f"\n[OK] All {len(test_cases)} tests passed!")
    else:
        print(f"\n[FAIL] {errors}/{len(test_cases)} tests failed")
