#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stage 1 · ASR 兜底（仅当 parse_bilibili.py 未拿到字幕时）。
backend:
  none    -> 直接报错提示用户配置 ASR（默认，绝不编造）
  whisper -> 本地 faster-whisper（需 pip install faster-whisper，CPU 较慢）
  api     -> 调用 --asr-api 指定的云端接口（自行实现返回 [{t,text}]）
产出 transcript.json / transcript.txt（与 parse_bilibili.py 同格式）
"""
import argparse
import json
import os
import subprocess
import sys


def get_ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def download_audio(url, out, proxy):
    path = os.path.join(out, "audio.mp3")
    r = subprocess.run(
        [sys.executable, "-m", "yt_dlp"] + (["--proxy", proxy] if proxy else []) + [
            "--ffmpeg-location", get_ffmpeg(),
            "--no-warnings", "-x", "--audio-format", "mp3", "-o", path, url],
        capture_output=True, text=True,
    )
    return path if os.path.exists(path) else None


def decode_with_ffmpeg(path):
    """用 imageio-ffmpeg 的 ffmpeg 把任意音视频解码成 16kHz 单声道 float32。
    绕开 faster-whisper 内部 PyAV 的版本兼容问题。"""
    import numpy as np
    ff = get_ffmpeg()
    cmd = [ff, "-nostdin", "-i", path, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"]
    r = subprocess.run(cmd, capture_output=True)
    if not r.stdout:
        raise RuntimeError("ffmpeg 解码音频失败: " + r.stderr.decode("utf-8", "ignore")[-800:])
    audio = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    return audio


def whisper_transcribe(audio_path, model_size="base"):
    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    audio = decode_with_ffmpeg(audio_path)
    # vad_filter 抑制音乐/静音段幻觉；关闭上文依赖避免复读循环
    segs, info = model.transcribe(
        audio, language="zh", beam_size=5,
        vad_filter=True, condition_on_previous_text=False,
    )
    out = []
    for s in segs:
        out.append((round(s.start, 1), s.text.strip()))
    return out, float(getattr(info, "duration", 0.0) or 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--proxy", default="", help="可选；留空则用系统代理/直连")
    ap.add_argument("--backend", default="none", choices=["none", "whisper", "api"])
    ap.add_argument("--model", default="base", help="faster-whisper 模型：tiny/base/small/medium")
    ap.add_argument("--asr-api", default="")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    if args.backend == "none":
        print(json.dumps({"error": "no_subtitle_and_backend_none",
                          "msg": "该视频无字幕，且未配置 ASR（backend=none）。请在 transcribe.py 配置 whisper/api，或提供带字幕的视频。"}))
        sys.exit(2)

    audio = download_audio(args.url, args.out, args.proxy)
    if not audio:
        raise RuntimeError("音频下载失败，无法 ASR")

    if args.backend == "whisper":
        transcript, _audio_dur = whisper_transcribe(audio, args.model)
    else:  # api：占位，按你的接口实现解析
        raise NotImplementedError("--asr-api 的解析需按你的接口格式实现（返回 [{t,text}]）")

    with open(os.path.join(args.out, "transcript.json"), "w", encoding="utf-8") as f:
        json.dump([{"t": t, "text": x} for t, x in transcript], f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "transcript.txt"), "w", encoding="utf-8") as f:
        for t, x in transcript:
            mm, ss = int(t // 60), int(t % 60)
            f.write(f"[{mm:02d}:{ss:02d}] {x}\n")
    print(json.dumps({"asr_lines": len(transcript)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
