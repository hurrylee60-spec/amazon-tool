import os
from flask import Flask, request, jsonify, render_template
import pandas as pd
from werkzeug.utils import secure_filename

app = Flask(__name__)

DATA_PATH = os.path.join('订单数据', '鸿锐美国订单汇总.xlsx')
UPLOAD_FOLDER = '订单数据'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

SEARCH_DATA_PATH = os.path.join('搜索词数据', 'Targeting_-_03_24_2026T20_47_30.csv')
SEARCH_UPLOAD_FOLDER = '搜索词数据'


def load_and_aggregate(filepath):
    """读取 Excel，过滤 Shipped 订单，计算各维度聚合数据。"""
    # 工作表名为 '1'，第2行（index=1）为空行，从第3行（header=2 → skiprows）起为数据
    # header=0 表示第1行为列名，skiprows=[1] 跳过第2行空行
    df = pd.read_excel(filepath, sheet_name='1', header=0, skiprows=[1])

    # 过滤已发货订单
    df = df[df['order-status'] == 'Shipped'].copy()
    if df.empty:
        raise ValueError('没有找到已发货订单 (order-status == Shipped)')

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
    df['month'] = df['purchase-date'].dt.strftime('%Y-%m')
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


def load_and_aggregate_search(filepath, campaign=None):
    """读取搜索词 CSV，按搜索词分组汇总，返回聚合数据。"""
    df = pd.read_csv(filepath, encoding='utf-8-sig')

    # 提取广告活动列表（去重）
    campaigns = sorted(df['广告活动名称'].dropna().unique().tolist())

    # 按广告活动筛选
    if campaign and campaign != '全部':
        df = df[df['广告活动名称'] == campaign]

    # 数值列清洗：转为数值
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


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/data')
def api_data():
    if not os.path.exists(DATA_PATH):
        return jsonify({'empty': True}), 200
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
    original_name = file.filename
    if not original_name.endswith('.xlsx'):
        return jsonify({'error': '仅支持 .xlsx 格式'}), 400
    # secure_filename 会去掉中文，用时间戳保证文件名安全
    filename = f"upload_{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}.xlsx"
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    file.save(save_path)
    try:
        data = load_and_aggregate(save_path)
        # 更新默认数据路径
        global DATA_PATH
        DATA_PATH = save_path
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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


if __name__ == '__main__':
    app.run(debug=True)
