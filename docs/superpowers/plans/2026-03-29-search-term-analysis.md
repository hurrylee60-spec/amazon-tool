# 搜索词分析工具 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 Flask 应用中新增搜索词分析页面，支持 CSV 上传、搜索词效果排名、烧钱词识别、操作建议自动标注。

**Architecture:** 扩展 app.py 新增 3 个路由（/search、/api/search-data、/api/search-upload），新建 templates/search.html 前端页面。数据用 pandas 按搜索词分组汇总，操作建议在前端基于目标 ACOS 实时计算。两个页面通过 header 导航互相跳转。

**Tech Stack:** Python 3, Flask, pandas, 原生 JS

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `app.py` | 修改 | 新增搜索词相关的 3 个路由和数据处理函数 |
| `templates/search.html` | 创建 | 搜索词分析前端页面 |
| `templates/index.html` | 修改 | header 加导航链接 |

---

## Task 1: 在 app.py 中新增搜索词后端逻辑

**Files:**
- Modify: `app.py`

- [ ] **Step 1: 在 app.py 顶部添加搜索词数据路径变量**

在 `UPLOAD_FOLDER = '订单数据'` 行之后添加：

```python
SEARCH_DATA_PATH = os.path.join('搜索词数据', 'Targeting_-_03_24_2026T20_47_30.csv')
SEARCH_UPLOAD_FOLDER = '搜索词数据'
```

- [ ] **Step 2: 添加搜索词聚合函数**

在 `load_and_aggregate` 函数之后添加：

```python
def load_and_aggregate_search(filepath, campaign=None):
    """读取搜索词 CSV，按搜索词分组汇总，返回聚合数据。"""
    df = pd.read_csv(filepath, encoding='utf-8-sig')

    # 提取广告活动列表（去重）
    campaigns = sorted(df['广告活动名称'].dropna().unique().tolist())

    # 按广告活动筛选
    if campaign and campaign != '全部':
        df = df[df['广告活动名称'] == campaign]

    # 数值列清洗：去掉百分号，转为数值
    for col in ['展示量', '点击量', '总成本', '购买量', '销售额']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # 按搜索词分组汇总
    grouped = df.groupby('搜索词').agg({
        '展示量': 'sum',
        '点击量': 'sum',
        '总成本': 'sum',
        '购买量': 'sum',
        '销售额': 'sum',
    }).reset_index()

    # 重新计算比率
    grouped['点击率'] = (grouped['点击量'] / grouped['展示量'] * 100).round(2).fillna(0)
    grouped['acos'] = (grouped['总成本'] / grouped['销售额'] * 100).round(2)
    grouped['acos'] = grouped['acos'].replace([float('inf')], -1).fillna(-1)
    grouped['roas'] = (grouped['销售额'] / grouped['总成本']).round(2)
    grouped['roas'] = grouped['roas'].replace([float('inf')], -1).fillna(-1)

    # 汇总统计
    total_cost = round(float(grouped['总成本'].sum()), 2)
    total_sales = round(float(grouped['销售额'].sum()), 2)
    total_purchases = int(grouped['购买量'].sum())
    summary = {
        'total_terms': len(grouped),
        'total_cost': total_cost,
        'total_sales': total_sales,
        'total_purchases': total_purchases,
        'overall_acos': round(total_cost / total_sales * 100, 2) if total_sales > 0 else -1,
        'overall_roas': round(total_sales / total_cost, 2) if total_cost > 0 else -1,
    }

    # 搜索词明细列表（按花费降序）
    grouped = grouped.sort_values('总成本', ascending=False)
    terms = []
    for _, row in grouped.iterrows():
        terms.append({
            'term': row['搜索词'],
            'impressions': int(row['展示量']),
            'clicks': int(row['点击量']),
            'ctr': float(row['点击率']),
            'cost': round(float(row['总成本']), 2),
            'purchases': int(row['购买量']),
            'sales': round(float(row['销售额']), 2),
            'acos': float(row['acos']),
            'roas': float(row['roas']),
        })

    return {
        'summary': summary,
        'terms': terms,
        'campaigns': campaigns,
    }
```

- [ ] **Step 3: 添加 3 个路由**

