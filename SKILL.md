---
name: video2book
description: 输入B站视频链接，多模态读取字幕/语音与关键帧画面，由本 agent（host model）合成并生成单页交互式 HTML 速学报告（大白话中文要点 + 术语悬停释义 + 自绘矢量原理图 + ECharts 自适应图表），帮助用户快速掌握视频知识而无需看完视频。当用户给出 B站 视频链接、想"把视频变成笔记/报告/图文总结/速读"、或"快速了解这个视频讲什么"时使用。
version: 0.6.1
agent_created: true
---

# video2book —— 视频速读成书（代码包版）

## 0. 为什么是"代码包"而不是纯 md
SKILL.md 只是给 agent 的提示词，无法保证渲染质量。本 skill 把确定性工作交给脚本与固定模板：
- 解析 / 抽帧 / ASR / 渲染 → Python 脚本（可复现、样式统一）
- 报告外观 → 固定 `assets/report_template.html`（CSS 一次写好，不再临场发挥）
- 图表 → 本地内置 `echarts.min.js`（离线可用，不依赖运行时 CDN）
- 配图 → **agent 自绘 SVG 原理图**（矢量、内联、离线），截图只在确有信息价值时保留
- agent 只做它擅长的事：**多模态看图 + 总结合成 + 设计图表 + 画原理图**

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
| 产出 | 单页交互式 HTML（本地 echarts + 内联 SVG） |
| 结构 | 速览卡 → 章节要点长文（含自绘原理图）→ 内嵌图表 → 术语表 |
| 配图 | **自绘 SVG 原理图/架构图优先**；截图仅在画面本身不可替代时保留 |
| 文风 | **大白话优先**：术语不解释不进要点，解释交给术语表 + 悬停提示（§5.5 / §5.6） |
| 语言/篇幅 | 中文 · 极简要点 |
| 时间戳锚点 | 不做 |

## 3. 工作流（分阶段，agent 调度脚本）
**Stage A · bootstrap（仅首次）**
```
python scripts/setup_env.py
```

**Stage 0 · 解析**
```
python scripts/parse_bilibili.py --url <BV链接> --out <workdir>
```
产出：`meta.json`、`transcript.json`(含时间戳)、`transcript.txt`。无字幕时 `transcript.json` 为空，进入 Stage 1。

**Stage 1 · 转录（仅当无字幕）**
```
python scripts/transcribe.py --url <链接> --out <workdir> --backend whisper
```
缺失字幕且 `backend=none` → **停下并告知用户**："该视频无字幕，需配置 ASR"，绝不编造。

**Stage 2 · 抽帧 + 画面理解（host model 多模态）**
```
python scripts/extract_frames.py --url <链接> --out <workdir> --frames-max 20
```
产出 `frames/frame_*.jpg` + `frames.json`。随后 agent 用 **Read 工具逐帧读取**这些 jpg，得到 `[(t, 视觉描述)]`。
注意：抽帧的目的是**搞懂视频讲了什么**，不是"把截图塞进报告"。

**Stage 3 · 合成（host model，核心）**
输入 `meta.json + transcript + frames视觉描述`，产出 `report.json`（schema 见 §6）：
1. 类型分类：教程/实操、知识科普/讲座、产品/会议（可叠加"含数据"）。
2. 章节切分（4–8 章）：标题 + 时间区间 + 3–5 极简要点。
3. 速览卡：一句话结论 + 3 takeaway + 元信息 + `source_note`（说明来源与读法，如"硬字幕/ASR"）。
4. **配图设计**：为每章判断"读者要理解这个机制，最需要看到什么"，据此规划 2–6 张自绘原理图（见 §5）。
5. 图表：`charts[]` 每项含 `title/type/option`（合法 ECharts option）。只生成视频真实内容对应的图。
6. 术语表（可选）。

