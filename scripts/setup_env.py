#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
video2book 环境引导：
1) 通过代理用 pip 安装 yt-dlp / requests / pysocks / imageio-ffmpeg
2) 下载 echarts.min.js 到 assets/
3) 校验 ffmpeg 二进制可用
失败即明确报错，不静默继续。
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(ROOT, "assets")
ECHARTS_URL = "https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"
PIP_PKGS = ["yt-dlp", "requests", "pysocks", "imageio-ffmpeg"]


def run(cmd):
    print(">> " + " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxy", default="", help="可选；留空则用系统代理/直连")
    args = ap.parse_args()
    proxy = args.proxy
    if proxy:
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy
        pip_index = []
    else:
        # 清掉可能损坏的系统代理/镜像，强制官方源直连
        for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
            os.environ.pop(k, None)
        pip_index = ["-i", "https://pypi.org/simple"]

    # 1) pip 安装（无代理时走官方源直连）
    pip_cmd = [sys.executable, "-m", "pip", "install"] + pip_index
    if proxy:
        pip_cmd += ["--proxy", proxy]
    pip_cmd += PIP_PKGS
    r = run(pip_cmd)
    if r.returncode != 0:
        print("[WARN] pip install 失败，检查网络或参考 references/proxy_pip.md。")
        print(r.stderr[-2000:])
    else:
        print("[OK] pip 依赖安装完成")

    # 2) 下载 echarts
    os.makedirs(ASSETS, exist_ok=True)
    dest = os.path.join(ASSETS, "echarts.min.js")
    try:
        import requests
        with requests.Session() as s:
            if proxy:
                s.proxies = {"http": proxy, "https": proxy}
            resp = s.get(ECHARTS_URL, timeout=60)
            resp.raise_for_status()
            with open(dest, "wb") as f:
                f.write(resp.content)
        print(f"[OK] echarts.min.js -> {dest} ({len(resp.content)} bytes)")
    except Exception as e:
        print(f"[FAIL] 下载 echarts 失败: {e}")
        print("请手动下载并放到 assets/echarts.min.js")

    # 3) 校验 ffmpeg 二进制
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        print(f"[OK] ffmpeg 二进制: {exe}")
    except Exception as e:
        print(f"[FAIL] imageio-ffmpeg 未就绪: {e}")

    print("bootstrap 完成。若上面有 [FAIL]，先解决再跑视频流程。")


if __name__ == "__main__":
    main()
