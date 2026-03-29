# Amazon 订单下单时间分析工具 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个基于 Flask 的 Web 工具，读取 Amazon 订单 Excel，分析下单时间分布并生成分时出价建议。

**Architecture:** Flask 后端提供两个 API（`/api/data` 和 `/api/upload`），使用 pandas 处理 Excel 数据并返回聚合 JSON；单页前端用 Chart.js 渲染四张图表和出价建议表，支持上传新文件后无刷新更新。

**Tech Stack:** Python 3, Flask, pandas, openpyxl, Chart.js (CDN)

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `requirements.txt` | 声明 Python 依赖 |
| `app.py` | Flask 主程序：数据加载、聚合计算、API 路由 |
| `templates/index.html` | 单页前端：Chart.js 图表 + 出价建议表 + 上传按钮 |

---

## Task 1: 创建 requirements.txt

**Files:**
- Create: `requirements.txt`

- [ ] **Step 1: 写入依赖文件**

```
flask
pandas
openpyxl
```

保存为 `requirements.txt`。

- [ ] **Step 2: 安装依赖并验证**

```bash
pip install -r requirements.txt
python -c "import flask, pandas, openpyxl; print('OK')"
```

期望输出：`OK`

- [ ] **Step 3: Commit**

```bash
git init
git add requirements.txt
git commit -m "chore: add requirements.txt"
```

---

## Task 2: 实现 Flask 后端 app.py

**Files:**
- Create: `app.py`

### 2a: 数据加载与聚合函数

- [ ] **Step 1: 在 `app.py` 中写核心数据处理函数**

创建文件 `app.py`，内容如下（完整）：