**Stage 3.5 · 画原理图（agent 手写 SVG）**
把每张图写成 `<workdir>/diagrams/<name>.svg`，然后在 `report.json` 的章节里用
`"diagrams":[{"file":"<name>.svg","caption":"这张图说明什么"}]` 引用。
规范与验收流程见 §5。**这一步不做完不要进 Stage 4。**

**Stage 4 · 渲染**
```
python scripts/render_report.py --report <workdir>/report.json \
  --frames-dir <workdir>/frames --diagrams-dir <workdir>/diagrams \
  --template assets/report_template.html --echarts assets/echarts.min.js --out <workdir>
```
产出单页 HTML：SVG 会被**内联**进 HTML（不依赖外部图片），`echarts.min.js` 复制到同级目录。
`--diagrams-dir` 缺省时自动取 `report.json` 同级的 `diagrams/`。

> **命名规则**：`--out` 给**目录**或缺省时，自动命名为 `「标题（BV号）.html」`
> （如 `一口气学会 pi-agent 的底层原理和二开实践（BV1JB8o6BEit）.html`），
> 避免所有报告都叫 `report.html` 而分不清。需要自定义文件名时，`--out` 传完整路径即可。

**Stage 5 · 交付**：`present_files` 预览生成的 HTML。

## 4. 自适应图表映射
| 类型 | 图表 | ECharts |
|---|---|---|
| 教程/实操 | 步骤流程 + 操作清单 | `graph`(纵向) 或 `timeline` |
| 知识科普/讲座 | 概念关系图 + 术语表 | `graph`(树/力导) |
| 产品/会议 | 决策清单 + 要点时间线 | `timeline` / 卡片 |
| 含数据 | 柱状/趋势 | `bar` / `line` |
> 无对应素材不生成空图。**结构/机制类内容交给 §5 的 SVG 原理图，不要硬塞进 ECharts**；
> 同一个概念不要既画 SVG 又画 ECharts 图，二选一。

## 5. 内容与配图规范（重要）
### 5.1 原则
- **默认自绘**。视频里出现的代码窗口、终端、PPT 页、人脸、logo 之类的"截图"，
  对理解知识往往**没有增量信息**（文字要点里已经说了），不要放进报告。
- **只在以下情况保留截图**（章节字段 `frame` + 必填 `frame_note` 说明"看图看什么"）：
  - 画面本身就是**数据可视化 / 图表 / 示意图**，且是视频作者的原创成果（复刻不如原图准确）；
  - 画面是**实物/界面/装置**，语言描述成本极高且容易失真；
  - 画面包含**报告正文无法用文字承载的信息**（如真实的架构全景、实验装置）。
- `frame_note` 要写清"这张图值得看什么"，禁止出现"视频画面"这类无信息量的说明。
- 一张报告里截图建议 0–2 张；其余全部自绘。
- **每张图要带足信息量**：避免「几个圆点 + 几根连线」式的大留白构图（用户会觉得"太简陋"）；
  每个框里除了名字，再给一句"它是干什么的"；图的留白不要大于内容本身。

### 5.2 画布与配色约定（与报告模板一致）
- 画布：`<svg viewBox="0 0 680 H" xmlns=... font-family="-apple-system,'PingFang SC','Microsoft YaHei',sans-serif">`，
  第一层先铺 `<rect x="0" y="0" width="680" height="H" fill="#ffffff"/>`（报告是浅色主题，禁止深底）。
- 配色（与模板同源，勿自创）：
  | 用途 | 填充 | 描边 | 说明 |
  |---|---|---|---|
  | 主色/循环/流程 | `#eaf1ff` | `#2f6bff` | 模型、步骤 |
  | 强调/扩展/警示 | `#fff3e6` | `#ff9f43` | 分支、可选、注意 |
  | 结果/工具/成功 | `#e8f8f2` | `#00a870` | 产出、执行 |
  | 中性/背景块 | `#f2f3f5` / `#f7f8fa` | `#c9cdd4` | 角色、容器 |
  | 错误 | `#fdeff0` | `#e34d59` | 报错、失效 |
  | 正文 | `#1f2329` | — | 标题 15px/600，小标题 12–13px/600 |
  | 辅助文字 | `#646a73` | — | 说明 11px；图内小字最小 10px |
