# 数据库 Schema 速查

完整 DDL 见同级 `../scripts/schema.sql`。下表为各实体与关键字段速查。

| 表 | 用途 | 关键字段 |
|----|------|---------|
| characters | 角色 | name/alias/role/status/location_id/first_appearance/skills_note/blind_spots |
| locations | 地点(支持嵌套) | name/type/parent_id |
| chapters | 章节 | num/title/status/pov_character_id |
| scenes | 场景(时空切片) | chapter_id/seq/location_id/time_start/time_end/pov_character_id |
| perceptions | **四感知(核心)** | scene_id/character_id/ptype(SEE/HEAR/FEEL/THINK/KNOW/SAY/DO)/content/target_type/target_id/confidence |
| props | 道具 | name/category/holder_id/location_id/status/specs |
| prop_transfers | 道具流转(留痕) | prop_id/from_char_id/to_char_id/scene_id/chapter_id/method |
| events | 事件 | chapter_id/scene_id/time/type/description/involved(JSON)/consequence |
| foreshadowing | 伏笔 | code/title/planted_chapter/payoff_chapter/status(planted/active/paid_off/dropped)/planted_scene_id |
| timeline | 时间线 | datetime(ISO)/chapter_id/scene_id/event_summary/kind |
| consistency_issues | 审计结果 | check_type/severity/error|warn|info/detail/detected_at/resolved |

## ptype 取值
SEE 见 / HEAR 闻 / FEEL 感(情绪身体) / THINK 想(判断推断) / KNOW 已知事实 /
SAY 言 / DO 行

## 外键约定
所有 `*_id` 指向对应表主键。perceptions.target_id 按 target_type 指向
characters 或 props。seed/capture 时以 name/code 自动解析,无需手写 id。

## 查询示例(SQL)
```sql
-- 某角色截至某章的全部"已知/推断"
SELECT p.ptype, p.content, c.num, s.seq
FROM perceptions p
JOIN scenes s ON p.scene_id=s.id
JOIN chapters c ON s.chapter_id=c.id
JOIN characters ch ON p.character_id=ch.id
WHERE ch.name='林黛玉' AND c.num<=10
ORDER BY c.num, s.seq;

-- 某道具流转史
SELECT t.method, fc.name, tc.name, c.num
FROM prop_transfers t
LEFT JOIN characters fc ON t.from_char_id=fc.id
LEFT JOIN characters tc ON t.to_char_id=tc.id
LEFT JOIN chapters c ON t.chapter_id=c.id
WHERE t.prop_id=(SELECT id FROM props WHERE name='幽灵芯片PM-7721')
ORDER BY c.num;
```
