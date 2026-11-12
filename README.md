# db-novel-writer

> 以数据库为中心的小说创作辅助 skill——把长篇当作策略 RPG 的游戏状态库来写。

## 它解决什么问题

写长篇（尤其悬疑/科幻/群像）最痛的是**前后不一致**：同一个角色在同一时间出现在两地、道具持有者前后矛盾、埋了三年的伏笔忘了收、角色突然"知道"了他本不该知道的事。

`db-novel-writer` 用 **SQLite 作为单一事实源（SSOT）**，把每个角色在**每个场景**里的原子感知入库：

| 字段 | 含义 |
|------|------|
| `SEE` 见 | 角色看到了什么 |
| `HEAR` 闻 | 听到了什么 |
| `FEEL` 感 | 身体/情绪感受 |
| `THINK` 想 | 推断、内心活动 |
| `KNOW` 已知 | 角色当前已知事实（**读者信息差的关键**） |
| `SAY` 言 | 说出口的话 |
| `DO` 行 | 采取的动作 |

散文只是"渲染层"——数据库才是一切查询与审计的依据。

## 安装

本 skill 兼容 WorkBuddy / OpenClaw 的技能目录结构，直接放入技能目录即可：

```bash
# WorkBuddy（用户级）
cp -r db-novel-writer ~/.workbuddy/skills/

# 或 OpenClaw
cp -r db-novel-writer ~/.qclaw/skills/
```

脚本仅依赖 Python 3 标准库（`sqlite3` / `json` / `argparse`），**无第三方依赖**。

## 工作流

```
1. init    建库 + 可选 --seed 导入策展种子（角色/地点/章节/伏笔/时间线）
2. query   动笔前查：某角色到某章为止已知什么、在哪、时间线如何
3. write   写正文（ prose 仍由你/模型完成，本 skill 不代写）
4. capture 写完一幕，把感知/事件/道具流转/时间线填 JSON 入库（幂等）
5. audit   一致性审计：同场景双地 / 持有者冲突 / 伏笔未回收 / 感知悬空 / 时间线乱序
6. report  生成 markdown 一致性看板，给作者/编辑审阅
7. literary 文学性审查（降 AI 味 / 修辞轮换）：初稿完成后扫描 AI 味写法、统计修辞密度、落库待修
```

### 快速开始

```bash
# 1. 建库（一致性种子 + 文学性种子）
python scripts/init_db.py --db novel.db --seed references/seed-honglou.json --seed-literary

# 2. 动笔前：查黛玉写到 Ch10 已知什么
python scripts/query.py --db novel.db knowledge 林黛玉 --chapter 10

# 3. 写完 Ch11 一幕，抓入数据库
python scripts/capture.py --db novel.db --file references/example_scene_ch11.json

# 4. 一致性审计 + 看板
python scripts/audit.py --db novel.db
python scripts/report.py --db novel.db --out 看板.md

# 5. 初稿完成后：文学性体检
python scripts/literary_audit.py report --db novel.db --text-file 第011章.md --out 文学性审计.md --chapter 11
#    或先扫描 AI 味并一键去味
python scripts/literary_audit.py ai-flavor --db novel.db --text-file draft.md --fix --out draft.clean.md
```

## 目录结构

```
db-novel-writer/
├── SKILL.md                      # 技能入口（WorkBuddy/OpenClaw 读取）
├── README.md                     # 本文件
├── LICENSE                       # MIT
├── .gitignore
├── scripts/
│   ├── schema.sql                # 16 张表 DDL（11 一致性 + 5 文学性）
│   ├── init_db.py                # 建库 + 种子导入 / 文学性种子 / 从现有 md best-effort 导入
│   ├── capture.py                # 场景抽取 JSON → 入库（幂等）
│   ├── query.py                  # knowledge/prop/timeline/foreshadowing/scene/who
│   ├── audit.py                  # 5 项一致性检查
│   ├── report.py                 # 生成 markdown 一致性看板
│   └── literary_audit.py        # 文学性审查：ai-flavor / rhetoric / report 三个子命令
└── references/
    ├── methodology.md            # RPG 隐喻、四感知模型、读者信息差、完整工作流、文学性管理理念
    ├── schema.md                 # 字段速查 + SQL 示例
    ├── seed-honglou.json         # 示例种子：《红楼：硬件鬼才林黛玉》真实设定（截至 Ch10）
    ├── example_scene_ch11.json   # 场景抓取 JSON 样例
    ├── rhetoric-catalog.json     # 修辞手法图谱（通用，可复用）
    ├── ai-flavor-catalog.json    # AI 味写法谱系（通用，可复用）
    └── style-thresholds.json     # 风格阈值默认值（可逐项目覆盖）
```

