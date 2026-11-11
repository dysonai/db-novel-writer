#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
init_db.py -- 建立小说状态库并(可选)灌入种子数据

用法:
  # 仅建库(空表)
  python init_db.py --db .novel-db/novel.db

  # 建库 + 灌入策展种子(推荐用于《红楼:硬件鬼才林黛玉》)
  python init_db.py --db .novel-db/novel.db --seed references/seed-honglou.json

  # 建库 + 从项目现有 md 文档 best-effort 导入(伏笔/时间线/道具/人物)
  python init_db.py --db .novel-db/novel.db --project "D:/Claw/IntellectualProperties/红楼悬疑"

说明:
  - schema 从同目录 schema.sql 读取
  - seed JSON 顶层键对应各表: characters / locations / chapters / scenes /
    perceptions / props / prop_transfers / events / foreshadowing / timeline
  - 外键在插入时直接用 name/code 映射解析为 id, 不依赖二次回填
"""
import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime


def here(*p):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), *p)


def create_schema(conn):
    with open(here("schema.sql"), "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()


# ---------- 策展种子导入 ----------
def seed_from_json(conn, json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cur = conn.cursor()

    def ins(table, **kw):
        cols = list(kw.keys())
        vals = [kw[c] for c in cols]
        cur.execute(
            f"INSERT INTO {table}({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",
            vals,
        )
        return cur.lastrowid

    # 1) 基础实体(无外键)
    loc_map, char_map, prop_map, chap_map, fs_map = {}, {}, {}, {}, {}
    for r in data.get("locations", []):
        loc_map[r["name"]] = ins("locations", name=r["name"], type=r.get("type"),
                                 parent_id=None, note=r.get("note"))
    for r in data.get("characters", []):
        loc = loc_map.get(r.get("location_name"))
        char_map[r["name"]] = ins(
            "characters", name=r["name"], alias=r.get("alias"), role=r.get("role"),
            status=r.get("status"), location_id=loc,
            first_appearance=r.get("first_appearance"),
            skills_note=r.get("skills_note"), blind_spots=r.get("blind_spots"),
            bio=r.get("bio"))
    for r in data.get("props", []):
        holder = char_map.get(r.get("holder_name"))
        loc = loc_map.get(r.get("location_name"))
        prop_map[r["name"]] = ins(
            "props", name=r["name"], category=r.get("category"),
            description=r.get("description"), holder_id=holder, location_id=loc,
            status=r.get("status"), first_appearance=r.get("first_appearance"),
            specs=r.get("specs"), note=r.get("note"))
    for r in data.get("chapters", []):
        pov = char_map.get(r.get("pov_character_name"))
        chap_map[r["num"]] = ins(
            "chapters", num=r["num"], title=r.get("title"), status=r.get("status"),
            pov_character_id=pov, summary=r.get("summary"))
    for r in data.get("foreshadowing", []):
        fs_map[r["code"]] = ins(
            "foreshadowing", code=r["code"], title=r.get("title"),
            planted_chapter=r.get("planted_chapter"),
            payoff_chapter=r.get("payoff_chapter"), status=r.get("status"),
            description=r.get("description"), note=r.get("note"))

    # 2) 依赖实体
    scene_map = {}
    for r in data.get("scenes", []):
        chap = chap_map.get(r.get("chapter_num"))
        loc = loc_map.get(r.get("location"))
        pov = char_map.get(r.get("pov"))
        scene_map[r["key"]] = ins(
            "scenes", chapter_id=chap, seq=r.get("seq"), location_id=loc,
            time_start=r.get("time_start"), time_end=r.get("time_end"),
            pov_character_id=pov, summary=r.get("summary"))

    for r in data.get("events", []):
        chap = chap_map.get(r.get("chapter_num"))
        sc = scene_map.get(r.get("scene_key"))
        ins("events", chapter_id=chap, scene_id=sc, time=r.get("time"),
            type=r.get("type"), description=r.get("description"),
            involved=json.dumps(r.get("involved", []), ensure_ascii=False),
            consequence=r.get("consequence"))

    for p in data.get("perceptions", []):
        sc = scene_map.get(p.get("scene_key"))
        ch = char_map.get(p.get("character"))
        tgt = None
        if p.get("target_type") == "character":
            tgt = char_map.get(p.get("target"))
        elif p.get("target_type") == "prop":
            tgt = prop_map.get(p.get("target"))
        ins("perceptions", scene_id=sc, character_id=ch, ptype=p.get("ptype"),
            content=p.get("content"), target_type=p.get("target_type"),
            target_id=tgt, confidence=p.get("confidence"),
            source_note=p.get("source_note"))

    for pt in data.get("prop_transfers", []):
        pr = prop_map.get(pt.get("prop"))
        frm = char_map.get(pt.get("from"))
        to = char_map.get(pt.get("to"))
        sc = scene_map.get(pt.get("scene_key"))
        chap = chap_map.get(pt.get("chapter_num"))
        ins("prop_transfers", prop_id=pr, from_char_id=frm, to_char_id=to,
            scene_id=sc, chapter_id=chap, method=pt.get("method"),
            note=pt.get("note"))

    for tl in data.get("timeline", []):
        chap = chap_map.get(tl.get("chapter_num"))
        sc = scene_map.get(tl.get("scene_key"))
        ins("timeline", datetime=tl.get("datetime"), chapter_id=chap,
            scene_id=sc, event_summary=tl.get("event_summary"),
            kind=tl.get("kind"), anchor_note=tl.get("anchor_note"))

    for fs in data.get("foreshadowing", []):
        if fs.get("planted_scene_key"):
            sc = scene_map.get(fs.get("planted_scene_key"))
            if sc:
                conn.execute(
                    "UPDATE foreshadowing SET planted_scene_id=? WHERE code=?",
                    (sc, fs.get("code")))

    conn.commit()
    print(f"[seed] 已灌入: 角色{len(char_map)} 地点{len(loc_map)} 道具{len(prop_map)} "
          f"章节{len(chap_map)} 场景{len(scene_map)} 伏笔{len(fs_map)}")


# ---------- 从项目 md best-effort 导入 ----------
def import_project(conn, root):
    imported = {"foreshadowing": 0, "timeline": 0, "props": 0, "characters": 0}

    pdir = os.path.join(root, "02-人物档案")
    if os.path.isdir(pdir):
        for fn in os.listdir(pdir):
            if fn.endswith(".md") and ("-" in fn or "主角" in fn or "关键" in fn or "核心" in fn):
                name = fn.replace(".md", "")
                conn.execute(
                    "INSERT OR IGNORE INTO characters(name,status,first_appearance) VALUES(?,?,?)",
                    (name, "待补", ""))
                imported["characters"] += 1

    fpath = os.path.join(root, "03-核心道具与线索", "伏笔与回收追踪.md")
    if os.path.isfile(fpath):
        txt = open(fpath, encoding="utf-8").read()
        for m in re.finditer(r"###\s+(V\d{2}):([^\n]+)", txt):
            code, title = m.group(1), m.group(2).strip()
            st = "planted"
            seg = txt[m.start():m.start() + 1200]
            if "已回收" in seg[:200]:
                st = "paid_off"
            elif "已回收" in seg[:400] or "已激活" in seg[:400] or "进行中" in seg[:400]:
                st = "active"
            conn.execute(
                "INSERT OR IGNORE INTO foreshadowing(code,title,status,description) VALUES(?,?,?,?)",
                (code, title, st, ""))
            imported["foreshadowing"] += 1

    tpath = os.path.join(root, "07-连续性追踪", "时间线与状态.md")
    if os.path.isfile(tpath):
        txt = open(tpath, encoding="utf-8").read()
        for m in re.finditer(r"\|(\d{4}年[^\|]*?)\s*\|\s*([^|]+?)\s*\|\s*(Ch[^\|]*?)\s*\|", txt):
            dt, ev, src = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            conn.execute(
                "INSERT INTO timeline(datetime,event_summary,kind,anchor_note) VALUES(?,?,?,?)",
                (dt, ev, "absolute", src))
            imported["timeline"] += 1

    ppath = os.path.join(root, "03-核心道具与线索", "关键道具清单.md")
    if os.path.isfile(ppath):
        txt = open(ppath, encoding="utf-8").read()
        for m in re.finditer(r"###\s+(\d+)\.\s+([^\n]+)", txt):
            name = m.group(2).strip()
            conn.execute(
                "INSERT OR IGNORE INTO props(name,category,status) VALUES(?,?,?)",
                (name, "待分类", "待定"))
            imported["props"] += 1

    conn.commit()
    print(f"[import-project] 粗粒度导入完成: {imported}")
    print("  提示: best-effort 导入仅做实体占位, 建议再用 seed JSON 做精确填充。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="数据库文件路径")
    ap.add_argument("--seed", help="策展种子 JSON 路径")
    ap.add_argument("--project", help="项目根目录(从现有 md best-effort 导入)")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.db)), exist_ok=True)
    conn = sqlite3.connect(args.db)
    create_schema(conn)
    print(f"[init] schema 已创建: {args.db}")

    if args.seed:
        if not os.path.isfile(args.seed):
            print(f"[错误] seed 文件不存在: {args.seed}", file=sys.stderr)
            sys.exit(1)
        seed_from_json(conn, args.seed)

    if args.project:
        if not os.path.isdir(args.project):
            print(f"[错误] 项目目录不存在: {args.project}", file=sys.stderr)
            sys.exit(1)
        import_project(conn, args.project)

    conn.close()
    print(f"[完成] {datetime.now().isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
