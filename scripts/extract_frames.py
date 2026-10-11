#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stage 2 · 抽关键帧（供 host model 多模态理解）。
1) yt-dlp 经代理下载最佳 mp4 到 <out>/video.mp4
2) imageio-ffmpeg 提供 ffmpeg，按 duration 均匀抽 N 帧到 <out>/frames/
N = clamp(duration//150, 4, frames_max)，即约每 2.5 分钟 1 帧。
产出 frames/frame_*.jpg + frames.json([{t, file}])
"""
import argparse
import json
import os
import subprocess
import sys


def get_ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def get_duration(url, proxy):
    r = subprocess.run(
        [sys.executable, "-m", "yt_dlp"] + (["--proxy", proxy] if proxy else []) + [
            "--dump-json", "--no-warnings", "--skip-download", url],
        capture_output=True, text=True,
    )
    for line in reversed(r.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return int(json.loads(line).get("duration", 0) or 0)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--proxy", default="", help="可选；留空则用系统代理/直连")
    ap.add_argument("--frames-max", type=int, default=20)
    args = ap.parse_args()

    frames_dir = os.path.join(args.out, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    video_path = os.path.join(args.out, "video.mp4")

    ffmpeg = get_ffmpeg()

    # 下载视频（显式告知 yt-dlp ffmpeg 位置，否则音视频合并会失败）
    dl = subprocess.run(
        [sys.executable, "-m", "yt_dlp"] + (["--proxy", args.proxy] if args.proxy else []) + [
            "--ffmpeg-location", ffmpeg, "--no-warnings", "-f",
            "bv*+ba/best", "-o", video_path, args.url],
        capture_output=True, text=True,
    )
    if not os.path.exists(video_path):
        raise RuntimeError("视频下载失败:\n" + (dl.stderr or dl.stdout)[-1500:])

    dur = get_duration(args.url, args.proxy) or 0
    # 短视频抽密一点（约每 15s 一帧），长视频受 frames-max 上限约束
    n = max(4, min(args.frames_max, (dur // 15) or 4)) if dur else args.frames_max
    if dur == 0:
        n = args.frames_max

    frames = []
    for i in range(n):
        t = int(dur * (i + 0.5) / n) if dur else i * 30
        out_jpg = os.path.join(frames_dir, f"frame_{i:03d}.jpg")
        cmd = [ffmpeg, "-ss", str(t), "-i", video_path, "-frames:v", "1", "-q:v", "2", out_jpg]
        subprocess.run(cmd, capture_output=True, text=True)
        if os.path.exists(out_jpg):
            frames.append({"t": t, "file": os.path.relpath(out_jpg, args.out)})

    with open(os.path.join(args.out, "frames.json"), "w", encoding="utf-8") as f:
        json.dump(frames, f, ensure_ascii=False, indent=2)
    print(json.dumps({"frames": len(frames), "duration_sec": dur}, ensure_ascii=False))


if __name__ == "__main__":
    main()
