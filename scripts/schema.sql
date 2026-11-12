-- ============================================================
-- db-novel-writer : SQLite 小说状态库 Schema
-- 设计理念: 把长篇小说当成一款策略 RPG 的"游戏状态"
-- 每一个角色、场景、道具、事件、伏笔都是可被查询/校验的实体
-- 角色的 所见/所闻/所感/所想 以 perceptions 表逐条落库
-- ============================================================

-- 角色 -----------------------------------------------------
CREATE TABLE characters (
    id            INTEGER PRIMARY KEY,
    name          TEXT UNIQUE NOT NULL,   -- 林黛玉
    alias         TEXT,                    -- 黛玉 / 颦儿
    role          TEXT,                    -- 主角/反派/关键/配角/已故
    status        TEXT,                    -- 在逃/通缉/停职/失踪/正常/已故
    location_id   INTEGER,                -- 当前位置(外键)
    first_appearance TEXT,                 -- Ch1
    skills_note   TEXT,                    -- 技能简述
    blind_spots   TEXT,                    -- 技术盲点
    bio           TEXT,
    FOREIGN KEY(location_id) REFERENCES locations(id)
);

-- 地点(支持嵌套: 楼 -> 机房 -> 机柜) -----------------------
CREATE TABLE locations (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    type          TEXT,                    -- building/room/outdoor/vehicle
    parent_id     INTEGER,                 -- 父地点
    note          TEXT,
    FOREIGN KEY(parent_id) REFERENCES locations(id)
);

-- 章节 -----------------------------------------------------
CREATE TABLE chapters (
    id            INTEGER PRIMARY KEY,
    num           INTEGER UNIQUE NOT NULL, -- 1..N
    title         TEXT,
    status        TEXT,                    -- outline/draft/review/done
    pov_character_id INTEGER,
    summary       TEXT,
    FOREIGN KEY(pov_character_id) REFERENCES characters(id)
);

-- 场景(章节内的一个时空切片) -------------------------------
CREATE TABLE scenes (
    id            INTEGER PRIMARY KEY,
    chapter_id    INTEGER NOT NULL,
    seq           INTEGER NOT NULL,        -- 章节内序号
    location_id   INTEGER,
    time_start    TEXT,                    -- 绝对: 2017-07-24 00:03 / 相对: T+0
    time_end      TEXT,
    pov_character_id INTEGER,
    summary       TEXT,
    FOREIGN KEY(chapter_id) REFERENCES chapters(id),
    FOREIGN KEY(location_id) REFERENCES locations(id),
    FOREIGN KEY(pov_character_id) REFERENCES characters(id)
);

-- 感知: 所见 / 所闻 / 所感 / 所想 (核心表) ----------------
-- ptype: SEE 见 / HEAR 闻 / FEEL 感(情绪/身体) / THINK 想(判断/推断)
--        KNOW 已知事实 / SAY 言 / DO 行
CREATE TABLE perceptions (
    id            INTEGER PRIMARY KEY,
    scene_id      INTEGER NOT NULL,
    character_id  INTEGER NOT NULL,        -- 谁在感知
    ptype         TEXT NOT NULL,
    content       TEXT NOT NULL,
    target_type   TEXT,                    -- character/prop/event/location/other
    target_id     INTEGER,                 -- 指向的实体 id
    confidence    TEXT,                    -- fact/inferred/unknown
    source_note   TEXT,
    FOREIGN KEY(scene_id) REFERENCES scenes(id),
    FOREIGN KEY(character_id) REFERENCES characters(id)
);

-- 道具(含物证/电子证据/文档/随身/监控) --------------------
CREATE TABLE props (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    category      TEXT,
    description   TEXT,
    holder_id     INTEGER,                 -- 当前持有者
    location_id   INTEGER,                 -- 当前位置
    status        TEXT,                    -- 在手中/已销毁/已解密/待提取/已移交
    first_appearance TEXT,
    specs         TEXT,                    -- 技术规格(JSON 字符串)
    note          TEXT,
    FOREIGN KEY(holder_id) REFERENCES characters(id),
    FOREIGN KEY(location_id) REFERENCES locations(id)
);