- 字号：标题 15、小标题 12–13、正文 11、图内极限小字 10。**不要再小**。

### 5.3 画法要点（实测踩过）
- **先把坐标算出来再写**：矩形起止 x、相邻间距、箭头起终点都先心算一遍，避免框重叠 / 文字溢出。
- 文字宽度估算：中文 ≈ 1.0 × 字号，ASCII ≈ 0.55 × 字号。**框内文字宽度必须 < 框宽 - 12**。
- 需要居中的文字用 `text-anchor="middle"`，别靠手数空格。
- 箭头用 `<marker>`；`refX` 取 9、`markerWidth` 10 时端点画到目标边框即可。
- 回边（循环线）**不要穿过其他方框**——改走画布外侧留白。
- 弧线（`<path>` 曲线）的顶点会跑到控制点 y 的约 0.75 处，标签要放到弧线下方，别压在线上。
- `defs` 里的 `id` 在同一份 HTML 里会全局冲突：多张图内联进同一页时，**箭头 marker 的 id 必须各不相同**
  （如 `ah`/`ahb`/`aho`/`ahrl`/`ahg`）。否则后加载的图会抢走先加载图的箭头样式。

### 5.4 验收（强制步骤，别跳）
写完 SVG 必须**渲染出来用眼睛看**，不能凭想象交付：
```
# 单张放大验收（force-device-scale-factor=2 让字看得清）
& "<Chrome路径>" --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
  --force-device-scale-factor=2 --window-size=700,360 \
  --screenshot="<workdir>\_shot.png" "file:///<workdir>/diagrams/<name>.svg"
```
然后用 **Read 工具读这张 png**，逐张确认：
1. 有没有文字出框 / 压线 / 与方框重叠；2. 箭头方向对不对；3. 回边有没有穿过方框；
4. 深色底或看不清的字（浅色主题下必须是浅底深字）。发现问题就改，改完再截一次。

### 5.5 要点必须说人话（否则报告等于没写）
用户反馈原话：「像这句，好多词，看不懂」——被点名的句子长这样：
> ① 配置模型：必须 OpenAI 兼容——POST {baseUrl}/chat/completions、必须支持 SSE 流式(stream:true)、Bearer 鉴权；内网不满足就上转换层

**唯一的判断标准**：一个完全不懂这个领域的人，读一遍能不能说出「这是在说什么事」。

硬规则：
1. **一条要点只说一件事**。上面那句用分号并列了 4 个概念 → 必须拆成 2–3 条。
2. **先白话，后术语**：先讲「要干什么、为什么」，术语只在必要时出现。
   - ❌ `必须支持 SSE 流式(stream:true)`
   - ✅ `支持边生成边吐字的流式返回`
3. **禁止把参数名 / 函数名 / 英文缩写直接扔进要点**（`{baseUrl}/chat/completions`、`stream:true` 这类）。
   它们应该挪进术语表的 `explain`，要点里说「接口格式对得上」就够了。
4. 一条尽量 ≤ 45 个汉字，里面不要出现 3 个以上陌生的词。
5. 章节标题也用白话：❌「原理2+3：token、上下文窗口与 BPE 分词」
   ✅「原理二三：输入的字要先被切块，且它能记住的量有上限」。
6. 宁可少说一句，也不要写得像 API 文档。
7. **图内文字同样要说人话**：SVG 里的字没法悬停解释，术语要么不用、要么就地用人话讲清
   （❌ `SSE 流式 + Bearer` → ✅ `接口格式得跟 OpenAI 保持一致`；`回调带 ctx` → `能拦、能改`）。

