#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
literary_audit.py -- 文学性 / 降AI味 审查

把"怎么写更有人味"格式化为可查询、可校验的数据, 在初稿完成后对正文做审查:
  - ai-flavor : 扫描 AI 味写法谱系命中, 输出位置与轮换替换建议; --fix 生成去味稿
  - rhetoric  : 统计修辞手法密度与同词近距离重复, 给轮换建议
  - report    : 综合输出 markdown 文学性审计报告(并落库 style_audit_issues / rhetoric_usage)

所有判定依据都在数据库里(ai_flavor_catalog / rhetoric_catalog / style_thresholds),
因此阈值与谱系可逐项目覆盖, 不写死在代码里。

示例:
  python literary_audit.py ai-flavor --db .novel-db/novel.db \
      --text-file 第009章-结盟.md --chapter 9
  python literary_audit.py ai-flavor --db .novel-db/novel.db \
      --text-file draft.md --fix --out draft.clean.md
  python literary_audit.py rhetoric --db .novel-db/novel.db --text-file 第009章-结盟.md
  python literary_audit.py report --db .novel-db/novel.db \
      --text-file 第009章-结盟.md --out lit-audit.md --chapter 9
"""
import argparse
import json
import os
import re
import sqlite3
from datetime import datetime


def here(*p):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), *p)


def open_db(path):
    if not os.path.isfile(path):
        print(f"[错误] 数据库不存在: {path}\n  先运行 init_db.py --db {path} --seed ... --seed-literary",
              file=__import__("sys").stderr)
        __import__("sys").exit(1)
    return sqlite3.connect(path)


def load_catalogs(conn):
    cur = conn.cursor()
    af = []
    for row in cur.execute(
        "SELECT code,category,severity,match_type,match,replacements,auto_fix,rationale "
        "FROM ai_flavor_catalog"):
        af.append({
            "code": row[0], "category": row[1], "severity": row[2],
            "match_type": row[3], "match": row[4],
            "replacements": json.loads(row[5]) if row[5] else [],
            "auto_fix": bool(row[6]), "rationale": row[7] or ""})
    rh = []
    for row in cur.execute(
        "SELECT type,format_desc,connectors,example,rotation_rule,density_limit FROM rhetoric_catalog"):
        rh.append({
            "type": row[0], "format_desc": row[1],
            "connectors": json.loads(row[2]) if row[2] else [],
            "example": row[3], "rotation_rule": row[4], "density_limit": row[5]})
    th = {}
    for row in cur.execute("SELECT name,value,unit,note FROM style_thresholds"):
        th[row[0]] = {"value": row[1], "unit": row[2], "note": row[3]}
    return af, rh, th


def load_techniques(conn):
    cur = conn.cursor()
    out = []
    for row in cur.execute(
        "SELECT code,category,name,summary,when_use,anti_pattern,example,rotation,detectors "
        "FROM writing_techniques"):
        out.append({
            "code": row[0], "category": row[1], "name": row[2], "summary": row[3],
            "when_use": row[4], "anti_pattern": row[5], "example": row[6],
            "rotation": row[7],
            "detectors": json.loads(row[8]) if row[8] else []})
    return out


def scan_techniques(text, techs):
    """对每个带 detectors 的手法, 统计反模式命中数(全文本扫描, 不分行)。"""
    results = []
    for t in techs:
        hits = 0
        samples = []
        for d in t["detectors"]:
            m = d["match"]
            if d["match_type"] == "regex":
                try:
                    pat = re.compile(m)
                except re.error:
                    continue
                for mm in pat.finditer(text):
                    hits += 1
                    if len(samples) < 3:
                        samples.append(mm.group(0))
            else:
                start = 0
                while True:
                    idx = text.find(m, start)
                    if idx < 0:
                        break
                    hits += 1
                    if len(samples) < 3:
                        samples.append(m)
                    start = idx + len(m)
        results.append({"tech": t, "hits": hits, "samples": samples})
    return results


def char_count(text):
    """去空白后的中文字数(密度分母)。"""
    return len(re.sub(r"\s", "", text))


def resolve_chapter_id(conn, num):
    if not num:
        return None
    row = conn.execute("SELECT id FROM chapters WHERE num=?", (num,)).fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# AI 味扫描
# ---------------------------------------------------------------------------
def scan_ai_flavor(text, af):
    lines = text.split("\n")
    findings = []
    for p in af:
        m = p["match"]
        if p["match_type"] == "regex":
            try:
                pat = re.compile(m)
            except re.error:
                continue
            for li, line in enumerate(lines, 1):
                for mm in pat.finditer(line):
                    findings.append(_mk(li, mm.start() + 1, mm.group(0), p))
        else:
            for li, line in enumerate(lines, 1):
                start = 0
                while True:
                    idx = line.find(m, start)
                    if idx < 0:
                        break
                    findings.append(_mk(li, idx + 1, m, p))
                    start = idx + len(m)
    findings.sort(key=lambda x: (x["line"], x["col"]))
    return findings


def _mk(line, col, matched, p):
    return {
        "line": line, "col": col, "matched": matched, "category": p["category"],
        "severity": p["severity"], "code": p["code"],
        "replacements": p["replacements"], "auto_fix": p["auto_fix"],
        "rationale": p["rationale"]}


def apply_fix(text, af):
    """仅对 substring 且 auto_fix=1 的项按命中次序轮换替换。

    按匹配串长度从长到短处理, 避免短匹配串(如'冷得像冰')抢先在长句
    ('声音冷得像冰')内部替换而破坏语法。结果仍建议人工通读一遍。
    """
    counters = {}
    fixable = [p for p in af
               if p["auto_fix"] and p["replacements"] and p["match_type"] == "substring"]
    fixable.sort(key=lambda p: -len(p["match"]))
    lines = text.split("\n")
    for p in fixable:
        reps = p["replacements"]
        ci = counters.get(p["code"], 0)
        m = p["match"]
        for li in range(len(lines)):
            new_line = ""
            start = 0
            while True:
                idx = lines[li].find(m, start)
                if idx < 0:
                    new_line += lines[li][start:]
                    break
                new_line += lines[li][start:idx]
                new_line += reps[ci % len(reps)]
                ci += 1
                start = idx + len(m)
            lines[li] = new_line
        counters[p["code"]] = ci
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 修辞扫描
# ---------------------------------------------------------------------------
def scan_rhetoric(text, rh, th):
    total = char_count(text)
    per1k = (total / 1000.0) if total else 0
    results = []
    for d in rh:
        conns = [c for c in d["connectors"] if c]
        counts = {c: text.count(c) for c in conns}
        total_hits = sum(counts.values())
        # 同标记词近距离重复(<200字)检测
        repeats = []
        for c, n in counts.items():
            if n >= 2:
                positions = [m.start() for m in re.finditer(re.escape(c), text)]
                for i in range(len(positions) - 1):
                    if positions[i + 1] - positions[i] < 200:
                        repeats.append((c, positions[i + 1]))
        limit = d.get("density_limit") or 0
        density = (total_hits / per1k) if per1k else 0
        results.append({
            "type": d["type"], "counts": counts, "total": total_hits,
            "density": density, "limit": limit,
            "over": bool(limit) and density > limit,
            "repeats": repeats, "rotation_rule": d["rotation_rule"]})
    return results, total


def count_dash(text, th):
    total = char_count(text)
    per1k = (total / 1000.0) if total else 0
    n = text.count("——")
    limit = th.get("dash_per_1k", {}).get("value", 7)
    return n, (n / per1k) if per1k else 0, limit


def count_short_sentences(text, th):
    """连续 ≤6 字短句(以。！？分割)的最大连续数。"""
    max_allowed = int(th.get("consecutive_short_sent", {}).get("value", 3))
    sents = re.split(r"[。！？!?]", text)
    run = 0
    max_run = 0
    for s in sents:
        stripped = re.sub(r"\s", "", s)
        if 0 < len(stripped) <= 6:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    return max_run, max_allowed


# ---------------------------------------------------------------------------
# 落库
# ---------------------------------------------------------------------------
def record_ai(conn, chapter_id, findings):
    cur = conn.cursor()
    for f in findings:
        cur.execute(
            "INSERT INTO style_audit_issues(chapter_id,issue_type,category,severity,line_no,detail,suggestion,detected_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (chapter_id, "ai_flavor", f["category"], f["severity"], f["line"],
             f"[{f['code']}] {f['matched']}",
             " / ".join(f["replacements"]) if f["replacements"] else "需人工判断(语境)",
             datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def record_rhetoric(conn, chapter_id, results, total):
    cur = conn.cursor()
    per1k = (total / 1000.0) if total else 0
    for r in results:
        if r["total"] == 0:
            continue
        cur.execute(
            "INSERT INTO rhetoric_usage(chapter_id,device_type,count,density) VALUES(?,?,?,?)",
            (chapter_id, r["type"], r["total"], round(r["density"], 2)))
        if r["over"]:
            cur.execute(
                "INSERT INTO style_audit_issues(chapter_id,issue_type,category,severity,detail,suggestion,detected_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (chapter_id, "rhetoric", r["type"], "warn",
                 f"{r['type']}密度 {r['density']:.2f}/千字 > 上限 {r['limit']}/千字",
                 r["rotation_rule"], datetime.now().isoformat(timespec="seconds")))
        if r["repeats"]:
            cur.execute(
                "INSERT INTO style_audit_issues(chapter_id,issue_type,category,severity,detail,suggestion,detected_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (chapter_id, "rhetoric", r["type"], "info",
                 f"{r['type']}标记词近距离重复 {len(r['repeats'])} 处(同词<200字)",
                 r["rotation_rule"], datetime.now().isoformat(timespec="seconds")))
    conn.commit()


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def print_ai(findings):
    if not findings:
        print("  [ai-flavor] 未发现 AI 味写法命中。")
        return
    print(f"  [ai-flavor] 命中 {len(findings)} 处:")
    for f in findings:
        tag = "可自动替换" if (f["auto_fix"] and f["replacements"]) else "需人工"
        sug = " / ".join(f["replacements"]) if f["replacements"] else "—"
        print(f"    L{f['line']}:{f['col']} [{f['severity']}] {f['category']}({f['code']}) "
              f"「{f['matched']}」→ {sug} ({tag})")


def print_rhetoric(results, total):
    print(f"  [rhetoric] 字数(去空白)≈{total}  修辞密度:")
    for r in results:
        if r["total"] == 0:
            continue
        flag = " ⚠超上限" if r["over"] else ""
        rep = f"  重复{r['repeats'] and len(r['repeats'])}处" if r["repeats"] else ""
        print(f"    {r['type']}: 命中{r['total']} 密度{r['density']:.2f}/千字 "
              f"(上限{r['limit']}){flag}{rep}")


def write_report_md(path, src_name, total, af_findings, rh_results, dash, short, th):
    n_dash, dash_d, dash_lim = dash
    max_run, short_lim = short
    lines = []
    lines.append(f"# 文学性审计报告 — {src_name}\n")
    lines.append(f"- 字数(去空白): {total}")
    lines.append(f"- 破折号: {n_dash} 处 / {dash_d:.2f} 千字 (上限 {dash_lim})"
                 f"{' ⚠超上限' if dash_d > dash_lim else ''}")
    lines.append(f"- 连续短句最长: {max_run} 句 (上限 {short_lim})"
                 f"{' ⚠断奏依赖' if max_run > short_lim else ''}\n")

    lines.append("## 一、AI 味写法命中\n")
    if not af_findings:
        lines.append("无。\n")
    else:
        lines.append("| 行:列 | 类别 | 严重度 | 命中 | 替换建议 |")
        lines.append("|------|------|--------|------|----------|")
        for f in af_findings:
            sug = " / ".join(f["replacements"]) if f["replacements"] else "需人工判断"
            lines.append(f"| {f['line']}:{f['col']} | {f['category']} | {f['severity']} | "
                         f"「{f['matched']}」 | {sug} |")
        lines.append("")

    lines.append("## 二、修辞手法密度\n")
    any_rh = [r for r in rh_results if r["total"] > 0]
    if not any_rh:
        lines.append("无显著修辞命中。\n")
    else:
        lines.append("| 手法 | 命中 | 密度/千字 | 上限 | 状态 |")
        lines.append("|------|------|-----------|------|------|")
        for r in any_rh:
            status = "⚠超上限" if r["over"] else ("重复" if r["repeats"] else "正常")
            lines.append(f"| {r['type']} | {r['total']} | {r['density']:.2f} | {r['limit']} | {status} |")
        lines.append("")

    lines.append("## 三、轮换建议\n")
    tips = []
    for r in any_rh:
        if r["over"] or r["repeats"]:
            tips.append(f"- **{r['type']}**: {r['rotation_rule']}")
    if n_dash > dash_lim:
        tips.append(f"- **破折号**: 非必要的「——」改逗号或句号, 当前 {n_dash} 处超 {dash_lim}/千字。")
    if max_run > short_lim:
        tips.append(f"- **断奏依赖**: 连续短句最长 {max_run} 句超 {short_lim}, 适当并入长句或加动作细节。")
    if not tips:
        tips.append("- 当前文学性指标均在阈值内, 无强制轮换项。")
    lines.extend(tips)
    lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[report] 已写出: {path}")


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------
def cmd_ai_flavor(args, conn, af, rh, th):
    text = open(args.text_file, encoding="utf-8").read()
    findings = scan_ai_flavor(text, af)
    chapter_id = resolve_chapter_id(conn, args.chapter)
    print(f"\n=== ai-flavor: {args.text_file} ===")
    print_ai(findings)
    if not args.no_record:
        record_ai(conn, chapter_id, findings)
        print(f"  [已落库 style_audit_issues: {len(findings)} 条]")
    if args.fix:
        out = apply_fix(text, af)
        out_path = args.out or (args.text_file + ".clean.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"  [--fix] 去味稿已写出: {out_path}")
        print("  [提示] --fix 为初稿机械去味, 子串替换可能改动原句语法, 请人工通读一遍。")


def cmd_rhetoric(args, conn, af, rh, th):
    text = open(args.text_file, encoding="utf-8").read()
    results, total = scan_rhetoric(text, rh, th)
    chapter_id = resolve_chapter_id(conn, args.chapter)
    dash = count_dash(text, th)
    short = count_short_sentences(text, th)
    print(f"\n=== rhetoric: {args.text_file} ===")
    print_rhetoric(results, total)
    print(f"  破折号: {dash[0]} 处 / {dash[1]:.2f} 千字 (上限 {dash[2]})"
          f"{' ⚠超上限' if dash[1] > dash[2] else ''}")
    print(f"  连续短句最长: {short[0]} 句 (上限 {short[1]})"
          f"{' ⚠断奏依赖' if short[0] > short[1] else ''}")
    if not args.no_record:
        record_rhetoric(conn, chapter_id, results, total)
        print("  [已落库 rhetoric_usage / style_audit_issues]")


def cmd_report(args, conn, af, rh, th):
    text = open(args.text_file, encoding="utf-8").read()
    findings = scan_ai_flavor(text, af)
    results, total = scan_rhetoric(text, rh, th)
    dash = count_dash(text, th)
    short = count_short_sentences(text, th)
    chapter_id = resolve_chapter_id(conn, args.chapter)
    if not args.no_record:
        record_ai(conn, chapter_id, findings)
        record_rhetoric(conn, chapter_id, results, total)
    out = args.out or (args.text_file + ".lit-audit.md")
    write_report_md(out, os.path.basename(args.text_file), total, findings, results, dash, short, th)


def _print_technique_cards(techs):
    by_cat = {}
    for t in techs:
        by_cat.setdefault(t["category"], []).append(t)
    print(f"\n=== 写作手法图谱({len(techs)} 项, {len(by_cat)} 类) ===")
    for cat, items in by_cat.items():
        print(f"\n▍{cat}")
        for t in items:
            det = "可机检" if t["detectors"] else "人工核查"
            print(f"  · {t['name']} [{t['code']}] ({det})")
            print(f"      说明: {t['summary']}")
            print(f"      何时用: {t['when_use']}")
            print(f"      反模式: {t['anti_pattern']}")
            print(f"      示例: {t['example']}")
            print(f"      轮换: {t['rotation']}")


def _write_technique_md(path, src_name, results, techs):
    by_cat = {}
    for t in techs:
        by_cat.setdefault(t["category"], []).append(t)
    lines = [f"# 写作手法覆盖检查 — {src_name}\n"]
    lines.append(f"- 手法总数: {len(techs)}（可机检 {sum(1 for t in techs if t['detectors'])} 项 / 人工核查 {sum(1 for t in techs if not t['detectors'])} 项）\n")
    lines.append("## 一、可机检项 · 反模式命中\n")
    any_hit = False
    for r in results:
        if r["hits"]:
            any_hit = True
            t = r["tech"]
            lines.append(f"- ⚠ **{t['name']}**（{t['category']}）：反模式命中 {r['hits']} 处")
            lines.append(f"  - 样本: {', '.join(r['samples'])}")
            lines.append(f"  - 反模式: {t['anti_pattern']}")
            lines.append(f"  - 轮换建议: {t['rotation']}")
    if not any_hit:
        lines.append("无。机检项未检出明显反模式。\n")
    lines.append("## 二、人工核查项\n")
    for t in techs:
        if not t["detectors"]:
            lines.append(f"- **{t['name']}**（{t['category']}）：{t['summary']}")
    lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[techniques] 已写出: {path}")


def cmd_techniques(args, conn, af, rh, th):
    techs = load_techniques(conn)
    if not args.text_file:
        _print_technique_cards(techs)
        return
    text = open(args.text_file, encoding="utf-8").read()
    results = scan_techniques(text, techs)
    print(f"\n=== techniques: {args.text_file} ===")
    print(f"  写作手法图谱: {len(techs)} 项, 可机检 {sum(1 for t in techs if t['detectors'])} 项")
    for r in results:
        t = r["tech"]
        if r["hits"]:
            print(f"  ⚠ [{t['category']}] {t['name']}: 反模式命中 {r['hits']} 处 "
                  f"(样本: {', '.join(r['samples'])})")
        else:
            print(f"    [{t['category']}] {t['name']}: 文本中未检出反模式")
    no_det = [t for t in techs if not t["detectors"]]
    if no_det:
        print(f"  · 人工核查项({len(no_det)}): " + " / ".join(t["name"] for t in no_det))
    if args.out:
        _write_technique_md(args.out, os.path.basename(args.text_file), results, techs)


def main():
    ap = argparse.ArgumentParser(description="文学性 / 降AI味 审查")
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--db", required=True, help="数据库文件路径")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ai-flavor", parents=[parent], help="扫描 AI 味写法")
    a.add_argument("--text-file", required=True)
    a.add_argument("--chapter", type=int, help="关联章节号(用于落库)")
    a.add_argument("--fix", action="store_true", help="生成去味稿")
    a.add_argument("--out", help="--fix 输出路径")
    a.add_argument("--no-record", action="store_true", help="不写入数据库")
    a.set_defaults(func=cmd_ai_flavor)

    r = sub.add_parser("rhetoric", parents=[parent], help="修辞密度与轮换")
    r.add_argument("--text-file", required=True)
    r.add_argument("--chapter", type=int)
    r.add_argument("--no-record", action="store_true")
    r.set_defaults(func=cmd_rhetoric)

    p = sub.add_parser("report", parents=[parent], help="综合 markdown 报告")
    p.add_argument("--text-file", required=True)
    p.add_argument("--chapter", type=int)
    p.add_argument("--out", required=True)
    p.add_argument("--no-record", action="store_true")
    p.set_defaults(func=cmd_report)

    t = sub.add_parser("techniques", parents=[parent], help="写作手法图谱/反模式机检")
    t.add_argument("--text-file", help="待检正文; 省略则仅列出手法图谱")
    t.add_argument("--out", help="机检结果 markdown 输出路径")
    t.set_defaults(func=cmd_techniques)

    args = ap.parse_args()
    conn = open_db(args.db)
    af, rh, th = load_catalogs(conn)
    args.func(args, conn, af, rh, th)
    conn.close()


if __name__ == "__main__":
    main()