-- 道具流转(每一次易手都留痕) -----------------------------
CREATE TABLE prop_transfers (
    id            INTEGER PRIMARY KEY,
    prop_id       INTEGER NOT NULL,
    from_char_id  INTEGER,
    to_char_id    INTEGER,
    scene_id      INTEGER,
    chapter_id    INTEGER,
    method        TEXT,
    note          TEXT,
    FOREIGN KEY(prop_id) REFERENCES props(id),
    FOREIGN KEY(from_char_id) REFERENCES characters(id),
    FOREIGN KEY(to_char_id) REFERENCES characters(id),
    FOREIGN KEY(scene_id) REFERENCES scenes(id),
    FOREIGN KEY(chapter_id) REFERENCES chapters(id)
);

-- 事件 -----------------------------------------------------
CREATE TABLE events (
    id            INTEGER PRIMARY KEY,
    chapter_id    INTEGER,
    scene_id      INTEGER,
    time          TEXT,
    type          TEXT,                    -- 拆解/烧机/登录/通话/转账/鉴定...
    description   TEXT,
    involved      TEXT,                    -- JSON 数组: 涉及角色 id/name
    consequence   TEXT,
    FOREIGN KEY(chapter_id) REFERENCES chapters(id),
    FOREIGN KEY(scene_id) REFERENCES scenes(id)
);

-- 伏笔(埋设 / 回收追踪) -----------------------------------
CREATE TABLE foreshadowing (
    id            INTEGER PRIMARY KEY,
    code          TEXT UNIQUE NOT NULL,    -- V01..V22
    title         TEXT,
    planted_chapter TEXT,                  -- Ch1
    planted_scene_id INTEGER,
    payoff_chapter  TEXT,                  -- 可为空(未回收)
    status        TEXT,                    -- planted/active/paid_off/dropped
    description   TEXT,
    note          TEXT,
    FOREIGN KEY(planted_scene_id) REFERENCES scenes(id)
);

-- 时间线(绝对/相对时间锚点) -------------------------------
CREATE TABLE timeline (
    id            INTEGER PRIMARY KEY,
    datetime      TEXT,                    -- ISO: 2017-07-24T00:03
    chapter_id    INTEGER,
    scene_id      INTEGER,
    event_summary TEXT,
    kind          TEXT,                    -- absolute/relative
    anchor_note   TEXT,
    FOREIGN KEY(chapter_id) REFERENCES chapters(id),
    FOREIGN KEY(scene_id) REFERENCES scenes(id)
);

-- 一致性问题(审计结果落库) -------------------------------
CREATE TABLE consistency_issues (
    id            INTEGER PRIMARY KEY,
    check_type    TEXT,
    severity      TEXT,                    -- error/warn/info
    detail        TEXT,
    detected_at   TEXT,
    resolved      INTEGER DEFAULT 0
);

-- 常用索引 ------------------------------------------------
CREATE INDEX idx_perc_char ON perceptions(character_id);
CREATE INDEX idx_perc_scene ON perceptions(scene_id);
CREATE INDEX idx_scene_chap ON scenes(chapter_id);
CREATE INDEX idx_tl_dt ON timeline(datetime);
CREATE INDEX idx_fs_code ON foreshadowing(code);

-- ============================================================
-- 文学性管理(降AI味 / 修辞轮换) -- 第二真相源
-- 把"怎么写更有人味"也格式化为可查询、可校验的数据
-- ============================================================

-- 修辞手法图谱: 每种手法的形式 / 标记词 / 轮换规则 / 密度上限 ----
CREATE TABLE rhetoric_catalog (
    id            INTEGER PRIMARY KEY,
    type          TEXT UNIQUE NOT NULL,   -- 明喻/暗喻/拟人/排比/通感/夸张/反问/对偶/反复/借代/反语/移就
    format_desc   TEXT,                    -- 该手法的形式定义
    connectors    TEXT,                    -- JSON 数组: 典型标记词(如 明喻的 像/如/如同)
    example       TEXT,                    -- 示例
    rotation_rule TEXT,                    -- 同手法内用词轮换规则
    density_limit REAL                     -- 每千字建议上限(超则告警); 0/NULL=不限制
);