在现有路由之后、`if __name__` 之前添加：

```python
@app.route('/search')
def search_page():
    return render_template('search.html')


@app.route('/api/search-data')
def api_search_data():
    campaign = request.args.get('campaign', None)
    if not os.path.exists(SEARCH_DATA_PATH):
        return jsonify({'empty': True}), 200
    try:
        data = load_and_aggregate_search(SEARCH_DATA_PATH, campaign)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/search-upload', methods=['POST'])
def api_search_upload():
    if 'file' not in request.files:
        return jsonify({'error': '未找到文件字段 file'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '未选择文件'}), 400
    original_name = file.filename
    if not original_name.endswith('.csv'):
        return jsonify({'error': '仅支持 .csv 格式'}), 400
    filename = f"search_upload_{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}.csv"
    os.makedirs(SEARCH_UPLOAD_FOLDER, exist_ok=True)
    save_path = os.path.join(SEARCH_UPLOAD_FOLDER, filename)
    file.save(save_path)
    try:
        data = load_and_aggregate_search(save_path)
        global SEARCH_DATA_PATH
        SEARCH_DATA_PATH = save_path
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
```

- [ ] **Step 4: 验证后端逻辑**

```bash
cd /Users/hongruili/Documents/amazon-tool
python3 - <<'EOF'
from app import load_and_aggregate_search
data = load_and_aggregate_search('搜索词数据/Targeting_-_03_24_2026T20_47_30.csv')
print("搜索词数:", data['summary']['total_terms'])
print("总花费:", data['summary']['total_cost'])
print("总销售额:", data['summary']['total_sales'])
print("广告活动数:", len(data['campaigns']))
print("前3个搜索词:", [t['term'] for t in data['terms'][:3]])
EOF
```

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: add search term analysis backend routes and aggregation"
```

---

## Task 2: 创建搜索词分析前端 templates/search.html

**Files:**
- Create: `templates/search.html`

- [ ] **Step 1: 创建完整的 search.html 文件**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Amazon 搜索词分析</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #f5f6fa; color: #2d3436; }
    header { background: #2d3436; color: #fff; padding: 16px 24px;
             display: flex; justify-content: space-between; align-items: center; }
    header h1 { font-size: 18px; }
    nav a { color: #dfe6e9; text-decoration: none; margin-left: 16px; font-size: 14px; }
    nav a:hover, nav a.active { color: #fdcb6e; }
    .controls { display: flex; gap: 16px; padding: 20px 24px; align-items: center; flex-wrap: wrap; }
    .controls label { font-size: 13px; color: #636e72; }
    .controls input, .controls select { padding: 6px 10px; border: 1px solid #dfe6e9;
      border-radius: 6px; font-size: 13px; }
    .controls input[type=number] { width: 80px; }
    #upload-btn { background: #fdcb6e; color: #2d3436; border: none;
                  padding: 8px 16px; border-radius: 6px; cursor: pointer;
                  font-weight: 600; font-size: 14px; }
    #upload-btn:hover { background: #e17055; color: #fff; }
    #file-input { display: none; }
    .cards { display: flex; gap: 16px; padding: 0 24px 20px; flex-wrap: wrap; }
    .card { background: #fff; border-radius: 10px; padding: 20px 24px;
            flex: 1; min-width: 130px; box-shadow: 0 2px 8px rgba(0,0,0,.06); }
    .card .label { font-size: 12px; color: #636e72; margin-bottom: 6px; }
    .card .value { font-size: 24px; font-weight: 700; color: #2d3436; }
    .warning-section { padding: 0 24px 20px; }
    .warning-section h2 { font-size: 14px; color: #e17055; margin-bottom: 10px; }
    .warning-list { display: flex; flex-wrap: wrap; gap: 8px; }
    .warning-tag { background: #ffeaa7; color: #d63031; padding: 4px 12px;
                   border-radius: 6px; font-size: 12px; font-weight: 500; }
    .table-section { padding: 0 24px 24px; }
    .table-section h2 { font-size: 14px; color: #636e72; margin-bottom: 12px; }
    table.data-table { width: 100%; border-collapse: collapse;
                       background: #fff; border-radius: 10px; overflow: hidden;
                       box-shadow: 0 2px 8px rgba(0,0,0,.06); }
    table.data-table th { background: #2d3436; color: #fff; padding: 10px 12px;
                          font-size: 12px; text-align: left; cursor: pointer;
                          user-select: none; white-space: nowrap; }
    table.data-table th:hover { background: #636e72; }
    table.data-table td { padding: 8px 12px; font-size: 12px;
                          border-bottom: 1px solid #f0f0f0; }
    table.data-table tr:last-child td { border-bottom: none; }
    .tag-red { background: #ff7675; color: #fff; border-radius: 4px;
               padding: 2px 8px; font-size: 11px; white-space: nowrap; }
    .tag-yellow { background: #fdcb6e; color: #2d3436; border-radius: 4px;
                  padding: 2px 8px; font-size: 11px; white-space: nowrap; }
    .tag-green { background: #00b894; color: #fff; border-radius: 4px;
                 padding: 2px 8px; font-size: 11px; white-space: nowrap; }
    .sort-arrow { font-size: 10px; margin-left: 4px; }
  </style>
</head>
<body>
<header>
  <div style="display:flex;align-items:center;gap:24px;">
    <h1>Amazon 搜索词分析</h1>
    <nav>
      <a href="/">订单时间分析</a>
      <a href="/search" class="active">搜索词分析</a>
    </nav>
  </div>
  <div>
    <button id="upload-btn" onclick="document.getElementById('file-input').click()">上传 CSV</button>
    <input type="file" id="file-input" accept=".csv" onchange="uploadFile(this)" />
  </div>
</header>

<div class="controls">
  <div>
    <label>目标 ACOS (%)：</label>
    <input type="number" id="target-acos" value="30" min="1" max="100" onchange="reRender()" />
  </div>
  <div>
    <label>广告活动：</label>
    <select id="campaign-filter" onchange="loadData()">
      <option value="全部">全部活动</option>
    </select>
  </div>
</div>

<div class="cards">
  <div class="card"><div class="label">搜索词数</div><div class="value" id="c-terms">-</div></div>
  <div class="card"><div class="label">总花费 ($)</div><div class="value" id="c-cost">-</div></div>
  <div class="card"><div class="label">总销售额 ($)</div><div class="value" id="c-sales">-</div></div>
  <div class="card"><div class="label">总购买量</div><div class="value" id="c-purchases">-</div></div>
  <div class="card"><div class="label">整体 ACOS</div><div class="value" id="c-acos">-</div></div>
  <div class="card"><div class="label">整体 ROAS</div><div class="value" id="c-roas">-</div></div>
</div>

<div class="warning-section" id="warning-section" style="display:none;">
  <h2>⚠ 烧钱词（花费 > 0，零购买）</h2>
  <div class="warning-list" id="warning-list"></div>
</div>

<div class="table-section">
  <h2>搜索词明细</h2>
  <table class="data-table">
    <thead>
      <tr>
        <th data-key="term">搜索词</th>
        <th data-key="impressions">展示量 <span class="sort-arrow"></span></th>
        <th data-key="clicks">点击量 <span class="sort-arrow"></span></th>
        <th data-key="ctr">点击率% <span class="sort-arrow"></span></th>
        <th data-key="cost">花费$ <span class="sort-arrow">▼</span></th>
        <th data-key="purchases">购买量 <span class="sort-arrow"></span></th>
        <th data-key="sales">销售额$ <span class="sort-arrow"></span></th>
        <th data-key="acos">ACOS% <span class="sort-arrow"></span></th>
        <th data-key="roas">ROAS <span class="sort-arrow"></span></th>
        <th>建议</th>
      </tr>
    </thead>
    <tbody id="table-body"></tbody>
  </table>
</div>

<script>
  let allData = null;
  let sortKey = 'cost';
  let sortAsc = false;

  async function loadData() {
    const campaign = document.getElementById('campaign-filter').value;
    const url = '/api/search-data' + (campaign !== '全部' ? '?campaign=' + encodeURIComponent(campaign) : '');
    const res = await fetch(url);
    if (!res.ok) { alert('数据加载失败'); return; }
    const data = await res.json();
    if (data.empty) return;
    if (data.error) { alert(data.error); return; }
    allData = data;
    updateCampaignFilter(data.campaigns);
    reRender();
  }

  function updateCampaignFilter(campaigns) {
    const sel = document.getElementById('campaign-filter');
    const current = sel.value;
    const opts = '<option value="全部">全部活动</option>' +
      campaigns.map(c => `<option value="${c}"${c === current ? ' selected' : ''}>${c}</option>`).join('');
    sel.innerHTML = opts;
  }

  async function uploadFile(input) {
    const file = input.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch('/api/search-upload', { method: 'POST', body: fd });
    const data = await res.json();
    if (data.error) { alert('上传失败: ' + data.error); return; }
    allData = data;
    updateCampaignFilter(data.campaigns);
    reRender();
    input.value = '';
  }

  function getSuggestion(t, targetAcos) {
    if (t.cost > 0 && t.purchases === 0) return { label: '否定', cls: 'tag-red' };
    if (t.acos < 0) return { label: '-', cls: '' };
    if (t.acos > targetAcos * 1.5) return { label: '否定/降价', cls: 'tag-red' };
    if (t.acos > targetAcos) return { label: '降低出价', cls: 'tag-yellow' };
    if (t.acos <= targetAcos * 0.5 && t.purchases >= 2) return { label: '提价/精准', cls: 'tag-green' };
    if (t.purchases > 0) return { label: '良好', cls: 'tag-green' };
    return { label: '-', cls: '' };
  }

  function reRender() {
    if (!allData) return;
    const s = allData.summary;
    const targetAcos = parseFloat(document.getElementById('target-acos').value) || 30;

    // 汇总卡片
    document.getElementById('c-terms').textContent = s.total_terms;
    document.getElementById('c-cost').textContent = s.total_cost.toFixed(2);
    document.getElementById('c-sales').textContent = s.total_sales.toFixed(2);
    document.getElementById('c-purchases').textContent = s.total_purchases;
    document.getElementById('c-acos').textContent = s.overall_acos >= 0 ? s.overall_acos.toFixed(1) + '%' : '-';
    document.getElementById('c-roas').textContent = s.overall_roas >= 0 ? s.overall_roas.toFixed(2) : '-';

    // 烧钱词
    const burners = allData.terms.filter(t => t.cost > 0 && t.purchases === 0);
    const warnSection = document.getElementById('warning-section');
    if (burners.length > 0) {
      warnSection.style.display = '';
      document.getElementById('warning-list').innerHTML = burners
        .sort((a, b) => b.cost - a.cost)
        .map(t => `<span class="warning-tag">${t.term} ($${t.cost.toFixed(2)})</span>`).join('');
    } else {
      warnSection.style.display = 'none';
    }

    // 排序
    const terms = [...allData.terms].sort((a, b) => {
      let va = a[sortKey], vb = b[sortKey];
      if (typeof va === 'string') { va = va.toLowerCase(); vb = vb.toLowerCase(); }
      if (va < vb) return sortAsc ? -1 : 1;
      if (va > vb) return sortAsc ? 1 : -1;
      return 0;
    });

    // 表格
    const tbody = document.getElementById('table-body');
    tbody.innerHTML = terms.map(t => {
      const sug = getSuggestion(t, targetAcos);
      const tagHtml = sug.cls ? `<span class="${sug.cls}">${sug.label}</span>` : sug.label;
      return `<tr>
        <td>${t.term}</td>
        <td>${t.impressions.toLocaleString()}</td>
        <td>${t.clicks.toLocaleString()}</td>
        <td>${t.ctr.toFixed(2)}</td>
        <td>${t.cost.toFixed(2)}</td>
        <td>${t.purchases}</td>
        <td>${t.sales.toFixed(2)}</td>
        <td>${t.acos >= 0 ? t.acos.toFixed(1) : '∞'}</td>
        <td>${t.roas >= 0 ? t.roas.toFixed(2) : '∞'}</td>
        <td>${tagHtml}</td>
      </tr>`;
    }).join('');

    // 更新排序箭头
    document.querySelectorAll('.data-table th[data-key]').forEach(th => {
      const arrow = th.querySelector('.sort-arrow');
      if (arrow) arrow.textContent = th.dataset.key === sortKey ? (sortAsc ? '▲' : '▼') : '';
    });
  }

  // 表头排序
  document.querySelectorAll('.data-table th[data-key]').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.dataset.key;
      if (sortKey === key) { sortAsc = !sortAsc; }
      else { sortKey = key; sortAsc = key === 'term'; }
      reRender();
    });
  });

  loadData();
</script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add templates/search.html
git commit -m "feat: add search term analysis frontend page"
```

