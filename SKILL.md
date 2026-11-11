---
name: db-novel-writer
description: "Database-centered novel writing assistant for long fiction needing strict consistency of characters, timeline, locations, props, and foreshadowing. Models each character's 所见/所闻/所感/所想 per scene in SQLite, tracks prop transitions and foreshadowing payoffs, runs consistency audits. Built for 《红楼：硬件鬼才林黛玉》 but reusable. Trigger: 数据库写小说 / 一致性检查 / 伏笔追踪 / 角色已知状态."
agent_created: true
---

# Db Novel Writer — 以数据库为中心的小说创作

## Overview

把长篇小说当成一款策略 RPG 的"游戏状态":用 SQLite 把角色、场景、四感知、
道具流转、事件、伏笔、时间线全部建为可查询、可校验的实体。数据库是**单一真相源**,
正文只是它的渲染层。写新场景前先查库,写完后把场景实体抽进库,定期跑审计把前后文矛盾
变成可定位的工单。

本 skill 不代写正文、不代构大纲——它专治"写到第三卷人物时间地点道具对不上"的顽疾。
大纲构思(避开俗套/单问交互)由 `plan-fiction` 类 skill 负责,两者互补。

## When to use

- 动笔写新章/新场景前,需要确认"某角色此刻知道什么、某道具现在在谁手里"
- 写完一章后,把该章的感知/事件/道具流转落库,防止记忆漂移
- 定期审计:查同角色同地冲突、道具双持有、伏笔长期未回收、感知悬空引用
- 项目已有 `03-核心道具与线索/伏笔与回收追踪.md` 等文档,本 skill 提供其机器可查询镜像

## Workflow

### 1. 初始化(一次)
```bash
python scripts/init_db.py --db .novel-db/novel.db \
    --seed references/seed-honglou.json
```
- `--seed`:灌入策展种子(本项目已备 `seed-honglou.json`,对齐 V01–V22/时间线/道具/人物)
- 也可用 `--project "D:/Claw/IntellectualProperties/红楼悬疑"` 从现有 md best-effort 导入占位
- schema 从 `scripts/schema.sql` 读取

### 2. 动笔前:查状态(避免写飞)
```bash
python scripts/query.py --db .novel-db/novel.db knowledge 林黛玉 --chapter 10
python scripts/query.py --db .novel-db/novel.db prop 幽灵芯片PM-7721
python scripts/query.py --db .novel-db/novel.db foreshadowing --status active
python scripts/query.py --db .novel-db/novel.db who 贾宝玉
```
- `knowledge 角色名 [--chapter N]`:该角色截至某章的全部 见/闻/感/想/知
- `prop 道具名`:当前持有/位置/状态 + 流转史
- `timeline [--chapter N]` / `foreshadowing [--status]` / `scene 章号 seq` / `who 角色名`

### 3. 写作
正文照常写。本 skill 不介入创作。

### 4. 写完后:抽场景实体入库
把该场景的感知/事件/道具流转抽成 JSON(格式见 `capture.py` 顶部 docstring),执行:
```bash
python scripts/capture.py --db .novel-db/novel.db --file scene_ch11_01.json
```
- 自动建/更新 chapter 与 scene(按 chapter_num+seq 幂等)
- 自动按 name 解析 角色/道具/地点 外键;缺失实体自动建占位并告警
- `prop_transfers` 会自动同步 `props.holder_id` 与状态

### 5. 定期审计 + 看板
```bash
python scripts/audit.py --db .novel-db/novel.db
python scripts/report.py --db .novel-db/novel.db --out .novel-db/report.md
```
- `audit.py`:检查 char_location(同刻异地)/prop_holder(持有与流转落点矛盾)/
  foreshadowing_open(未回收)/perception_dangling(悬空引用)/timeline_order,写入 `consistency_issues`
- `report.py`:生成 markdown 一致性看板(角色状态/道具/伏笔/时间线/问题)

## Perception 模型(perceptions 表)

| ptype | 含义 | 用途 |
|-------|------|------|
| SEE   | 见   | 客观看到的事实 |
| HEAR  | 闻   | 听到的话/声音 |
| FEEL  | 感   | 情绪/身体感受 |
| THINK | 想   | 角色判断/推断(可能错,带 confidence=inferred) |
| KNOW  | 已知 | 角色此刻已掌握的事实——信息差核心 |
| SAY   | 言   | 说出口的话 |
| DO    | 行   | 动作 |

每条可带 `target_type/target_id`(指向角色/道具)与 `confidence`(fact/inferred/unknown)。

## 与项目文档的关系

《红楼》已有 `伏笔与回收追踪.md`/`时间线与状态.md`/`关键道具清单.md`/`人物档案`。
这些**保留为人类可读权威叙述**;本 skill 的数据库是它们的**机器可查询镜像**。
`seed-honglou.json` 即由上述文档策展。冲突时以**已发布正文 + 钉死设定**为准,
用 `audit.py` 显式暴露,不静默掩盖。

## 边界

- 不写正文、不代构大纲;是"事实账本"不是"创作脑"
- 已发布前8章正文**一字不改动**(项目铁律);新事实只经后续章节补叙带入
- 技术设定改动须同步 `01-世界观设定` 与 `03-核心道具与线索`,并回写 seed/capture 保持库与文档一致

## References

- `references/methodology.md` — RPG 状态库类比、四感知模型、读者信息差、完整工作流
- `references/schema.md` — 各表字段速查与 SQL 示例
- `references/seed-honglou.json` — 《红楼》初始种子(对齐至 Ch10)
- `scripts/schema.sql` — 完整 DDL
