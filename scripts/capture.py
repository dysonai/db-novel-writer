#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
capture.py -- 将一次"场景写作"中抽取的实体写入状态库

用法:
  python capture.py --db .novel-db/novel.db --file scene_ch11_01.json

输入 JSON 结构(均为可选, 按需填写):
{
  "chapter": {"num":11, "title":"烟幕", "status":"draft", "pov":"林黛玉", "summary":"..."},
  "scene":   {"seq":1, "location":"恒通机房", "time_start":"2017-07-26T14:00",
              "time_end":"2017-07-26T14:30", "pov":"林黛玉", "summary":"..."},
  "perceptions": [
     {"character":"林黛玉","ptype":"SEE","content":"配电柜的金属件在轻微震颤",
      "target_type":"prop","target":"幽灵芯片PM-7721","confidence":"inferred","source_note":"Ch11 Lxx"}
  ],
  "events": [
     {"time":"2017-07-26T14:10","type":"擦除","description":"清道夫远程擦除SD卡",
      "involved":["清道夫"],"consequence":"证据只剩碎片"}
  ],
  "prop_transfers": [
     {"prop":"幽灵芯片PM-7721","from":null,"to":"林黛玉","method":"拆下","note":"Ch3拆解"}
  ],
  "timeline": [
     {"datetime":"2017-07-26T14:10","event_summary":"清道夫擦除SD卡","kind":"absolute","anchor_note":"Ch11"}
  ]
}

ptype 取值: SEE 见 / HEAR 闻 / FEEL 感 / THINK 想 / KNOW 已知 / SAY 言 / DO 行
"""
import argparse
import json
import os
import sqlite3
import sys


def here(*p):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), *p)


def _id(conn, table, name, **defaults):
    row = conn.execute(f"SELECT id FROM {table} WHERE name=?", (name,)).fetchone()
    if row:
        return row[0]
    cols = ["name"] + list(defaults.keys())
    vals = [name] + list(defaults.values())
    cur = conn.execute(
        f"INSERT INTO {table}({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})", vals)
    conn.commit()
    print(f"  [新建] {table}: {name}")
    return cur.lastrowid


def _loc_id(conn, name):
    return _id(conn, "locations", name, type="unknown")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--file", required=True, help="场景抽取 JSON")
    args = ap.parse_args()

    if not os.path.isfile(args.file):
        print(f"[错误] 文件不存在: {args.file}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(args.db)
    with open(args.file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # chapter
    chap_id = None
    if "chapter" in data:
        c = data["chapter"]
        row = conn.execute("SELECT id FROM chapters WHERE num=?", (c["num"],)).fetchone()
        if row:
            chap_id = row[0]
            conn.execute(
                "UPDATE chapters SET title=?,status=?,summary=? WHERE id=?",
                (c.get("title"), c.get("status"), c.get("summary"), chap_id))
        else:
            cur = conn.execute(
                "INSERT INTO chapters(num,title,status,summary) VALUES(?,?,?,?)",
                (c["num"], c.get("title"), c.get("status"), c.get("summary")))
            chap_id = cur.lastrowid
        # pov
        if c.get("pov"):
            pov = _id(conn, "characters", c["pov"])
            conn.execute("UPDATE chapters SET pov_character_id=? WHERE id=?", (pov, chap_id))
        conn.commit()

    # scene
    scene_id = None
    if "scene" in data:
        s = data["scene"]
        if chap_id is None:
            print("[错误] scene 需要 chapter", file=sys.stderr)
            sys.exit(1)
        row = conn.execute(
            "SELECT id FROM scenes WHERE chapter_id=? AND seq=?",
            (chap_id, s.get("seq", 1))).fetchone()
        pov = _id(conn, "characters", s["pov"]) if s.get("pov") else None
        loc = _loc_id(conn, s["location"]) if s.get("location") else None
        if row:
            scene_id = row[0]
            conn.execute(
                "UPDATE scenes SET location_id=?,time_start=?,time_end=?,pov_character_id=?,summary=? WHERE id=?",
                (loc, s.get("time_start"), s.get("time_end"), pov, s.get("summary"), scene_id))
        else:
            cur = conn.execute(
                "INSERT INTO scenes(chapter_id,seq,location_id,time_start,time_end,pov_character_id,summary)"
                " VALUES(?,?,?,?,?,?,?)",
                (chap_id, s.get("seq", 1), loc, s.get("time_start"), s.get("time_end"),
                 pov, s.get("summary")))
            scene_id = cur.lastrowid
        conn.commit()

    if scene_id is None:
        print("[错误] 未提供 scene 或 chapter", file=sys.stderr)
        sys.exit(1)

    # perceptions
    n_p = 0
    for p in data.get("perceptions", []):
        ch = _id(conn, "characters", p["character"])
        tgt = None
        if p.get("target_type") == "character":
            tgt = _id(conn, "characters", p["target"])
        elif p.get("target_type") == "prop":
            tgt = _id(conn, "props", p["target"])
        conn.execute(
            "INSERT INTO perceptions(scene_id,character_id,ptype,content,target_type,target_id,confidence,source_note)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (scene_id, ch, p.get("ptype"), p.get("content"), p.get("target_type"),
             tgt, p.get("confidence"), p.get("source_note")))
        n_p += 1

    # events
    n_e = 0
    for e in data.get("events", []):
        conn.execute(
            "INSERT INTO events(chapter_id,scene_id,time,type,description,involved,consequence)"
            " VALUES(?,?,?,?,?,?,?)",
            (chap_id, scene_id, e.get("time"), e.get("type"), e.get("description"),
             json.dumps(e.get("involved", []), ensure_ascii=False), e.get("consequence")))
        n_e += 1

    # prop_transfers + 同步 props.holder_id/status
    n_t = 0
    for pt in data.get("prop_transfers", []):
        pr = _id(conn, "props", pt["prop"])
        to = _id(conn, "characters", pt["to"]) if pt.get("to") else None
        frm = _id(conn, "characters", pt["from"]) if pt.get("from") else None
        conn.execute(
            "INSERT INTO prop_transfers(prop_id,from_char_id,to_char_id,scene_id,chapter_id,method,note)"
            " VALUES(?,?,?,?,?,?,?)",
            (pr, frm, to, scene_id, chap_id, pt.get("method"), pt.get("note")))
        if to is not None:
            conn.execute("UPDATE props SET holder_id=? WHERE id=?", (to, pr))
        if pt.get("new_status"):
            conn.execute("UPDATE props SET status=? WHERE id=?", (pt["new_status"], pr))
        n_t += 1

    # timeline
    n_tl = 0
    for tl in data.get("timeline", []):
        conn.execute(
            "INSERT INTO timeline(datetime,chapter_id,scene_id,event_summary,kind,anchor_note)"
            " VALUES(?,?,?,?,?,?)",
            (tl.get("datetime"), chap_id, scene_id, tl.get("event_summary"),
             tl.get("kind"), tl.get("anchor_note")))
        n_tl += 1

    conn.commit()
    conn.close()
    print(f"[capture] 写入完成: 感知{n_p} 事件{n_e} 流转{n_t} 时间线{n_tl} (scene_id={scene_id})")


if __name__ == "__main__":
    main()
