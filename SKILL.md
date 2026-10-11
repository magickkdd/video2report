---
name: video2book
description: 输入B站视频链接，多模态读取字幕/语音与关键帧画面，由本 agent（host model）合成并生成单页交互式 HTML 速学报告（中文极简要点 + ECharts 自适应图表），帮助用户快速掌握视频知识而无需看完视频。当用户给出 B站 视频链接、想"把视频变成笔记/报告/图文总结/速读"、或"快速了解这个视频讲什么"时使用。
version: 0.4.0
agent_created: true
---

# video2book —— 视频速读成书（代码包版）

## 0. 为什么是"代码包"而不是纯 md
SKILL.md 只是给 agent 的提示词，无法保证渲染质量。本 skill 把确定性工作交给脚本与固定模板：
- 解析 / 抽帧 / ASR / 渲染 → Python 脚本（可复现、样式统一）
- 报告外观 → 固定 `assets/report_template.html`（CSS 一次写好，不再临场发挥）
- 图表 → 本地内置 `echarts.min.js`（离线可用，不依赖运行时 CDN）
- agent 只做它擅长的事：**多模态看图 + 总结合成 + 按类型设计图表**

## 1. 环境闸门（每次运行前先确认）
- **网络**：默认直连 / 系统代理即可（实测 bilibili、pypi、echarts 的 CDN 均可直连）。除非你的环境特殊，否则**无需配置任何代理**。若确需代理，用 `--proxy <url>` 覆盖（脚本默认留空=自动）。
- **首次需 bootstrap**：运行 `scripts/setup_env.py` 安装 `yt-dlp / requests / pysocks / imageio-ffmpeg` 并下载 `echarts.min.js`。ffmpeg 二进制由 `imageio-ffmpeg` 提供，无需手动装。
- 仅当某环境直连与系统代理都失败时才按 `references/proxy_pip.md` 处理。

## 2. 已确认设计决策
| 维度 | 决策 |
|---|---|
| 来源 | 主要为 B站 |
| 读取 | 字幕优先 + 语音 ASR 兜底 + 关键帧多模态理解 |
| 理解/总结 | 使用运行本 skill 的 host model（多模态，零额外密钥） |
| ASR 兜底 | 可配置：`none`(仅字幕,默认) / `whisper`(本地) / `api`(云端) |
| 产出 | 单页交互式 HTML（本地 echarts） |
| 结构 | 速览卡 → 章节要点长文 → 内嵌图表 → 术语表 |
| 语言/篇幅 | 中文 · 极简要点 |
| 时间戳锚点 | 不做 |

## 3. 工作流（分阶段，agent 调度脚本）
**Stage A · bootstrap（仅首次）**
```
python scripts/setup_env.py --proxy socks5h://127.0.0.1:7897
```

**Stage 0 · 解析**
```
python scripts/parse_bilibili.py --url <BV链接> --out <workdir> --proxy socks5h://127.0.0.1:7897
```
产出：`meta.json`、`transcript.json`(含时间戳)、`transcript.txt`。无字幕时 `transcript.json` 为空，进入 Stage 1b。

**Stage 1 · 转录（仅当无字幕）**
```
python scripts/transcribe.py --url <链接> --out <workdir> --proxy ... --backend whisper
```
缺失字幕且 `backend=none` → **停下并告知用户**："该视频无字幕，需配置 ASR"，绝不编造。

**Stage 2 · 抽帧 + 画面理解（host model 多模态）**
```
python scripts/extract_frames.py --url <链接> --out <workdir> --proxy ... --frames-max 20
```
产出 `frames/frame_*.jpg` + `frames.json`。随后 agent 用 **Read 工具逐帧读取**这些 jpg，得到 `[(t, 视觉描述)]`。

**Stage 3 · 合成（host model，核心）**
输入 `meta.json + transcript + frames视觉描述`，产出 `report.json`（schema 见 §5）：
1. 类型分类：教程/实操、知识科普/讲座、产品/会议（可叠加"含数据"）。
2. 章节切分（4–8 章）：标题 + 时间区间 + 3–5 极简要点 + 可选 `frame` 插图名。
3. 速览卡：一句话结论 + 3 takeaway + 元信息。
4. 图表：`charts[]` 每项含 `title/type/option`（合法 ECharts option）。只生成视频真实内容对应的图。
5. 术语表（可选）。

