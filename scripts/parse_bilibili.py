#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stage 0 · 解析 B站视频：元数据 + 字幕（优先官方/AI 字幕）。
依赖：yt-dlp（经代理）。无字幕时 transcript.json 为空列表，交给 transcribe.py。
"""
import argparse
import json
import os
import subprocess
import sys


def run_yt(cmd):
    print(">> " + " ".join(cmd), file=sys.stderr)
    return subprocess.run(cmd, capture_output=True, text=True)


def dump_meta(url, proxy):
    base = [sys.executable, "-m", "yt_dlp"] + (["--proxy", proxy] if proxy else [])
    cmd = base + ["--dump-json", "--no-warnings", "--skip-download", url]
    r = run_yt(cmd)
    if r.returncode != 0:
        raise RuntimeError("yt-dlp 获取元数据失败:\n" + (r.stderr or r.stdout)[-1500:])
    # 最后一行是 JSON
    for line in reversed(r.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise RuntimeError("未在输出中找到 JSON 元数据")


def parse_json3(path):
    """把 yt-dlp 的 json3 字幕解析为 [(start_sec, text), ...]"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for ev in data.get("events", []):
        segs = ev.get("segs") or []
        text = "".join(s.get("utf8", "") for s in segs).strip()
        text = text.replace("\n", " ").strip()
        if not text:
            continue
        start = (ev.get("tStartMs", 0) + ev.get("tOffsetMs", 0)) / 1000.0
        out.append((round(start, 1), text))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--proxy", default="", help="可选；留空则用系统代理/直连")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    meta = dump_meta(args.url, args.proxy)
    info = {
        "bvid": meta.get("id", ""),
        "title": meta.get("title", ""),
        "up": meta.get("uploader", meta.get("channel", "")),
        "duration_sec": int(meta.get("duration", 0) or 0),
        "type": meta.get("categories", [""])[0] if meta.get("categories") else "",
        "webpage_url": meta.get("webpage_url", ""),
        "thumbnail": meta.get("thumbnail", ""),
    }
    with open(os.path.join(args.out, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    # 拉字幕（官方 + 自动）
    sub_cmd = [sys.executable, "-m", "yt_dlp"] + (["--proxy", args.proxy] if args.proxy else []) + [
        "--no-warnings", "--skip-download",
        "--write-subs", "--write-auto-subs",
        "--sub-langs", "zh-CN,zh,zh-Hans,all",
        "--sub-format", "json3",
        "-o", os.path.join(args.out, "sub.%(ext)s"),
        args.url,
    ]
    run_yt(sub_cmd)

    transcript = []
    for fn in sorted(os.listdir(args.out)):
        if fn.startswith("sub.") and fn.endswith(".json3"):
            transcript = parse_json3(os.path.join(args.out, fn))
            break

    with open(os.path.join(args.out, "transcript.json"), "w", encoding="utf-8") as f:
        json.dump([{"t": t, "text": x} for t, x in transcript], f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "transcript.txt"), "w", encoding="utf-8") as f:
        for t, x in transcript:
            mm = int(t // 60); ss = int(t % 60)
            f.write(f"[{mm:02d}:{ss:02d}] {x}\n")

    print(json.dumps({
        "bvid": info["bvid"], "title": info["title"], "duration_sec": info["duration_sec"],
        "has_subtitle": bool(transcript),
        "subtitle_lines": len(transcript),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
