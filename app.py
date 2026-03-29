import os
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


if __name__ == '__main__':
    app.run(debug=True)