---

## Task 3: 在 index.html 的 header 添加导航

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: 修改 index.html 的 header**

将现有 header：
```html
<header>
  <h1>Amazon 订单下单时间分析</h1>
  <div>
```

替换为：
```html
<header>
  <div style="display:flex;align-items:center;gap:24px;">
    <h1>Amazon 订单下单时间分析</h1>
    <nav>
      <a href="/" style="color:#fdcb6e;text-decoration:none;font-size:14px;">订单时间分析</a>
      <a href="/search" style="color:#dfe6e9;text-decoration:none;font-size:14px;margin-left:16px;">搜索词分析</a>
    </nav>
  </div>
  <div>
```

- [ ] **Step 2: Commit**

```bash
git add templates/index.html
git commit -m "feat: add navigation links to index.html header"
```

---

## Task 4: 集成验收

**Files:** 无新文件

- [ ] **Step 1: 验证后端数据加载**

```bash
cd /Users/hongruili/Documents/amazon-tool
python3 - <<'EOF'
from app import load_and_aggregate_search
data = load_and_aggregate_search('搜索词数据/Targeting_-_03_24_2026T20_47_30.csv')
print("搜索词数:", data['summary']['total_terms'])
print("总花费:", data['summary']['total_cost'])
print("总销售额:", data['summary']['total_sales'])
print("总购买量:", data['summary']['total_purchases'])
print("广告活动:", data['campaigns'])
burners = [t for t in data['terms'] if t['cost'] > 0 and t['purchases'] == 0]
print("烧钱词数:", len(burners))

# 测试活动筛选
data2 = load_and_aggregate_search('搜索词数据/Targeting_-_03_24_2026T20_47_30.csv', campaign='电缆线-自动')
print("筛选后搜索词数:", data2['summary']['total_terms'])
EOF
```

