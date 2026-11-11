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
```

### 快速开始

```bash
# 1. 建库（用自带示例种子）
python scripts/init_db.py --db novel.db --seed references/seed-honglou.json

# 2. 动笔前：查黛玉写到 Ch10 已知什么
python scripts/query.py --db novel.db knowledge 林黛玉 --chapter 10

# 3. 写完 Ch11 一幕，抓入数据库
python scripts/capture.py --db novel.db --file references/example_scene_ch11.json

# 4. 审计
python scripts/audit.py --db novel.db

# 5. 出看板
python scripts/report.py --db novel.db --out 看板.md
```

## 目录结构

```
db-novel-writer/
├── SKILL.md                      # 技能入口（WorkBuddy/OpenClaw 读取）
├── README.md                     # 本文件
├── LICENSE                       # MIT
├── .gitignore
├── scripts/
│   ├── schema.sql                # 11 张表 DDL
│   ├── init_db.py                # 建库 + 种子导入 / 从现有 md best-effort 导入
│   ├── capture.py                # 场景抽取 JSON → 入库（幂等）
│   ├── query.py                  # knowledge/prop/timeline/foreshadowing/scene/who
│   ├── audit.py                  # 5 项一致性检查
│   └── report.py                 # 生成 markdown 看板
└── references/
    ├── methodology.md            # RPG 隐喻、四感知模型、读者信息差、完整工作流
    ├── schema.md                 # 字段速查 + SQL 示例
    ├── seed-honglou.json         # 示例种子：《红楼：硬件鬼才林黛玉》真实设定（截至 Ch10）
    └── example_scene_ch11.json   # 场景抓取 JSON 样例
```

## 数据模型（要点）

11 张表：`characters` / `locations` / `chapters` / `scenes` / `perceptions` /
`props` / `prop_transfers` / `events` / `foreshadowing` / `timeline` / `consistency_issues`。

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

## 边界

- **不代写正文**：本 skill 负责"状态管理 + 一致性保障"，prose 由你完成。
- **不修改既有正文**：对已完成章节只做追踪/审计，新内容走数据库后续章节。
- 种子数据（`seed-honglou.json`）是《红楼：硬件鬼才林黛玉》的**脱敏示例**，仅用于演示；换成你自己的小说，只需提供对应的种子 JSON。

## License

MIT — 详见 [LICENSE](LICENSE)。