-- AI 味写法谱系: 训练语料偏好的组合/句式/标点 -------------------
CREATE TABLE ai_flavor_catalog (
    id            INTEGER PRIMARY KEY,
    code          TEXT UNIQUE NOT NULL,    -- af-cold-ice ...
    category      TEXT,                    -- 冷感比喻簇/目光比喻簇/停顿填充/否定替换句式...
    severity      TEXT,                    -- warn/info
    match_type    TEXT,                    -- substring/regex
    match         TEXT,                    -- 匹配串或正则
    replacements  TEXT,                    -- JSON 数组: 轮换替换候选(仅 substring + auto_fix=1 时用于 --fix)
    auto_fix      INTEGER DEFAULT 0,       -- 1=允许自动替换, 0=仅告警(需语境判断)
    rationale     TEXT                     -- 为何属 AI 味(语料证据)
);

-- 文学性风格阈值(可逐项目覆盖) -------------------------------
CREATE TABLE style_thresholds (
    id            INTEGER PRIMARY KEY,
    name          TEXT UNIQUE NOT NULL,    -- dash_per_1k / simile_per_1k / consecutive_short_sent ...
    value         REAL NOT NULL,
    unit          TEXT,
    note          TEXT
);

-- 文学性审计结果(落库) ---------------------------------------
CREATE TABLE style_audit_issues (
    id            INTEGER PRIMARY KEY,
    chapter_id    INTEGER,
    issue_type    TEXT,                    -- ai_flavor/rhetoric/dash/short_sentence
    category      TEXT,
    severity      TEXT,                    -- warn/info
    line_no       INTEGER,
    detail        TEXT,
    suggestion    TEXT,
    detected_at   TEXT,
    resolved      INTEGER DEFAULT 0,
    FOREIGN KEY(chapter_id) REFERENCES chapters(id)
);

-- 修辞手法实际使用统计(每章每类计数) -------------------------
CREATE TABLE rhetoric_usage (
    id            INTEGER PRIMARY KEY,
    chapter_id    INTEGER NOT NULL,
    device_type   TEXT NOT NULL,
    count         INTEGER NOT NULL,
    density       REAL,                    -- count per 1k chars
    FOREIGN KEY(chapter_id) REFERENCES chapters(id)
);

-- 写作手法图谱: 不止修辞 —— 把"怎么把人和事讲明白"也格式化为数据 -----
-- 涵盖 遣词造句 / 引经据典 / 细节填充 / 展示不告知 / 对话 / 视角RPG / 节奏 / 钩子 / 环境烘托 / 伏笔
-- detectors 为可机检的反模式标记(JSON 数组); 空=人工核查项
CREATE TABLE writing_techniques (
    id            INTEGER PRIMARY KEY,
    code          TEXT UNIQUE NOT NULL,    -- wt-show-dont-tell ...
    category      TEXT,                    -- 展示不告知/遣词造句/引经据典/细节填充/对话/视角RPG/节奏/钩子/环境烘托/伏笔
    name          TEXT NOT NULL,
    summary       TEXT,                    -- 说明
    when_use      TEXT,                    -- 何时用
    anti_pattern  TEXT,                    -- 反模式(AI 倾向)
    example       TEXT,                    -- 示例
    rotation      TEXT,                    -- 轮换/备选写法
    detectors     TEXT                     -- JSON 数组: [{match_type, match}] 可机检项; 空=人工核查
);

-- 文学性索引 ------------------------------------------------
CREATE INDEX idx_af_code ON ai_flavor_catalog(code);
CREATE INDEX idx_sai_chap ON style_audit_issues(chapter_id);
CREATE INDEX idx_ru_chap ON rhetoric_usage(chapter_id);
CREATE INDEX idx_wt_code ON writing_techniques(code);