```python
import os
import json
from flask import Flask, request, jsonify, render_template
import pandas as pd
from werkzeug.utils import secure_filename

app = Flask(__name__)

DATA_PATH = os.path.join('订单数据', '鸿锐美国订单汇总.xlsx')
UPLOAD_FOLDER = '订单数据'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


def load_and_aggregate(filepath):
    """读取 Excel，过滤 Shipped 订单，计算各维度聚合数据。"""
    # 工作表名为 '1'，第2行（index=1）为空行，从第3行（header=2 → skiprows）起为数据
    # header=0 表示第1行为列名，skiprows=[1] 跳过第2行空行
    df = pd.read_excel(filepath, sheet_name='1', header=0, skiprows=[1])

    # 过滤已发货订单
    df = df[df['order-status'] == 'Shipped'].copy()

    # 解析 purchase-date 为 datetime（UTC，不转换时区）
    df['purchase-date'] = pd.to_datetime(df['purchase-date'], utc=True)

    # ---- 小时分布（0-23）----
    df['hour'] = df['purchase-date'].dt.hour
    hourly_series = df.groupby('hour').size().reindex(range(24), fill_value=0)
    hourly = hourly_series.tolist()

    # ---- 星期分布（0=周一 ~ 6=周日）----
    df['weekday'] = df['purchase-date'].dt.dayofweek
    weekday_series = df.groupby('weekday').size().reindex(range(7), fill_value=0)
    weekday = weekday_series.tolist()

    # ---- 月度趋势 ----
    df['month'] = df['purchase-date'].dt.to_period('M').astype(str)
    monthly_series = df.groupby('month').size().sort_index()
    monthly = {'labels': monthly_series.index.tolist(), 'data': monthly_series.tolist()}

    # ---- 7×24 热力图（星期 × 小时）----
    heatmap_df = df.groupby(['weekday', 'hour']).size().reset_index(name='count')
    # 构建 7 行 × 24 列矩阵
    matrix = [[0] * 24 for _ in range(7)]
    for _, row in heatmap_df.iterrows():
        matrix[int(row['weekday'])][int(row['hour'])] = int(row['count'])
    heatmap = matrix

    # ---- 汇总信息 ----
    total = len(df)
    date_min = df['purchase-date'].dt.date.min().isoformat()
    date_max = df['purchase-date'].dt.date.max().isoformat()
    date_range_days = (df['purchase-date'].dt.date.max() - df['purchase-date'].dt.date.min()).days + 1
    daily_avg = round(total / date_range_days, 1) if date_range_days > 0 else 0
    peak_hour = int(hourly_series.idxmax())
    summary = {
        'total': total,
        'date_range': f"{date_min} ~ {date_max}",
        'daily_avg': daily_avg,
        'peak_hour': peak_hour,
    }

    # ---- 分时出价建议 ----
    mean_orders = hourly_series.mean()
    high_threshold = mean_orders * 1.3
    low_threshold = mean_orders * 0.7

    def classify(count):
        if count >= high_threshold:
            return 'peak'
        elif count < low_threshold:
            return 'trough'
        else:
            return 'normal'

    # 将连续相同类别的小时合并为时段
    segments = []
    current_type = classify(hourly[0])
    start_hour = 0
    for h in range(1, 24):
        t = classify(hourly[h])
        if t != current_type:
            segments.append({'start': start_hour, 'end': h, 'type': current_type})
            current_type = t
            start_hour = h
    segments.append({'start': start_hour, 'end': 24, 'type': current_type})

    bid_suggestion = []
    label_map = {'peak': '高峰', 'normal': '普通', 'trough': '低谷'}
    action_map = {
        'peak': '出价 +20%，建议增加预算',
        'normal': '维持默认出价',
        'trough': '出价 -20%，建议减少预算',
    }
    for seg in segments:
        bid_suggestion.append({
            'range': f"{seg['start']:02d}:00-{seg['end']:02d}:00",
            'type': label_map[seg['type']],
            'action': action_map[seg['type']],
        })

    return {
        'hourly': hourly,
        'weekday': weekday,
        'monthly': monthly,
        'heatmap': heatmap,
        'summary': summary,
        'bid_suggestion': bid_suggestion,
    }


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/data')
def api_data():
    try:
        data = load_and_aggregate(DATA_PATH)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/upload', methods=['POST'])
def api_upload():
    if 'file' not in request.files:
        return jsonify({'error': '未找到文件字段 file'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '未选择文件'}), 400
    filename = secure_filename(file.filename)
    if not filename.endswith('.xlsx'):
        return jsonify({'error': '仅支持 .xlsx 格式'}), 400
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(save_path)
    try:
        data = load_and_aggregate(save_path)
        # 更新默认数据路径
        global DATA_PATH
        DATA_PATH = save_path
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
```

- [ ] **Step 2: 创建 templates 目录**

```bash
mkdir -p templates
```

- [ ] **Step 3: 用 Python 快速验证数据加载逻辑**

```bash
python - <<'EOF'
from app import load_and_aggregate
data = load_and_aggregate('订单数据/鸿锐美国订单汇总.xlsx')
print("总订单数:", data['summary']['total'])
print("高峰小时:", data['summary']['peak_hour'])
print("月度标签:", data['monthly']['labels'][:3])
print("热力图尺寸:", len(data['heatmap']), "×", len(data['heatmap'][0]))
print("出价建议段数:", len(data['bid_suggestion']))
EOF
```

