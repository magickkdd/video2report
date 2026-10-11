# video2report

把一段 **B 站视频**在几分钟内变成一份 **单页、交互式、带图表**的中文速学报告 —— 目标不是"看完视频"，而是**用最短时间搞懂它讲了什么、要点有哪些、关键关系/数据是什么**。

---

## 它解决什么问题

长视频学习的痛点：完整看一遍太慢，跳过又怕漏掉关键内容。本工具把视频里的**字幕 / 语音 / 画面**抽出来，压缩成一份结构化报告，配关键图表与术语表。

## 核心能力

- **多模态读取**
  - 字幕优先（可下载的软字幕轨道）
  - 无字幕 → 语音转文字兜底（faster-whisper，CPU 可跑）
  - 关键帧画面 → 交给多模态大模型理解
- **自动识别"无旁白视频"**
  - 纯字幕卡 + BGM 的动画类视频，ASR 会输出幻觉歌词
  - 用 `vad_filter` 判定为 0 段语音后，自动切换到**纯视觉路线**（加密抽帧读画面字幕）
- **单页交互式 HTML 报告**
  - 速览卡（一句话结论 + 3 条 takeaway）
  - 章节要点（4–8 章，每章 3–5 个极简要点）
  - ECharts 图表（流程图 / 概念关系图 / 时间线 / 柱状趋势）
  - 术语表 + 关键帧插图
- **图表按视频类型自适应**：教程实操 → 步骤流程；知识科普 → 概念关系图；会议录屏 → 决策时间线；含数据 → 柱状/趋势

## 快速开始

```bash
git clone https://github.com/magickkdd/video2report.git
cd video2report

# 1) 首次引导：装依赖 + 下载 echarts（ffmpeg 由 imageio-ffmpeg 提供，无需手动装）
python scripts/setup_env.py

# 2) 解析：拿元数据 + 字幕
python scripts/parse_bilibili.py --url "https://www.bilibili.com/video/BVxxxx" --out output/BVxxxx

# 3) 无字幕时：语音转写（有字幕可跳过）
python scripts/transcribe.py --url "..." --out output/BVxxxx --backend whisper --model base

# 4) 抽关键帧（供多模态模型看图）
python scripts/extract_frames.py --url "..." --out output/BVxxxx --frames-max 20

# 5) 合成（这一步由 AI agent 完成）
#    读取 meta.json + transcript + frames，产出 report.json，格式见 examples/sample_report.json

# 6) 渲染
python scripts/render_report.py \
  --report output/BVxxxx/report.json \
  --frames-dir output/BVxxxx/frames \
  --template assets/report_template.html \
  --echarts assets/echarts.min.js \
  --out output/BVxxxx/report.html
```

> `assets/echarts.min.js` 由 `setup_env.py` 下载，已加入 `.gitignore`。

## 目录结构

```
video2report/
├─ SKILL.md                  # 给 AI agent 的编排说明（含环境闸门、工作流、坑位清单）
├─ README.md
├─ scripts/
│  ├─ setup_env.py           # 一键装依赖 + 拉 echarts
│  ├─ parse_bilibili.py      # 元数据 + 字幕（yt-dlp，json3）
│  ├─ transcribe.py          # ASR 兜底（whisper / 自建 API）
│  ├─ extract_frames.py      # ffmpeg 抽关键帧
│  └─ render_report.py       # report.json → 单页 HTML
├─ assets/
│  └─ report_template.html   # 固定中文极简模板（CSS 一次写好，保证输出一致性）
├─ references/
│  └─ proxy_pip.md           # pip 走代理的排错
└─ examples/
   └─ sample_report.json     # report.json schema 示例
```

## 实测踩过的坑（都已处理，详见 SKILL.md §6）

| 坑 | 处置 |
|---|---|
| 术语混淆：软字幕 / 硬字幕 / 弹幕 | 必须区分；`yt-dlp --list-subs` 判定。B站 的 `danmaku` 是弹幕不是字幕 |
| yt-dlp 找不到 ffmpeg，音视频无法合并 | 传 `--ffmpeg-location`（ffmpeg 来自 imageio-ffmpeg，不在 PATH） |
| faster-whisper 与 PyAV 版本不兼容 | 不让其内部解码：先用 ffmpeg 解码成 16k float32 再喂 `model.transcribe()` |
| HuggingFace 模型下载失败（代理 10061） | 用已缓存模型 + `HF_HUB_OFFLINE=1`；长音频优先 base 控耗时 |
| 无旁白视频 ASR 输出幻觉歌词 | `vad_filter=True` 复跑，`asr_lines==0` 即确认无语音 → 转视觉路线 |
| 渲染时帧图片路径错误 | 输出为 `frames/<文件名>`，与 `frames/` 目录同级 |
| pip 装包被镜像/代理坑 | 清代理变量 + `-i https://pypi.org/simple` 直连；需要代理时用 `--proxy` |

## 说明

- 本仓库最初作为 **WorkBuddy skill** 开发，`SKILL.md` 是给 AI agent 的编排说明（环境闸门 / 分阶段工作流 / 反模式）。即使不使用 agent，也可以按上面命令行手动跑通全链路。
- 音频/视频/帧等中间产物体积较大，已通过 `.gitignore` 排除，不会进仓库。