- [ ] **Step 2: 启动 Flask 浏览器验证**

```bash
python3 app.py
```

验证项目：
- 访问 `http://localhost:5000` — 订单分析页，header 有导航链接
- 访问 `http://localhost:5000/search` — 搜索词分析页
- 6 个汇总卡片显示正确
- 烧钱词区高亮花费>0但零购买的词
- 明细表可点击列头排序
- 修改目标 ACOS 输入框 → 建议标签实时变化
- 切换广告活动下拉框 → 数据重新加载
- 上传新 CSV → 数据更新

- [ ] **Step 3: 推送到 GitHub 触发 Render 部署**

```bash
git push
```

---

## 自检：Spec 覆盖确认

| Spec 需求 | 实现任务 |
|-----------|----------|
| GET /search → search.html | Task 1 Step 3 |
| GET /api/search-data（含 campaign 参数） | Task 1 Step 3 |
| POST /api/search-upload | Task 1 Step 3 |
| CSV 读取，按搜索词分组求和 | Task 1 Step 2 |
| 重新计算点击率/ACOS/ROAS | Task 1 Step 2 |
| 提取广告活动列表 | Task 1 Step 2 |
| 6 个汇总卡片 | Task 2 cards 区域 |
| 烧钱词警告区 | Task 2 warning-section |
| 可排序明细表 | Task 2 表格 + JS 排序 |
| 操作建议（5级标签） | Task 2 getSuggestion() |
| 目标 ACOS 可调（默认30%） | Task 2 input#target-acos |
| 广告活动筛选 | Task 2 select#campaign-filter |
| 上传 CSV 无刷新更新 | Task 2 uploadFile() |
| 导航链接互通 | Task 2 header nav + Task 3 |