期望输出类似：
```
总订单数: 1390
高峰小时: <0-23 之间的整数>
月度标签: ['2025-07', '2025-08', '2025-09']
热力图尺寸: 7 × 24
出价建议段数: <若干段>
```

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: add Flask backend with data aggregation and API routes"
```

---

## Task 3: 实现前端 templates/index.html

**Files:**
- Create: `templates/index.html`

- [ ] **Step 1: 创建完整的 HTML 前端文件**

创建 `templates/index.html`，内容如下：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Amazon 订单下单时间分析</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #f5f6fa; color: #2d3436; }
    header { background: #2d3436; color: #fff; padding: 16px 24px;
             display: flex; justify-content: space-between; align-items: center; }
    header h1 { font-size: 18px; }
    #upload-btn { background: #fdcb6e; color: #2d3436; border: none;
                  padding: 8px 16px; border-radius: 6px; cursor: pointer;
                  font-weight: 600; font-size: 14px; }
    #upload-btn:hover { background: #e17055; color: #fff; }
    #file-input { display: none; }
    .cards { display: flex; gap: 16px; padding: 20px 24px; flex-wrap: wrap; }
    .card { background: #fff; border-radius: 10px; padding: 20px 24px;
            flex: 1; min-width: 160px; box-shadow: 0 2px 8px rgba(0,0,0,.06); }
    .card .label { font-size: 12px; color: #636e72; margin-bottom: 6px; }
    .card .value { font-size: 28px; font-weight: 700; color: #2d3436; }
    .charts-grid { display: grid; grid-template-columns: 1fr 1fr;
                   gap: 20px; padding: 0 24px 20px; }
    .chart-box { background: #fff; border-radius: 10px; padding: 20px;
                 box-shadow: 0 2px 8px rgba(0,0,0,.06); }
    .chart-box h2 { font-size: 14px; color: #636e72; margin-bottom: 12px; }
    .heatmap-container { overflow-x: auto; }
    table.heatmap { border-collapse: collapse; font-size: 11px; width: 100%; }
    table.heatmap th, table.heatmap td {
      padding: 4px 3px; text-align: center; min-width: 28px; }
    table.heatmap th { color: #636e72; font-weight: 500; }
    table.heatmap td { border-radius: 3px; }
    .bid-section { padding: 0 24px 24px; }
    .bid-section h2 { font-size: 14px; color: #636e72; margin-bottom: 12px; }
    table.bid-table { width: 100%; border-collapse: collapse;
                      background: #fff; border-radius: 10px; overflow: hidden;
                      box-shadow: 0 2px 8px rgba(0,0,0,.06); }
    table.bid-table th { background: #2d3436; color: #fff; padding: 10px 16px;
                         font-size: 13px; text-align: left; }
    table.bid-table td { padding: 10px 16px; font-size: 13px;
                         border-bottom: 1px solid #f0f0f0; }
    table.bid-table tr:last-child td { border-bottom: none; }
    .tag-peak { background: #ff7675; color: #fff; border-radius: 4px;
                padding: 2px 8px; font-size: 12px; }
    .tag-normal { background: #74b9ff; color: #fff; border-radius: 4px;
                  padding: 2px 8px; font-size: 12px; }
    .tag-trough { background: #b2bec3; color: #fff; border-radius: 4px;
                  padding: 2px 8px; font-size: 12px; }
    @media (max-width: 768px) {
      .charts-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
<header>
  <h1>Amazon 订单下单时间分析</h1>
  <div>
    <button id="upload-btn" onclick="document.getElementById('file-input').click()">上传新数据</button>
    <input type="file" id="file-input" accept=".xlsx" onchange="uploadFile(this)" />
  </div>
</header>

<div class="cards">
  <div class="card"><div class="label">总订单数（已发货）</div><div class="value" id="c-total">-</div></div>
  <div class="card"><div class="label">数据时间范围</div><div class="value" id="c-range" style="font-size:16px">-</div></div>
  <div class="card"><div class="label">日均订单量</div><div class="value" id="c-avg">-</div></div>
  <div class="card"><div class="label">最高峰小时（UTC）</div><div class="value" id="c-peak">-</div></div>
</div>

<div class="charts-grid">
  <div class="chart-box">
    <h2>24小时下单分布（UTC）</h2>
    <canvas id="chart-hourly"></canvas>
  </div>
  <div class="chart-box">
    <h2>星期下单分布</h2>
    <canvas id="chart-weekday"></canvas>
  </div>
  <div class="chart-box">
    <h2>月度订单趋势</h2>
    <canvas id="chart-monthly"></canvas>
  </div>
  <div class="chart-box">
    <h2>周内每小时热力图（行=星期，列=小时，UTC）</h2>
    <div class="heatmap-container" id="heatmap-wrap"></div>
  </div>
</div>

<div class="bid-section">
  <h2>分时出价建议（基于UTC小时）</h2>
  <table class="bid-table">
    <thead><tr><th>时段（UTC）</th><th>类型</th><th>建议操作</th></tr></thead>
    <tbody id="bid-tbody"></tbody>
  </table>
</div>

<script>
  const WEEKDAY_LABELS = ['周一','周二','周三','周四','周五','周六','周日'];
  let charts = {};

  async function fetchData() {
    const res = await fetch('/api/data');
    if (!res.ok) { alert('数据加载失败'); return; }
    return res.json();
  }

  async function uploadFile(input) {
    const file = input.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch('/api/upload', { method: 'POST', body: fd });
    const data = await res.json();
    if (data.error) { alert('上传失败: ' + data.error); return; }
    renderAll(data);
  }

  function renderSummary(s) {
    document.getElementById('c-total').textContent = s.total.toLocaleString();
    document.getElementById('c-range').textContent = s.date_range;
    document.getElementById('c-avg').textContent = s.daily_avg;
    document.getElementById('c-peak').textContent = String(s.peak_hour).padStart(2,'0') + ':00';
  }

  function renderHourly(hourly) {
    // 前3名标红
    const sorted = [...hourly].sort((a,b) => b-a);
    const top3 = sorted.slice(0,3);
    const colors = hourly.map(v => top3.includes(v) ? '#e17055' : '#74b9ff');
    const labels = Array.from({length:24}, (_,i) => String(i).padStart(2,'0')+':00');
    destroyAndCreate('chart-hourly', 'bar', {
      labels,
      datasets: [{ label: '订单量', data: hourly, backgroundColor: colors, borderRadius: 4 }]
    }, { plugins: { legend: { display: false } } });
  }

  function renderWeekday(weekday) {
    destroyAndCreate('chart-weekday', 'bar', {
      labels: WEEKDAY_LABELS,
      datasets: [{ label: '订单量', data: weekday,
                   backgroundColor: '#a29bfe', borderRadius: 4 }]
    }, { plugins: { legend: { display: false } } });
  }

  function renderMonthly(monthly) {
    destroyAndCreate('chart-monthly', 'line', {
      labels: monthly.labels,
      datasets: [{ label: '订单量', data: monthly.data,
                   borderColor: '#00b894', backgroundColor: 'rgba(0,184,148,.1)',
                   fill: true, tension: 0.3, pointRadius: 4 }]
    }, { plugins: { legend: { display: false } } });
  }

  function renderHeatmap(matrix) {
    // 找最大值用于颜色归一化
    const maxVal = Math.max(...matrix.flat());
    const hours = Array.from({length:24}, (_,i) => String(i).padStart(2,'0'));
    let html = '<table class="heatmap"><thead><tr><th></th>';
    hours.forEach(h => { html += `<th>${h}</th>`; });
    html += '</tr></thead><tbody>';
    matrix.forEach((row, wi) => {
      html += `<tr><th>${WEEKDAY_LABELS[wi]}</th>`;
      row.forEach(v => {
        const alpha = maxVal > 0 ? (v / maxVal) : 0;
        const bg = `rgba(225,112,85,${alpha.toFixed(2)})`;
        const fg = alpha > 0.5 ? '#fff' : '#2d3436';
        html += `<td style="background:${bg};color:${fg}" title="${v}">${v||''}</td>`;
      });
      html += '</tr>';
    });
    html += '</tbody></table>';
    document.getElementById('heatmap-wrap').innerHTML = html;
  }

  function renderBidSuggestion(suggestions) {
    const tagClass = { '高峰': 'tag-peak', '普通': 'tag-normal', '低谷': 'tag-trough' };
    const tbody = document.getElementById('bid-tbody');
    tbody.innerHTML = suggestions.map(s => `
      <tr>
        <td>${s.range}</td>
        <td><span class="${tagClass[s.type]}">${s.type}</span></td>
        <td>${s.action}</td>
      </tr>`).join('');
  }

  function destroyAndCreate(id, type, data, options) {
    if (charts[id]) charts[id].destroy();
    const ctx = document.getElementById(id).getContext('2d');
    charts[id] = new Chart(ctx, {
      type,
      data,
      options: {
        responsive: true,
        plugins: { tooltip: { enabled: true }, ...((options||{}).plugins||{}) },
        ...(options||{})
      }
    });
  }

  function renderAll(data) {
    renderSummary(data.summary);
    renderHourly(data.hourly);
    renderWeekday(data.weekday);
    renderMonthly(data.monthly);
    renderHeatmap(data.heatmap);
    renderBidSuggestion(data.bid_suggestion);
  }

  fetchData().then(data => { if (data) renderAll(data); });
</script>
</body>
</html>
```