**改写示范**（同一件事，两种写法）：
> ❌ `① 配置模型：必须 OpenAI 兼容——POST {baseUrl}/chat/completions、必须支持 SSE 流式(stream:true)、Bearer 鉴权；内网不满足就上转换层`
> ✅ `第一步换成你自己的模型：配置里填地址就行 —— 但对方得是 OpenAI 兼容的接口`
> ✅ `公司内网的模型对不上这套接口，就在中间加一层转换服务翻译一下`

### 5.6 术语自动标注（渲染器已实现，你只需把术语写进 glossary）
- `render_report.py` 会把 `overview.summary / takeaways` 与各章 `points` 里出现的术语，自动包成
  `<abbr class="gl" title="短释义">术语</abbr>`，鼠标悬停即显释义。**正文因此不必自我解释，可以保持白话。**
- 术语条目字段：
  ```json
  {"term":"KV 缓存","alias":["前缀缓存","提示词缓存"],
   "def":"悬停显示的短释义（一句话）","explain":"底部术语表里的完整解释"}
  ```
  - `alias`：同一概念在正文里的其他写法（缩写、中文别称、英文名）。**正文里出现哪种写法就写进 alias**，
    否则不会被标注。
  - `def` 给悬停用（短）；省略 `def` 时悬停退回显示 `explain`。
- 匹配规则：术语（含别名）长度须 ≥ 2 字符；按长度从长到短替换，避免「上下文」抢在「上下文窗口」前面。
- 所以写作分工是：**要点里只出现白话主语 + 必要的术语名，解释一律交给术语表**。

## 6. report.json Schema
```json
{
  "meta": {"bvid":"","title":"","up":"","duration_sec":0,"type":"教程/科普/会议","source_note":""},
  "overview": {"summary":"","takeaways":["","",""]},
  "chapters": [
    {
      "title":"", "start":0, "end":120,
      "points":["",""],
      "diagrams":[{"file":"arch_layers.svg","caption":"这张图说明什么"}],
      "frame":"frame_008.jpg",
      "frame_note":"仅当截图不可替代时才有；写清看图要看什么"
    }
  ],
  "charts": [{"title":"","type":"flow|graph|bar|line|timeline|radar","option":{}}],
  "glossary": [{"term":"","alias":["正文里的其他写法"],"def":"悬停显示的短释义","explain":"术语表里的完整解释"}]
}
```
- `diagrams` 里的 `file` 只写文件名，脚本到 `--diagrams-dir`（默认 `<workdir>/diagrams`）里找。
- `diagrams` / `frame` / `points` 都是可选的，但**一章至少要有点要或图**。
- `frame` 与 `frame_note` 必须成对出现。
- `glossary` 不只是术语表：它同时驱动正文里的**悬停释义**（§5.6）。**正文写到的概念就要收进 glossary**，
  把悬停/别名的写法对齐，否则读者看到的还是"陌生的词"。

## 7. 已知坑与处置（实测沉淀）
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
- **Windows PowerShell 里跑脚本**：别用 here-string 拼带引号的 Python；把脚本写成文件再执行。
  Chrome/脚本的中文路径没问题，但 stdout 经 PowerShell 重定向会乱码 —— 需要读输出就让脚本自己写 UTF-8 日志文件。

## 8. 反模式
- 不编造视频里没有的要点/数据。
- **不把术语、参数名、函数名不解释地堆进要点**（用户直接反馈过"好多词，看不懂"）；一条要点不塞 3 个以上概念。
- 不让要点长成 API 文档：先讲人话，解释交给术语表 + 悬停释义。
- **不把视频截图当配图堆进报告**（除非满足 §5.1 的三条保留条件，且写了 `frame_note`）。
- 不为凑图表生成无关图；同一个概念不重复画（SVG 与 ECharts 二选一）。
- 不用运行时 CDN 加载 echarts；不引用外部图片 URL（SVG 一律内联）。
- SVG 图不验收就交付（必须走 §5.4 截图肉眼检查）。
- 不在代理不可达时静默继续。