## 数据模型（要点）

16 张表：11 张一致性表（`characters` / `locations` / `chapters` / `scenes` / `perceptions` /
`props` / `prop_transfers` / `events` / `foreshadowing` / `timeline` / `consistency_issues`）
+ 5 张文学性表（`rhetoric_catalog` / `ai_flavor_catalog` / `style_thresholds` /
`style_audit_issues` / `rhetoric_usage`）。

`perceptions` 是核心：

```sql
CREATE TABLE perceptions (
  id INTEGER PRIMARY KEY,
  scene_id INTEGER NOT NULL,
  character_id INTEGER NOT NULL,
  ptype TEXT NOT NULL,          -- SEE/HEAR/FEEL/THINK/KNOW/SAY/DO
  content TEXT NOT NULL,
  target_type TEXT, target_id INTEGER,
  confidence TEXT,              -- fact / inferred / rumor
  source_note TEXT,
  FOREIGN KEY(scene_id) REFERENCES scenes(id),
  FOREIGN KEY(character_id) REFERENCES characters(id)
);
```

## 文学性管理（降 AI 味 / 修辞轮换）

一致性只是"不写错"，文学性是"写得像人写的"。本 skill 把后者也**格式化为可查询、可校验的数据**：

- **修辞手法图谱 `rhetoric_catalog`**：每种手法（明喻/暗喻/拟人/排比/通感/夸张/反问/对偶/反复/借代/反语/移就）记录其**形式、标记词、轮换规则、密度上限**。`literary_audit.py rhetoric` 据此统计实际密度，超上限或同词近距离重复时给出轮换建议——回答"每种格式用哪些词、这些词该怎么轮换"。
- **AI 味写法谱系 `ai_flavor_catalog`**：先调查哪些**文字组合 / 写作方式 / 标点符号**是 AI 训练语料的统计偏好（冷感比喻簇、目光比喻簇、停顿填充、否定替换句式、概念-说明句式、程度副词堆砌、情绪标签直给……），把证据记进库；初稿完成后用 `literary_audit.py ai-flavor` 审查，**以查找替换的方式把 AI 味写法改成更有人味的样式**（`--fix` 按命中次序轮换替换，结果需人工通读）。
- **风格阈值 `style_thresholds`**：破折号每千字上限、明喻密度、连续短句数等——可逐项目覆盖（如《红楼》破折号 ≤7/千字），不写死在代码里。
- **结果落库**：审计结果写入 `style_audit_issues`，修辞计数写入 `rhetoric_usage`，可像一致性问题一样持续追踪。

三份文学性参考 JSON（`rhetoric-catalog.json` / `ai-flavor-catalog.json` / `style-thresholds.json`）是**通用数据**，换项目无需改动，只调 `style_thresholds` 即可。

```bash
# 一键去味：把 AI 味写法轮换替换为更有人味的样式
python scripts/literary_audit.py ai-flavor --db novel.db --text-file draft.md --fix --out draft.clean.md

# 综合文学性报告
python scripts/literary_audit.py report --db novel.db --text-file 第011章.md --out 文学性审计.md --chapter 11
```

## 边界

- **不代写正文**：本 skill 负责"状态管理 + 一致性保障 + 文学性体检"，prose 由你完成。
- **不修改既有正文**：对已完成章节只做追踪/审计，新内容走数据库后续章节；`--fix` 只输出去味稿，**不回写原文件**。
- 种子数据（`seed-honglou.json`）是《红楼：硬件鬼才林黛玉》的**脱敏示例**，仅用于演示；换成你自己的小说，只需提供对应的种子 JSON。

## License

MIT — 详见 [LICENSE](LICENSE)。