- [ ] **Step 2: 启动 Flask 并在浏览器验证**

```bash
python app.py
```

打开 http://localhost:5000，验证：
- 4 个概览卡片显示正确数值（总订单数应为 1390）
- 24小时分布柱状图渲染，前3高峰标红
- 星期分布柱状图渲染
- 月度折线图渲染
- 热力图以颜色深浅显示密度
- 分时出价建议表显示高峰/普通/低谷时段

- [ ] **Step 3: 验证上传功能**

在页面右上角点击「上传新数据」，选择同一个 `鸿锐美国订单汇总.xlsx`，确认图表数据与初始加载一致，页面无刷新。

- [ ] **Step 4: Commit**

```bash
git add templates/index.html
git commit -m "feat: add single-page frontend with Chart.js and bid suggestion table"
```

---

## Task 4: 最终集成验收

**Files:** 无新文件，验收现有代码

- [ ] **Step 1: 确认项目文件结构**

```bash
ls -1 .
# 期望：app.py  requirements.txt  templates/  订单数据/  docs/
ls templates/
# 期望：index.html
```

- [ ] **Step 2: 全流程端到端验证**

```bash
python app.py
```

使用 curl 验证 API：
```bash
curl -s http://localhost:5000/api/data | python -m json.tool | head -40
```

