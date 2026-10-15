-- Harness Engineer — 持久化层建表语句
-- Postgres 16+

-- 1. 会话记录
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id VARCHAR(255) NOT NULL,
    execution_lane INT NOT NULL DEFAULT 2,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    current_story_id VARCHAR(64),
    current_phase VARCHAR(32),
    metadata JSONB DEFAULT '{}',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id, updated_at DESC);

-- 2. 故事执行状态
CREATE TABLE IF NOT EXISTS stories (
    id SERIAL PRIMARY KEY,
    project_id VARCHAR(255) NOT NULL,
    prd_key VARCHAR(64) NOT NULL,
    title VARCHAR(512),
    status VARCHAR(32) DEFAULT 'pending',
    failed_reason TEXT,
    assigned_agent VARCHAR(64),
    plan_path VARCHAR(512),
    report_path VARCHAR(512),
    retry_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_stories_project ON stories(project_id, status);

-- 3. 纠错注册表（append-only）
CREATE TABLE IF NOT EXISTS corrections (
    id SERIAL PRIMARY KEY,
    project_id VARCHAR(255) NOT NULL,
    type VARCHAR(32) NOT NULL,           -- pitfall | constraint
    code VARCHAR(16) NOT NULL UNIQUE,
    title VARCHAR(255),
    description TEXT NOT NULL,
    fix_approach TEXT,
    scope VARCHAR(32) DEFAULT 'project',
    occurred_at TIMESTAMPTZ DEFAULT now()
);

-- 4. 项目约束规则
CREATE TABLE IF NOT EXISTS constraints (
    id SERIAL PRIMARY KEY,
    project_id VARCHAR(255) NOT NULL,
    category VARCHAR(64),
    rule_text TEXT NOT NULL,
    is_hard BOOLEAN DEFAULT true,
    source VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 5. 门禁执行结果
CREATE TABLE IF NOT EXISTS gate_results (
    id SERIAL PRIMARY KEY,
    session_id UUID REFERENCES sessions(id),
    story_id INT REFERENCES stories(id),
    gate_name VARCHAR(64) NOT NULL,
    result VARCHAR(16) NOT NULL,         -- pass | fail
    output_summary TEXT,
    baseline_delta INT DEFAULT 0,
    executed_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_gate_results_session ON gate_results(session_id);
