#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stage 4 · 渲染：把 agent 合成的 report.json 套进固定模板，生成单页交互式 HTML。
- 读取 assets/report_template.html（含 /*__DATA__*/ 与 /*__INIT__*/ 占位）
- 注入 window.__REPORT__ 与初始化 JS（含 ECharts setOption）
- 把 echarts.min.js 复制到输出目录旁，保证离线可用
"""
import argparse
import json
import os
import re
import shutil


ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def safe_filename(text, maxlen=40):
    """去掉 Windows 非法文件名字符并限长。"""
    t = ILLEGAL_CHARS.sub("", (text or "").strip())
    t = re.sub(r"\s+", " ", t)
    return t[:maxlen].rstrip(". ")


def auto_filename(meta):
    """按「标题（BV号）.html」生成可读文件名，避免所有报告都叫 report.html。"""
    title = safe_filename(meta.get("title", ""))
    bvid = safe_filename(meta.get("bvid", ""))
    if title and bvid:
        return f"{title}（{bvid}）.html"
    return (title or bvid or "report") + ".html"


INIT_JS = r"""
(function () {
  var R = window.__REPORT__;
  function esc(s){ s = s==null?'':String(s); return s.replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];}); }
  function fmtDur(s){ s=Math.round(s||0); var m=Math.floor(s/60), sec=s%60; return m+'分'+sec+'秒'; }
  function fmtRange(a,b){ return fmtDur(a)+' – '+fmtDur(b); }

  // 速览卡
  var ov = document.getElementById('overview');
  var ovHtml = '<h1>'+esc(R.meta&&R.meta.title)+'</h1>';
  ovHtml += '<div class="meta">'+esc(R.meta&&R.meta.up)+' · '+fmtDur(R.meta&&R.meta.duration_sec)+' · 类型：'+esc(R.meta&&R.meta.type)+'</div>';
  if (R.meta && R.meta.source_note){
    ovHtml += '<div class="note">'+esc(R.meta.source_note)+'</div>';
  }
  if (R.overview){
    ovHtml += '<div class="summary">'+esc(R.overview.summary)+'</div>';
    if (R.overview.takeaways && R.overview.takeaways.length){
      ovHtml += '<ul class="takeaways">'+R.overview.takeaways.map(function(t){return '<li>'+esc(t)+'</li>';}).join('')+'</ul>';
    }
  }
  ov.innerHTML = ovHtml;

  // 章节
  var ch = document.getElementById('chapters');
  if (R.chapters){
    ch.innerHTML = R.chapters.map(function(c){
      var html = '<article class="chapter"><h2>'+esc(c.title)+'<span class="time">'+fmtRange(c.start,c.end)+'</span></h2>';
      if (c.points && c.points.length){
        html += '<ul>'+c.points.map(function(p){return '<li>'+esc(p)+'</li>';}).join('')+'</ul>';
      }
      if (c.frame){ html += '<img class="frame" src="'+esc(c.frame)+'" alt="关键帧">'; }
      html += '</article>';
      return html;
    }).join('');
  }

  // 图表
  var ct = document.getElementById('charts');
  if (R.charts && R.charts.length){
    ct.innerHTML = R.charts.map(function(g,i){ return '<div class="chart-block"><h3>'+esc(g.title)+'</h3><div class="chart" id="chart'+i+'"></div></div>'; }).join('');
    R.charts.forEach(function(g,i){
      var el = document.getElementById('chart'+i);
      if(!el) return;
      var chart = echarts.init(el);
      chart.setOption(g.option||{});
      window.addEventListener('resize', function(){ chart.resize(); });
    });
  } else {
    ct.innerHTML = '<p class="muted">（本视频未生成图表）</p>';
  }

  // 术语表
  var gl = document.getElementById('glossary');
  if (R.glossary && R.glossary.length){
    gl.innerHTML = '<h2>术语表</h2>' + R.glossary.map(function(x){
      return '<div class="term"><b>'+esc(x.term)+'</b>：'+esc(x.explain)+'</div>';
    }).join('');
  }
})();
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--frames-dir", default="")
    ap.add_argument("--template", required=True)
    ap.add_argument("--echarts", required=True)
    ap.add_argument("--out", default="",
                    help="输出 html 路径，或目录；留空/给目录时自动命名为「标题（BV号）.html」")
    args = ap.parse_args()

    with open(args.report, "r", encoding="utf-8") as f:
        report = json.load(f)
    with open(args.template, "r", encoding="utf-8") as f:
        tpl = f.read()

    # 章节里的 frame 改为相对输出目录的路径（frames 目录与 report.html 同级时用 frames/xxx.jpg）
    if args.frames_dir:
        frames_base = os.path.basename(os.path.normpath(args.frames_dir))
        for c in report.get("chapters", []):
            if c.get("frame"):
                c["frame"] = frames_base + "/" + os.path.basename(c["frame"])

    data_js = json.dumps(report, ensure_ascii=False)
    html = tpl.replace("/*__DATA__*/", data_js).replace("/*__INIT__*/", INIT_JS)

    # 输出路径：--out 为目录或缺省时，自动按「标题（BV号）.html」命名
    if not args.out or os.path.isdir(args.out):
        base_dir = args.out if args.out else "."
        out_path = os.path.join(base_dir, auto_filename(report.get("meta", {})))
    else:
        out_path = args.out

    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    # 复制 echarts 到输出目录旁
    if os.path.exists(args.echarts):
        shutil.copy(args.echarts, os.path.join(out_dir, "echarts.min.js"))

    print(json.dumps({"out": out_path, "charts": len(report.get("charts", [])),
                      "chapters": len(report.get("chapters", []))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