期望：看到包含 `hourly`、`weekday`、`monthly`、`heatmap`、`summary`、`bid_suggestion` 的 JSON。

- [ ] **Step 3: 最终 Commit**

```bash
git add .
git commit -m "feat: complete Amazon order time analysis tool (Flask + Chart.js)"
```

---

## 自检：Spec 覆盖确认

| Spec 需求 | 实现任务 |
|-----------|----------|
| 读取 `订单数据/鸿锐美国订单汇总.xlsx` 工作表 `1` | Task 2 `load_and_aggregate` |
| 跳过第2行空行 | Task 2 `skiprows=[1]` |
| 过滤 `order-status == "Shipped"` | Task 2 过滤逻辑 |
| UTC 时间，不做转换 | Task 2 `utc=True`，不调用 `.tz_convert()` |
| hourly / weekday / monthly / heatmap / summary / bid_suggestion | Task 2 全部实现 |
| `GET /` → index.html | Task 2 `index()` 路由 |
| `GET /api/data` → 聚合 JSON | Task 2 `api_data()` |
| `POST /api/upload` → 替换数据源 | Task 2 `api_upload()` |
| 24小时柱状图，前3高峰标红 | Task 3 `renderHourly` |
| 星期分布柱状图 | Task 3 `renderWeekday` |
| 月度折线图 | Task 3 `renderMonthly` |
| 7×24 热力图 | Task 3 `renderHeatmap` |
| 4个概览卡片 | Task 3 `renderSummary` |
| 分时出价建议表 | Task 3 `renderBidSuggestion` |
| 上传后无刷新更新图表 | Task 3 `uploadFile` → `renderAll` |
| 高峰≥均值×1.3，低谷<均值×0.7 | Task 2 `classify` 函数 |
| 连续时段合并输出 | Task 2 `segments` 循环 |
