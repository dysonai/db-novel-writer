#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit.py -- 一致性审计: 把"前后文矛盾"变成可定位的工单

检查项:
  char_location    同角色在同一时刻出现在两个不同地点 (error)
  prop_holder     道具当前持有者与最新一次流转落点不一致 (warn)
  foreshadowing_open  伏笔已埋设但未回收 (info)
  perception_dangling  感知声明了目标类型却未解析到实体 (info)
  timeline_order  时间线日期与章节顺序不一致 (info)

审计结果写入 consistency_issues 表(每条带 detected_at/severity/resolved)。
"""
import argparse
import sqlite3
import sys
from datetime import datetime


def parse_time(s):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None  # 中文/相对格式(如 2010年9月14日 / T+0)跳过


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    args = ap.parse_args()
    conn = sqlite3.connect(args.db)

    issues = []  # (check_type, severity, detail)

    def name(t, i):
        r = conn.execute(f"SELECT name FROM {t} WHERE id=?", (i,)).fetchone()
        return r[0] if r else f"?{i}"

    # ---- char_location ----
    scenes = conn.execute(
        "SELECT id,location_id,time_start,time_end,pov_character_id FROM scenes").fetchall()
    presence = {}
    for sid, loc, ts, te, pov in scenes:
        chars = set()
        if pov:
            chars.add(pov)
        for (c,) in conn.execute(
                "SELECT character_id FROM perceptions WHERE scene_id=?", (sid,)).fetchall():
            chars.add(c)
        t0, t1 = parse_time(ts), parse_time(te)
        for c in chars:
            presence.setdefault(c, []).append((sid, loc, t0, t1))
    for c, lst in presence.items():
        al = [x for x in lst if x[2] is not None]
        for i in range(len(al)):
            for j in range(i + 1, len(al)):
                a, b = al[i], al[j]
                if a[1] == b[1]:
                    continue
                if a[2] == b[2]:
                    issues.append(("char_location", "error",
                                   f"角色【{name('characters', c)}】在 {a[2]} 同时出现在两处: "
                                   f"{name('locations', a[1])} / {name('locations', b[1])}"))
                elif a[3] and b[2] and a[2] <= b[2] <= a[3]:
                    issues.append(("char_location", "error",
                                   f"角色【{name('characters', c)}】时间区间重叠却异地: "
                                   f"{name('locations', a[1])}[{a[2]}] vs {name('locations', b[1])}[{b[2]}]"))
    # ---- prop_holder ----
    for pid, pname, holder, status in conn.execute(
            "SELECT id,name,holder_id,status FROM props").fetchall():
        last = conn.execute(
            "SELECT to_char_id FROM prop_transfers WHERE prop_id=? ORDER BY id DESC LIMIT 1",
            (pid,)).fetchone()
        if last and last[0] is not None and holder != last[0]:
            issues.append(("prop_holder", "warn",
                           f"道具【{pname}】当前持有={name('characters', holder)} "
                           f"但最新流转落点={name('characters', last[0])}"))
    # ---- foreshadowing_open ----
    for code, title, st, pc in conn.execute(
            "SELECT code,title,status,planted_chapter FROM foreshadowing").fetchall():
        if st not in ("paid_off", "dropped"):
            issues.append(("foreshadowing_open", "info",
                           f"{code} 【{title}】状态={st}, 仍未回收(埋设:{pc})"))
    # ---- perception_dangling ----
    d = conn.execute(
        "SELECT COUNT(*) FROM perceptions WHERE target_type IS NOT NULL AND target_id IS NULL"
    ).fetchone()[0]
    if d:
        issues.append(("perception_dangling", "info",
                       f"{d} 条感知声明了 target_type 却未解析到实体(需补 target)"))
    # ---- timeline_order ----
    tl = conn.execute(
        "SELECT t.datetime, c.num FROM timeline t JOIN chapters c ON t.chapter_id=c.id "
        "WHERE t.datetime LIKE '____-__-__%' ORDER BY t.datetime").fetchall()
    prev_num = -1
    for dt, num in tl:
        if prev_num != -1 and num < prev_num:
            issues.append(("timeline_order", "info",
                           f"时间线 {dt}(Ch{num}) 早于前一锚点章节(Ch{prev_num})"))
        prev_num = num

    # 写入表
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute("DELETE FROM consistency_issues")  # 每次审计刷新
    for ct, sev, detail in issues:
        conn.execute(
            "INSERT INTO consistency_issues(check_type,severity,detail,detected_at,resolved)"
            " VALUES(?,?,?,?,0)", (ct, sev, detail, now))
    conn.commit()

    # 打印
    order = {"error": 0, "warn": 1, "info": 2}
    issues.sort(key=lambda x: order.get(x[1], 9))
    print(f"=== 一致性审计 @ {now} ===")
    if not issues:
        print("  ✅ 无异常")
    else:
        for ct, sev, detail in issues:
            ic = {"error": "❌", "warn": "⚠️", "info": "ℹ️"}.get(sev, "·")
            print(f"  {ic} [{sev}] {ct}: {detail}")
    print(f"  共 {len(issues)} 条 (error/已入库 consistency_issues)")
    conn.close()


if __name__ == "__main__":
    main()
