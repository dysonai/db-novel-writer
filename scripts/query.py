#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
query.py -- 写作前/写作中查询状态库(单一真相源)

子命令:
  knowledge <角色名> [--chapter N]    查该角色截至某章的所有 见/闻/感/想/知
  prop <道具名>                       查道具当前持有者/位置/状态 + 流转史
  timeline [--chapter N]              查时间线
  foreshadowing [--status active]     查伏笔(默认列出全部)
  scene <章号> <seq>                  查某场景摘要 + 全部感知
  who <角色名>                        查角色档案(状态/位置/技能/盲点)

示例:
  python query.py --db .novel-db/novel.db knowledge 林黛玉 --chapter 10
  python query.py --db .novel-db/novel.db prop 幽灵芯片PM-7721
"""
import argparse
import json
import sqlite3
import sys


def conn_open(db):
    return sqlite3.connect(db)


def q_knowledge(conn, name, chapter=None):
    sql = """
        SELECT p.ptype, p.content, p.target_type, p.confidence, c.num, s.seq
        FROM perceptions p
        JOIN scenes s ON p.scene_id = s.id
        JOIN chapters c ON s.chapter_id = c.id
        JOIN characters ch ON p.character_id = ch.id
        WHERE ch.name = ?
    """
    params = [name]
    if chapter is not None:
        sql += " AND c.num <= ?"
        params.append(chapter)
    sql += " ORDER BY c.num, s.seq"
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        print(f"[knowledge] 未找到 {name} 的感知记录"
              + (f" (≤Ch{chapter})" if chapter else ""))
        return
    cur = None
    print(f"=== {name} 的感知(截至 Ch{chapter if chapter else '最新'}) ===")
    for ptype, content, ttype, conf, cnum, seq in rows:
        tag = f"[Ch{cnum}/{seq}]"
        print(f"  {tag} {ptype:<5} {content}  ({ttype or '-'}/{conf})")


def q_prop(conn, name):
    row = conn.execute(
        "SELECT id,holder_id,location_id,status,category,description,first_appearance,note "
        "FROM props WHERE name=?", (name,)).fetchone()
    if not row:
        print(f"[prop] 未找到道具: {name}")
        return
    pid, holder, loc, status, cat, desc, fa, note = row
    hname = conn.execute("SELECT name FROM characters WHERE id=?", (holder,)).fetchone()
    lname = conn.execute("SELECT name FROM locations WHERE id=?", (loc,)).fetchone()
    print(f"=== 道具: {name} ===")
    print(f"  类别: {cat}  状态: {status}  首现: {fa}")
    print(f"  当前持有: {hname[0] if hname else '无'}  位置: {lname[0] if lname else '无'}")
    if desc:
        print(f"  描述: {desc[:120]}")
    # 流转史
    trs = conn.execute(
        "SELECT t.method, fc.name, tc.name, c.num "
        "FROM prop_transfers t "
        "LEFT JOIN characters fc ON t.from_char_id=fc.id "
        "LEFT JOIN characters tc ON t.to_char_id=tc.id "
        "LEFT JOIN chapters c ON t.chapter_id=c.id "
        "WHERE t.prop_id=? ORDER BY c.num", (pid,)).fetchall()
    if trs:
        print("  流转史:")
        for method, f, t, cn in trs:
            print(f"    Ch{cn}: {f or '∅'} --({method})--> {t or '∅'}")


def q_timeline(conn, chapter=None):
    sql = "SELECT datetime, event_summary, anchor_note, kind FROM timeline"
    params = []
    if chapter is not None:
        sql += " WHERE chapter_id IN (SELECT id FROM chapters WHERE num<=?)"
        params.append(chapter)
    sql += " ORDER BY datetime"
    rows = conn.execute(sql, params).fetchall()
    print("=== 时间线 ===")
    for dt, ev, anchor, kind in rows:
        print(f"  {dt:<22} {ev}  ({anchor or ''})")


def q_foreshadowing(conn, status=None):
    sql = "SELECT code,title,status,planted_chapter,payoff_chapter FROM foreshadowing"
    params = []
    if status:
        sql += " WHERE status=?"
        params.append(status)
    sql += " ORDER BY code"
    rows = conn.execute(sql, params).fetchall()
    print("=== 伏笔 ===")
    for code, title, st, pc, pwc in rows:
        print(f"  {code:<4} [{st:<8}] {title}  (埋:{pc} 收:{pwc or '未'})")


def q_scene(conn, cnum, seq):
    row = conn.execute(
        "SELECT s.id,s.summary,l.name,s.time_start,s.time_end,ch.name "
        "FROM scenes s JOIN chapters c ON s.chapter_id=c.id "
        "LEFT JOIN locations l ON s.location_id=l.id "
        "LEFT JOIN characters ch ON s.pov_character_id=ch.id "
        "WHERE c.num=? AND s.seq=?", (cnum, seq)).fetchone()
    if not row:
        print(f"[scene] 未找到 Ch{cnum}/{seq}")
        return
    sid, summ, loc, ts, te, pov = row
    print(f"=== 场景 Ch{cnum}/{seq} @ {loc or '?'} [{ts}~{te}] POV:{pov or '?'} ===")
    print(f"  {summ}")
    percs = conn.execute(
        "SELECT p.ptype,p.content,ch.name FROM perceptions p "
        "JOIN characters ch ON p.character_id=ch.id WHERE p.scene_id=? ORDER BY p.ptype",
        (sid,)).fetchall()
    for ptype, content, who in percs:
        print(f"    {who} {ptype}: {content}")


def q_who(conn, name):
    row = conn.execute(
        "SELECT role,status,location_id,first_appearance,skills_note,blind_spots,bio "
        "FROM characters WHERE name=?", (name,)).fetchone()
    if not row:
        print(f"[who] 未找到: {name}")
        return
    role, status, loc, fa, skills, blind, bio = row
    lname = conn.execute("SELECT name FROM locations WHERE id=?", (loc,)).fetchone()
    print(f"=== {name} ===")
    print(f"  身份: {role}  状态: {status}  首现: {fa}  位置: {lname[0] if lname else '无'}")
    if skills:
        print(f"  技能: {skills}")
    if blind:
        print(f"  盲点: {blind}")
    if bio:
        print(f"  简介: {bio[:160]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("knowledge"); p.add_argument("name"); p.add_argument("--chapter", type=int)
    p = sub.add_parser("prop"); p.add_argument("name")
    p = sub.add_parser("timeline"); p.add_argument("--chapter", type=int)
    p = sub.add_parser("foreshadowing"); p.add_argument("--status")
    p = sub.add_parser("scene"); p.add_argument("cnum", type=int); p.add_argument("seq", type=int)
    p = sub.add_parser("who"); p.add_argument("name")

    args = ap.parse_args()
    conn = conn_open(args.db)
    if args.cmd == "knowledge":
        q_knowledge(conn, args.name, args.chapter)
    elif args.cmd == "prop":
        q_prop(conn, args.name)
    elif args.cmd == "timeline":
        q_timeline(conn, args.chapter)
    elif args.cmd == "foreshadowing":
        q_foreshadowing(conn, args.status)
    elif args.cmd == "scene":
        q_scene(conn, args.cnum, args.seq)
    elif args.cmd == "who":
        q_who(conn, args.name)
    conn.close()


if __name__ == "__main__":
    main()