**Stage 4 · 渲染**
```
python scripts/render_report.py --report <workdir>/report.json --frames-dir <workdir>/frames --template assets/report_template.html --echarts assets/echarts.min.js --out <workdir>/report.html
```
产出单页 HTML，并把 `echarts.min.js` 复制过去。

**Stage 5 · 交付**：`present_files` 预览 `<workdir>/report.html`。

## 4. 自适应图表映射
| 类型 | 图表 | ECharts |
|---|---|---|
| 教程/实操 | 步骤流程 + 操作清单 | `graph`(纵向) 或 `timeline` |
| 知识科普/讲座 | 概念关系图 + 术语表 | `graph`(树/力导) |
| 产品/会议 | 决策清单 + 要点时间线 | `timeline` / 卡片 |
| 含数据 | 柱状/趋势 | `bar` / `line` |
> 无对应素材不生成空图。

## 5. report.json Schema
```json
{
  "meta": {"bvid":"","title":"","up":"","duration_sec":0,"type":"教程/科普/会议"},
  "overview": {"summary":"","takeaways":["","",""],"cover":""},
  "chapters": [{"title":"","start":0,"end":120,"points":["",""],"frame":"frame_002.jpg"}],
  "charts": [{"title":"","type":"flow|graph|bar|line|timeline","option":{}}],
  "glossary": [{"term":"","explain":""}]
}
```

## 6. 已知坑与处置（实测沉淀）
- **术语必须区分"软字幕 / 硬字幕"**（曾因措辞笼统误导用户）：
  - yt-dlp 报"无字幕"= 没有可下载的**独立字幕轨道（软字幕）**，不代表画面上没有字。
  - 视频很可能带**硬字幕（烧录字幕）**，即文字被画进画面帧里。bilibili 的 `danmaku` 条目是**弹幕**，不是字幕。
  - 判定请用：`yt-dlp --skip-download --list-subs <url>`。
  - 对用户描述时必须讲清是哪一种，禁止笼统说"这个视频没有字幕"。
- **无旁白视频**（纯硬字幕卡 + BGM）：ASR 会输出幻觉歌词。**用 `vad_filter=True` 复跑**，
  若 `asr_lines == 0` 即确认无语音 → 转**纯视觉路线**：加密抽帧（约每 15s 一帧）读画面上的硬字幕，
  切勿采用幻觉文本。
- **yt-dlp 找不到 ffmpeg** → 音视频分离流无法合并。所有 yt-dlp 调用都要带
  `--ffmpeg-location <imageio_ffmpeg.get_ffmpeg_exe()>`（ffmpeg 不在 PATH）。
- **faster-whisper 与 PyAV 版本不兼容**（`av.open() got an unexpected keyword argument 'metadata_errors'`）
  → 不要让它内部解码：先用 imageio-ffmpeg 把音频解码成 16kHz 单声道 float32 数组，再喂给 `model.transcribe(np_array)`。
- **HF 模型下载可能失败**：faster-whisper 首次用某模型会走 HuggingFace，本机经代理常报 `WinError 10061`。
  → 优先用**已缓存的模型**并设 `HF_HUB_OFFLINE=1`（base 通常已缓存）；长音频（>30min）**用 base 控制耗时**（实测 36min 音频 base 约 5 分钟）。
- **抽帧密度**：`n = clamp(duration//15, 4, frames_max)`，短视频也保证覆盖。
- **渲染帧路径**：`render_report.py` 会把章节 `frame` 改写为 `frames/<文件名>`，与 `frames/` 目录同级。
- **bilibili-api 在本机 Py3.13 装不上**（锁定 pyyaml~=5.3，源码编译失败）→ 不要引入；元数据/字幕用 yt-dlp 即可。
- **pip 装包**：清代理变量 + `-i https://pypi.org/simple` 直连（tuna 镜像不通）。

## 7. 反模式
- 不编造视频里没有的要点/数据。
- 不为凑图表生成无关图。
- 不用运行时 CDN 加载 echarts。
- 不跳过代理直连外网。
- 不在代理不可达时静默继续。
