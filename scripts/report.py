#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
report.py -- 生成小说状态库的一致性看板(markdown)

用法:
  python report.py --db .novel-db/novel.db [--out report.md]

输出: 角色状态表 / 道具清单 / 待回收伏笔 / 时间线(末段) / 一致性问题
"""
import argparse
import sqlite3
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", help="输出 markdown 路径(默认打印到 stdout)")
    args = ap.parse_args()
    conn = sqlite3.connect(args.db)

    L = []
    L.append("# 小说状态库 · 一致性看板\n")

    # 角色状态
    L.append("## 一、角色状态")
    L.append("| 角色 | 身份 | 状态 | 当前位置 | 首现 |")
    L.append("|------|------|------|----------|------|")
    for name, role, status, loc, fa in conn.execute(
            "SELECT c.name,c.role,c.status,l.name,c.first_appearance "
            "FROM characters c LEFT JOIN locations l ON c.location_id=l.id ORDER BY c.id").fetchall():
        L.append(f"| {name} | {role or '-'} | {status or '-'} | {loc or '-'} | {fa or '-'} |")

    # 道具
    L.append("\n## 二、关键道具")
    L.append("| 道具 | 类别 | 状态 | 持有者 | 位置 |")
    L.append("|------|------|------|--------|------|")
    for name, cat, status, holder, loc in conn.execute(
            "SELECT p.name,p.category,p.status,ch.name,l.name "
            "FROM props p LEFT JOIN characters ch ON p.holder_id=ch.id "
            "LEFT JOIN locations l ON p.location_id=l.id ORDER BY p.id").fetchall():
        L.append(f"| {name} | {cat or '-'} | {status or '-'} | {holder or '-'} | {loc or '-'} |")

    # 伏笔
    L.append("\n## 三、伏笔回收追踪")
    L.append("| 编号 | 内容 | 状态 | 埋设 | 回收 |")
    L.append("|------|------|------|------|------|")
    for code, title, st, pc, pwc in conn.execute(
            "SELECT code,title,status,planted_chapter,payoff_chapter "
            "FROM foreshadowing ORDER BY code").fetchall():
        L.append(f"| {code} | {title} | {st} | {pc or '-'} | {pwc or '未'} |")

    # 时间线末段
    L.append("\n## 四、时间线(末 15 条)")
    for dt, ev, anchor in conn.execute(
            "SELECT datetime,event_summary,anchor_note FROM timeline "
            "ORDER BY datetime DESC LIMIT 15").fetchall():
        L.append(f"- `{dt}` {ev} ({anchor or ''})")

    # 一致性问题
    L.append("\n## 五、一致性问题")
    rows = conn.execute(
        "SELECT severity,check_type,detail FROM consistency_issues "
        "WHERE resolved=0 ORDER BY severity").fetchall()
    if not rows:
        L.append("- ✅ 无")
    else:
        for sev, ct, detail in rows:
            L.append(f"- **[{sev}] {ct}**: {detail}")

    conn.close()
    out = "\n".join(L) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"[report] 已写入: {args.out}")
    else:
        print(out)


if __name__ == "__main__":
    main()
