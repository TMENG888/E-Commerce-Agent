"""
商品精细化运营数据分析方案
基于Plotly的Web可视化展示
RESTful API + 分页导航
支持Excel文件上传分析
"""

from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
import pandas as pd
import numpy as np
import plotly
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import json
import os
import openpyxl
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# 缓存目录
CACHE_DIR = 'cache'
UPLOAD_DIR = 'uploads'
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 数据文件路径（使用绝对路径）
APP_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(APP_DIR, 'uploads')
CACHE_DIR = os.path.join(APP_DIR, 'cache')
DEFAULT_DATA_FILE = os.path.join(UPLOAD_DIR, r"经营罗盘商品数据_20260514084057742_商品明细表__20260515_115757.csv")
CURRENT_DATA_FILE = DEFAULT_DATA_FILE
PERIOD_CONFIG_FILE = os.path.join(CACHE_DIR, 'period_config.json')

# 全局变量存储分析结果
analysis_cache = {}
CURRENT_PERIOD_DAYS = 7
PERIOD_TYPE = 'quick'
CUSTOM_START_DATE = ''
CUSTOM_END_DATE = ''

def load_period_config():
    """加载周期配置"""
    global CURRENT_PERIOD_DAYS, PERIOD_TYPE, CUSTOM_START_DATE, CUSTOM_END_DATE
    try:
        if os.path.exists(PERIOD_CONFIG_FILE):
            with open(PERIOD_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                PERIOD_TYPE = config.get('period_type', 'quick')
                CURRENT_PERIOD_DAYS = config.get('period_days', 7)
                CUSTOM_START_DATE = config.get('start_date', '')
                CUSTOM_END_DATE = config.get('end_date', '')
                print(f"📅 已加载周期配置: {PERIOD_TYPE}, days={CURRENT_PERIOD_DAYS}, date_range={CUSTOM_START_DATE}~{CUSTOM_END_DATE}")
    except Exception as e:
        print(f"加载周期配置失败: {e}")
        PERIOD_TYPE = 'quick'
        CURRENT_PERIOD_DAYS = 7

def save_period_config(period_type='quick', period_days=7, start_date='', end_date=''):
    """保存周期配置"""
    global CURRENT_PERIOD_DAYS, PERIOD_TYPE, CUSTOM_START_DATE, CUSTOM_END_DATE
    try:
        config = {
            'period_type': period_type,
            'period_days': period_days,
            'start_date': start_date,
            'end_date': end_date
        }
        with open(PERIOD_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        PERIOD_TYPE = period_type
        CURRENT_PERIOD_DAYS = period_days
        CUSTOM_START_DATE = start_date
        CUSTOM_END_DATE = end_date
        print(f"📅 已保存周期配置: {period_type}, days={period_days}, date_range={start_date}~{end_date}")
    except Exception as e:
        print(f"保存周期配置失败: {e}")

load_period_config()


def load_data():
    """加载商品数据"""
    global CURRENT_DATA_FILE
    try:
        if CURRENT_DATA_FILE.lower().endswith('.xlsx'):
            df = pd.read_excel(CURRENT_DATA_FILE)
        else:
            df = pd.read_csv(CURRENT_DATA_FILE, encoding='utf-8-sig')
        return df
    except Exception as e:
        print("数据加载失败:", e)
        return pd.DataFrame()


def preprocess_data(df):
    """预处理数据并计算派生指标"""
    if df.empty:
        return df

    numeric_cols = ['商品曝光次数', '商品曝光人数', '商品浏览次数', '商品浏览人数',
                   '询单人数', '支付人数', '支付订单数', '支付金额']

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    df['CTR'] = np.where(df['商品曝光人数'] > 0, 
                          (df['商品浏览人数'] / df['商品曝光人数']) * 100, 
                          0)

    df['CVR'] = np.where(df['商品浏览人数'] > 0, 
                          (df['支付人数'] / df['商品浏览人数']) * 100, 
                          0)

    df['日均曝光量'] = np.where(df['累计上架天数'] > 0, 
                               df['商品曝光次数'] / df['累计上架天数'], 
                               0)

    df['GPM'] = np.where(df['商品曝光次数'] > 0, 
                          (df['支付金额'] / df['商品曝光次数']) * 10000, 
                          0)

    return df


def classify_products(df, period_days=None):
    """商品六维精细化分类 - 按上架天数标准化"""
    if df.empty:
        return df, 0, 0
    
    if period_days is None:
        period_days = CURRENT_PERIOD_DAYS
    
    df['标准化天数'] = df['累计上架天数'].apply(lambda x: min(x, period_days))
    
    df['日均曝光'] = np.where(df['标准化天数'] > 0, 
                               df['商品曝光人数'] / df['标准化天数'], 
                               0)
    
    df['日均浏览'] = np.where(df['标准化天数'] > 0, 
                               df['商品浏览人数'] / df['标准化天数'], 
                               0)
    
    df['日均支付'] = np.where(df['标准化天数'] > 0, 
                               df['支付人数'] / df['标准化天数'], 
                               0)
    
    df['标准化CTR'] = np.where(df['日均曝光'] > 0, 
                                (df['日均浏览'] / df['日均曝光']) * 100, 
                                0)
    
    df['标准化CVR'] = np.where(df['日均浏览'] > 0, 
                                (df['日均支付'] / df['日均浏览']) * 100, 
                                0)

    exposure_median = df['日均曝光'].median()
    ctr_mean = df['标准化CTR'].mean()
    cvr_mean = df['标准化CVR'].mean()
    
    ctr_high_threshold = ctr_mean * 1.5
    cvr_high_threshold = cvr_mean * 1.5
    ctr_low_threshold = ctr_mean * 0.3
    cvr_low_threshold = cvr_mean * 0.3

    print("分类阈值(标准化后): 日均曝光中位数=%s, 标准化CTR均值=%s, 标准化CVR均值=%s" % (exposure_median, ctr_mean, cvr_mean))

    def classify(row):
        is_high_exposure = row['日均曝光'] > exposure_median
        is_high_ctr = row['标准化CTR'] > ctr_mean
        is_high_cvr = row['标准化CVR'] > cvr_mean
        is_extreme_ctr = row['标准化CTR'] > ctr_high_threshold
        is_extreme_cvr = row['标准化CVR'] > cvr_high_threshold
        is_low_ctr = row['标准化CTR'] < ctr_low_threshold
        
        if cvr_mean == 0:
            is_low_cvr = row['标准化CVR'] <= cvr_mean
        else:
            is_low_cvr = row['标准化CVR'] < cvr_low_threshold
        
        is_trap = is_high_ctr and is_low_cvr

        if is_trap:
            return '转化陷阱'
        elif is_high_exposure and is_high_ctr and is_high_cvr:
            return '超级爆款'
        elif is_extreme_ctr and is_high_cvr and not is_high_exposure:
            return '视觉黑马'
        elif is_high_exposure and is_low_ctr:
            return '封面杀手'
        elif is_extreme_cvr and not is_high_exposure and not is_high_ctr:
            return '冷门精品'
        else:
            return '待清理垃圾'

    df['分类'] = df.apply(classify, axis=1)

    df['建议'] = df['分类'].map({
        '超级爆款': '防守：维持库存，拉高单价测试利润上限。这是店铺的"印钞机"',
        '视觉黑马': '进攻：立即加大引流词，手动"擦亮"，甚至付费买流量。被算法低估的明珠',
        '封面杀手': '重塑：100%是图丑或价格在搜索页没优势。立即换图，尝试使用实拍图或标注"包邮"、"99新"',
        '转化陷阱': '复盘：用户被骗进来了但不买。优先检查是否有差评，或询问客服询单未成交原因',
        '冷门精品': '收割：流量虽小但精准。保持挂机，无需过多干预',
        '待清理垃圾': '止损：累计14天无变动则直接删除，释放店铺权重'
    })

    df['处理优先级'] = df['分类'].map({
        '转化陷阱': 1,
        '视觉黑马': 2,
        '封面杀手': 3,
        '超级爆款': 4,
        '冷门精品': 5,
        '待清理垃圾': 6
    })

    return df, exposure_median, cvr_mean


def create_category_bar_chart(df):
    """创建分类数量柱状图"""
    category_counts = df['分类'].value_counts().reset_index()
    category_counts.columns = ['分类', '数量']

    color_map = {
        '超级爆款': '#10B981',
        '视觉黑马': '#8B5CF6',
        '封面杀手': '#F59E0B',
        '转化陷阱': '#EF4444',
        '冷门精品': '#3B82F6',
        '待清理垃圾': '#6B7280'
    }

    fig = px.bar(category_counts,
                 x='分类',
                 y='数量',
                 color='分类',
                 color_discrete_map=color_map,
                 title='商品分类分布',
                 labels={'数量': '商品数量'},
                 text='数量',
                 width=800,
                 height=400)

    fig.update_layout(
        plot_bgcolor='white',
        paper_bgcolor='white',
        font={'family': 'Microsoft YaHei'},
        barmode='group',
        yaxis=dict(
            range=[0, max(category_counts['数量']) * 1.2],
            title='商品数量',
            tickfont={'size': 12}
        ),
        xaxis=dict(
            title='分类',
            tickfont={'size': 12}
        ),
        showlegend=True
    )

    fig.update_traces(textposition='outside')

    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)


def create_kpi_cards(df):
    """创建KPI卡片数据"""
    df.columns = df.columns.str.strip()

    total_products = len(df)
    total_exposure = df['商品曝光人数'].sum()
    total_browse = df['商品浏览人数'].sum()
    total_pay = df['支付人数'].sum()
    total_revenue = df['支付金额'].sum()

    avg_ctr = df['CTR'].mean()
    avg_cvr = df['CVR'].mean()
    avg_gpm = df['GPM'].mean()

    category_stats = df['分类'].value_counts().to_dict()

    return {
        'total_products': total_products,
        'total_exposure': int(total_exposure),
        'total_browse': int(total_browse),
        'total_pay': int(total_pay),
        'total_revenue': round(total_revenue, 2),
        'avg_ctr': round(avg_ctr, 2),
        'avg_cvr': round(avg_cvr, 2),
        'avg_gpm': round(avg_gpm, 2),
        'category_stats': category_stats
    }


def create_top_gpm_chart(df):
    """创建GPM排行榜"""
    top_gpm = df[df['GPM'] > 0].sort_values('GPM', ascending=False).head(10)

    if len(top_gpm) == 0:
        fig = go.Figure()
        fig.add_annotation(
            x=0.5, y=0.5,
            text="暂无有效GPM数据",
            showarrow=False,
            font={'size': 16, 'color': '#9ca3af'}
        )
        fig.update_layout(
            title='商品GPM排行榜（TOP10）',
            plot_bgcolor='white',
            paper_bgcolor='white',
            font={'family': 'Microsoft YaHei'},
            width=800,
            height=500
        )
        return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    fig = go.Figure(data=[go.Bar(
        x=top_gpm['GPM'].values,
        y=top_gpm['商品名称'].values,
        orientation='h',
        marker_color='#3B82F6'
    )])

    fig.update_layout(
        title='商品GPM排行榜（TOP10）',
        xaxis_title='万次曝光成交额',
        yaxis_title='商品名称',
        plot_bgcolor='white',
        paper_bgcolor='white',
        font={'family': 'Microsoft YaHei'},
        width=800,
        height=500
    )

    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)


def create_price_band_chart(df, category_name=None, product_category=None):
    """创建价格带分析图表 - 包含转化率折线（归一化处理）"""
    filtered_df = df.copy()
    
    if category_name and category_name != 'all':
        if '渠道一级类目名称' in df.columns:
            filtered_df = filtered_df[filtered_df['渠道一级类目名称'] == category_name]
        elif 'category' in df.columns:
            filtered_df = filtered_df[filtered_df['category'] == category_name]
        elif '分类' in df.columns:
            filtered_df = filtered_df[filtered_df['分类'] == category_name]

    if product_category and product_category != 'all':
        filtered_df = filtered_df[filtered_df['分类'] == product_category]

    price_bands = [
        (0, 15, '¥0-15'),
        (15, 25, '¥15-25'),
        (25, 40, '¥25-40'),
        (40, 60, '¥40-60'),
        (60, 100, '¥60-100'),
        (100, 500, '¥100-500'),
        (500, float('inf'), '¥500+')
    ]

    price_band_data = []
    max_browse_rate = 0
    cvr_values = []
    
    for low, high, label in price_bands:
        mask = (filtered_df['商品价格'] > low) & (filtered_df['商品价格'] <= high)
        band_df = filtered_df[mask]

        if len(band_df) > 0:
            total_exposure = band_df['商品曝光人数'].sum()
            total_browse = band_df['商品浏览人数'].sum()
            total_pay = band_df['支付人数'].sum()
            product_count = len(band_df)
            avg_exposure = round(total_exposure / product_count, 0)
            avg_browse = round(total_browse / product_count, 0)
            browse_rate = (total_browse / total_exposure * 100) if total_exposure > 0 else 0
            cvr = (total_pay / total_browse * 100) if total_browse > 0 else 0
        else:
            total_exposure = 0
            total_browse = 0
            total_pay = 0
            product_count = 0
            avg_exposure = 0
            avg_browse = 0
            browse_rate = 0
            cvr = 0

        max_browse_rate = max(max_browse_rate, browse_rate)
        cvr_values.append(cvr)

        if browse_rate == 0:
            color_class = 'danger'
        elif browse_rate < 5:
            color_class = 'warn'
        else:
            color_class = 'success'

        price_band_data.append({
            'price_band': label,
            'product_count': product_count,
            'avg_exposure': int(avg_exposure),
            'avg_browse': int(avg_browse),
            'browse_rate': round(browse_rate, 1),
            'cvr': round(cvr, 1),
            'total_pay': int(total_pay),
            'color_class': color_class
        })

    df_chart = pd.DataFrame(price_band_data)

    color_map = {
        'success': '#10B981',
        'warn': '#F59E0B',
        'danger': '#EF4444'
    }

    max_display_range = max(max_browse_rate * 1.2, 15)

    cvr_max = max(cvr_values) if cvr_values else 0
    cvr_min = min([c for c in cvr_values if c > 0]) if any(c > 0 for c in cvr_values) else 0
    if cvr_min == cvr_max:
        cvr_min = 0
    
    cvr_range = cvr_max - cvr_min
    cvr_upper = cvr_max + cvr_range * 0.1 if cvr_range > 0 else 10
    cvr_lower = max(0, cvr_min - cvr_range * 0.1) if cvr_range > 0 else 0

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(go.Bar(
        x=df_chart['price_band'],
        y=df_chart['browse_rate'],
        marker_color=[color_map.get(c, '#10B981') for c in df_chart['color_class']],
        name='浏览/曝光率(%)',
        customdata=df_chart[['product_count', 'avg_exposure', 'avg_browse', 'cvr', 'total_pay']].values,
        hovertemplate='<b>价格段: %{x}</b><br>' +
                     '浏览/曝光: %{y:.1f}%<br>' +
                     '商品数: %{customdata[0]}款<br>' +
                     '平均曝光: %{customdata[1]}人<br>' +
                     '平均浏览: %{customdata[2]}人<br>' +
                     '转化率: %{customdata[3]:.1f}%<br>' +
                     '支付人数: %{customdata[4]}'
    ), secondary_y=False)

    fig.add_trace(go.Scatter(
        x=df_chart['price_band'],
        y=df_chart['cvr'],
        mode='lines+markers',
        name='转化率(%)',
        line=dict(color='#8B5CF6', width=3),
        marker=dict(color='#8B5CF6', size=8),
        customdata=df_chart['cvr'].values,
        hovertemplate='<b>价格段: %{x}</b><br>' +
                     '转化率: %{y:.1f}%'
    ), secondary_y=True)

    fig.update_layout(
        title='价格带浏览转化率分析',
        plot_bgcolor='white',
        paper_bgcolor='white',
        font={'family': 'Microsoft YaHei'},
        showlegend=True,
        legend=dict(orientation='v', y=0.5, x=1.15, xanchor='left'),
        width=None,
        height=None,
        margin=dict(l=100, r=180, t=80, b=80),
        xaxis=dict(
            title='价格段',
            title_font={'size': 14},
            tickfont={'size': 12}
        )
    )

    fig.update_yaxes(
        range=[0, max_display_range],
        tickformat='.1f',
        title='浏览/曝光(%)',
        title_font={'size': 14},
        tickfont={'size': 12},
        secondary_y=False,
        constrain='domain'
    )

    fig.update_yaxes(
        range=[0, max(cvr_upper, 1)],
        tickformat='.1f',
        title='转化率(%)',
        title_font={'size': 14},
        tickfont={'size': 12},
        secondary_y=True
    )

    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder), price_band_data


def get_categories(df):
    """获取一级类目列表"""
    categories = df['渠道一级类目名称'].dropna().unique().tolist()
    return categories


def analyze_and_cache():
    """执行分析并缓存结果"""
    global analysis_cache

    print("开始执行数据分析...")

    df = load_data()
    if df.empty:
        print("数据加载失败")
        return False

    df = preprocess_data(df)
    df, exposure_median, cvr_mean = classify_products(df)

    category_chart = create_category_bar_chart(df)
    top_gpm_chart = create_top_gpm_chart(df)

    price_band_chart, price_band_data = create_price_band_chart(df)

    categories = get_categories(df)
    kpi_data = create_kpi_cards(df)

    df.columns = df.columns.str.strip()
    df = df.rename(columns={'商品 ID': '商品ID'})
    
    product_list = []
    for _, row in df.iterrows():
        level4_category = row.get('渠道四级类目名称', '未分类')
        if pd.isna(level4_category) or level4_category == '':
            level4_category = '未分类'
        product_list.append({
            'id': row['商品ID'],
            'name': row['商品名称'],
            'price': row['商品价格'],
            'exposure': row['商品曝光人数'],
            'browse': row['商品浏览人数'],
            'pay': row['支付人数'],
            'ctr': round(row['CTR'], 2),
            'cvr': round(row['CVR'], 2),
            'category': row['分类'],
            'level4_category': level4_category
        })

    analysis_cache = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'kpi': kpi_data,
        'category_chart': category_chart,
        'top_gpm_chart': top_gpm_chart,
        'price_band_chart': price_band_chart,
        'price_band_data': price_band_data,
        'categories': categories,
        'product_list': product_list,
        'total_products': len(df)
    }

    cache_file = os.path.join(CACHE_DIR, 'analysis_result.json')
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(analysis_cache, f, ensure_ascii=False, indent=2)

    print("分析完成，结果已缓存")
    return True


@app.route('/test-chart')
def test_chart():
    """测试图表渲染"""
    return render_template('test_chart.html')

@app.route('/')
def index():
    """首页 - 仪表盘概览"""
    if not analysis_cache:
        analyze_and_cache()

    return render_template('index.html',
                         kpi=analysis_cache['kpi'],
                         category_chart=analysis_cache['category_chart'],
                         top_gpm_chart=analysis_cache['top_gpm_chart'],
                         price_band_chart=analysis_cache['price_band_chart'],
                         total_products=analysis_cache['total_products'],
                         timestamp=analysis_cache['timestamp'])


@app.route('/charts/category')
def chart_category():
    """商品分类分布图页面"""
    if not analysis_cache:
        analyze_and_cache()

    return render_template('charts/category.html',
                         category_chart=analysis_cache['category_chart'],
                         kpi=analysis_cache['kpi'],
                         timestamp=analysis_cache['timestamp'])


@app.route('/charts/gpm')
def chart_gpm():
    """GPM排行榜页面"""
    if not analysis_cache:
        analyze_and_cache()

    df = load_data()
    df = preprocess_data(df)
    df, _, _ = classify_products(df)
    top_gpm_data = df[df['GPM'] > 0].sort_values('GPM', ascending=False).head(20)[['商品名称', '商品价格', 'GPM', '商品曝光人数', '支付人数']].to_dict('records')

    return render_template('charts/gpm.html',
                         gpm_chart=analysis_cache['top_gpm_chart'],
                         gpm_data=top_gpm_data,
                         timestamp=analysis_cache['timestamp'])


@app.route('/charts/price-band')
def chart_price_band():
    """价格带分析页面"""
    if not analysis_cache:
        analyze_and_cache()

    return render_template('charts/price_band.html',
                         price_band_chart=analysis_cache['price_band_chart'],
                         price_band_data=analysis_cache['price_band_data'],
                         categories=analysis_cache['categories'],
                         timestamp=analysis_cache['timestamp'])


@app.route('/products')
def products():
    """商品列表页面"""
    if not analysis_cache:
        analyze_and_cache()

    page = int(request.args.get('page', 1))
    page_size = 10
    total_products = len(analysis_cache['product_list'])
    total_pages = (total_products + page_size - 1) // page_size
    start = (page - 1) * page_size
    end = start + page_size
    paginated_products = analysis_cache['product_list'][start:end]
    


    return render_template('products.html',
                         products=paginated_products,
                         category_chart=analysis_cache['category_chart'],
                         current_page=page,
                         total_pages=total_pages,
                         total_products=total_products,
                         page_size=page_size,
                         timestamp=analysis_cache['timestamp'])


@app.route('/strategy')
def strategy():
    """策略说明页面"""
    return render_template('strategy.html',
                         timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))


@app.route('/category-analysis')
def category_analysis():
    """四级类目分析页面"""
    if not analysis_cache:
        analyze_and_cache()

    df = load_data()
    df = preprocess_data(df)
    df, _, _ = classify_products(df)

    categories = [
        {'value': '超级爆款', 'label': '超级爆款', 'selected': False},
        {'value': '视觉黑马', 'label': '视觉黑马', 'selected': False},
        {'value': '封面杀手', 'label': '封面杀手', 'selected': False},
        {'value': '转化陷阱', 'label': '转化陷阱', 'selected': False},
        {'value': '冷门精品', 'label': '冷门精品', 'selected': False},
        {'value': '待清理垃圾', 'label': '待清理垃圾', 'selected': False}
    ]
    categories[0]['selected'] = True

    level4_data = analyze_category_distribution_for_class(df, '超级爆款')

    return render_template('category_analysis.html',
                         categories=categories,
                         current_category_label='超级爆款',
                         level4_data=level4_data,
                         timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))


def analyze_category_distribution_for_class(df, classification):
    """分析特定分类下的四级类目分布"""
    filtered = df[df['分类'] == classification]
    
    if len(filtered) == 0:
        return []
        
    level4_counts = filtered['渠道四级类目名称'].value_counts().reset_index()
    level4_counts.columns = ['name', 'count']
    level4_counts['percentage'] = (level4_counts['count'] / len(filtered) * 100).round(2)
    
    return level4_counts.to_dict('records')


def analyze_category_distribution(df):
    """分析四级类目在各分类中的分布"""
    category_stats = []
    
    for classification in ['超级爆款', '视觉黑马', '封面杀手', '转化陷阱', '冷门精品', '待清理垃圾']:
        filtered = df[df['分类'] == classification]
        
        if len(filtered) == 0:
            continue
            
        level4_counts = filtered['渠道四级类目名称'].value_counts().reset_index()
        level4_counts.columns = ['四级类目', '商品数']
        level4_counts['占比'] = (level4_counts['商品数'] / len(filtered) * 100).round(2)
        level4_counts['分类'] = classification
        
        category_stats.extend(level4_counts.to_dict('records'))
    
    return category_stats


@app.route('/api/refresh')
def refresh_analysis():
    """刷新分析数据"""
    success = analyze_and_cache()
    return jsonify({'success': success, 'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})


@app.route('/api/chart-data')
def api_chart_data():
    """获取图表数据API"""
    page = request.args.get('page', '')
    chart_id = request.args.get('chart', '')
    
    if not analysis_cache:
        analyze_and_cache()
    
    chart_key_map = {
        '/': {
            'category-chart': 'category_chart',
            'top-gpm-chart': 'top_gpm_chart',
            'price-band-chart': 'price_band_chart'
        },
        '/charts/category': {
            'category-chart': 'category_chart'
        },
        '/charts/gpm': {
            'gpm-chart': 'top_gpm_chart'
        },
        '/charts/ctr-cvr': {
            'ctr-cvr-chart': 'ctr_cvr_chart'
        },
        '/charts/price-band': {
            'price-band-chart': 'price_band_chart'
        }
    }
    
    page_charts = chart_key_map.get(page, {})
    cache_key = page_charts.get(chart_id, chart_id.replace('-', '_'))
    
    if cache_key in analysis_cache:
        return jsonify({'success': True, 'chartData': analysis_cache[cache_key]})
    else:
        return jsonify({'success': False, 'error': 'Chart data not found'})


@app.route('/api/products')
def api_products():
    """获取商品列表数据API，支持分类筛选和分页"""
    category = request.args.get('category', 'all')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 10))
    
    if not analysis_cache:
        analyze_and_cache()
    
    product_list = analysis_cache.get('product_list', [])
    
    if category != 'all':
        filtered_products = [p for p in product_list if p['category'] == category]
    else:
        filtered_products = product_list
    
    total_products = len(filtered_products)
    total_pages = (total_products + page_size - 1) // page_size
    start = (page - 1) * page_size
    end = start + page_size
    
    page_products = filtered_products[start:end]
    
    formatted_products = []
    for p in page_products:
        formatted_products.append({
            'name': p['name'],
            'price': p['price'],
            'exposure': p['exposure'],
            'browse': p['browse'],
            'pay': p['pay'],
            'ctr': p['ctr'],
            'cvr': p['cvr'],
            'category': p['category']
        })
    
    return jsonify({
        'success': True,
        'products': formatted_products,
        'current_page': page,
        'total_pages': total_pages,
        'total_products': total_products,
        'page_size': page_size
    })


@app.route('/api/products/ids')
def api_product_ids():
    """获取指定分类的所有商品ID列表"""
    category = request.args.get('category', 'all')
    
    if not analysis_cache:
        analyze_and_cache()
    
    product_list = analysis_cache.get('product_list', [])
    
    if category != 'all':
        filtered_products = [p for p in product_list if p['category'] == category]
    else:
        filtered_products = product_list
    
    product_ids = [str(p['id']) for p in filtered_products]
    
    return jsonify({
        'success': True,
        'ids': product_ids,
        'count': len(product_ids),
        'category': category,
        'ids_string': ','.join(product_ids)
    })


@app.route('/api/gpm-data')
def api_gpm_data():
    """获取GPM数据API，支持分类筛选"""
    category = request.args.get('category', 'all')
    
    if not analysis_cache:
        analyze_and_cache()
    
    df = load_data()
    df = preprocess_data(df)
    df, _, _ = classify_products(df)
    
    if category != 'all':
        df = df[df['分类'] == category]
    
    top_gpm_data = df[df['GPM'] > 0].sort_values('GPM', ascending=False).head(20)[['商品名称', '商品价格', 'GPM', '商品曝光人数', '支付人数']].to_dict('records')
    
    return jsonify({
        'success': True,
        'data': top_gpm_data
    })


@app.route('/api/category-analysis')
def api_category_analysis():
    """获取类目分析数据API"""
    classification = request.args.get('classification', '超级爆款')
    
    if not analysis_cache:
        analyze_and_cache()
    
    product_list = analysis_cache.get('product_list', [])
    
    filtered_products = [p for p in product_list if p['category'] == classification]
    
    if len(filtered_products) == 0:
        return jsonify({
            'label': classification,
            'items': []
        })
    
    level4_counts = {}
    for p in filtered_products:
        level4_name = p.get('level4_category', '未分类')
        if level4_name in level4_counts:
            level4_counts[level4_name] += 1
        else:
            level4_counts[level4_name] = 1
    
    level4_data = []
    total = len(filtered_products)
    for name, count in level4_counts.items():
        level4_data.append({
            'name': name,
            'count': count,
            'percentage': round(count / total * 100, 2)
        })
    
    level4_data.sort(key=lambda x: x['count'], reverse=True)
    
    return jsonify({
        'label': classification,
        'items': level4_data
    })


@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    """文件上传页面"""
    global CURRENT_DATA_FILE, analysis_cache
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('请选择要上传的文件', 'error')
            return redirect(url_for('upload_file'))
        
        file = request.files['file']
        period_type = request.form.get('period_type', 'quick')
        period_days = 7
        
        if period_type == 'custom':
            custom_days = request.form.get('custom_days', '')
            if not custom_days:
                flash('请输入自定义天数', 'error')
                return redirect(url_for('upload_file'))
            
            try:
                period_days = int(custom_days)
                if period_days < 1 or period_days > 30:
                    flash('自定义天数必须在1-30之间', 'error')
                    return redirect(url_for('upload_file'))
            except ValueError:
                flash('请输入有效的数字', 'error')
                return redirect(url_for('upload_file'))
        else:
            period_days = request.form.get('period_days_hidden', '7')
            try:
                period_days = int(period_days)
            except ValueError:
                period_days = 7
        
        if file.filename == '':
            flash('请选择要上传的文件', 'error')
            return redirect(url_for('upload_file'))
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_DIR, filename)
            file.save(filepath)
            
            CURRENT_DATA_FILE = filepath
            analysis_cache = {}
            
            save_period_config(period_type, period_days, '', '')
            
            try:
                success = analyze_and_cache()
                if success:
                    if period_type == 'custom':
                        flash(f'文件上传成功，分析已更新！（自定义周期：{start_date} ~ {end_date}，共{period_days}天）', 'success')
                    else:
                        flash(f'文件上传成功，分析已更新！（标准化周期：{period_days}天）', 'success')
                else:
                    CURRENT_DATA_FILE = DEFAULT_DATA_FILE
                    flash('文件格式不正确或数据不符合要求', 'error')
            except Exception as e:
                CURRENT_DATA_FILE = DEFAULT_DATA_FILE
                flash(f'文件解析失败: {str(e)}', 'error')
            
            return redirect(url_for('index'))
    
    return render_template('upload.html',
                         current_file=os.path.basename(CURRENT_DATA_FILE),
                         is_default=CURRENT_DATA_FILE == DEFAULT_DATA_FILE,
                         current_period=CURRENT_PERIOD_DAYS,
                         period_type=PERIOD_TYPE,
                         custom_start_date=CUSTOM_START_DATE,
                         custom_end_date=CUSTOM_END_DATE)


def allowed_file(filename):
    """检查文件扩展名是否允许"""
    allowed_extensions = {'csv', 'xlsx', 'xls'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions


def secure_filename(filename):
    """安全的文件名处理"""
    import re
    filename = re.sub(r'[^\w\.-]', '_', filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    name, ext = os.path.splitext(filename)
    return f"{name}_{timestamp}{ext}"


@app.route('/api/reset')
def reset_data():
    """重置为默认数据"""
    global CURRENT_DATA_FILE, analysis_cache
    CURRENT_DATA_FILE = DEFAULT_DATA_FILE
    analysis_cache = {}
    success = analyze_and_cache()
    return jsonify({'success': success, 'message': '已重置为默认数据'})


@app.route('/api/all_data')
def get_all_data():
    if not analysis_cache:
        analyze_and_cache()
    
    return jsonify({
        'kpi': analysis_cache['kpi'],
        'category_chart': analysis_cache['category_chart'],
        'top_gpm_chart': analysis_cache['top_gpm_chart'],
        'price_band_chart': analysis_cache['price_band_chart'],
        'price_band_data': analysis_cache['price_band_data'],
        'categories': analysis_cache['categories'],
        'product_list': analysis_cache['product_list'],
        'total_products': analysis_cache['total_products'],
        'timestamp': analysis_cache['timestamp']
    })


@app.route('/api/price-band')
def get_price_band_data():
    """获取价格带分析数据"""
    category = request.args.get('category', 'all')
    
    df = load_data()
    df = preprocess_data(df)
    
    chart, data = create_price_band_chart(df, category_name=category)
    
    return jsonify({
        'chart': chart,
        'data': data
    })


@app.route('/api/kpi')
def get_kpi():
    """获取KPI数据"""
    if not analysis_cache:
        analyze_and_cache()

    return jsonify(analysis_cache['kpi'])


@app.route('/api/price_band')
def get_price_band():
    """获取价格带分析数据"""
    if not analysis_cache:
        analyze_and_cache()

    return jsonify({
        'chart': analysis_cache['price_band_chart'],
        'data': analysis_cache['price_band_data'],
        'categories': analysis_cache['categories']
    })


@app.route('/api/price_band/<category>')
def get_price_band_by_category(category):
    """按类目获取价格带分析数据"""
    df = load_data()
    if df.empty:
        return jsonify({'error': '数据加载失败'})

    df = preprocess_data(df)
    df, _, _ = classify_products(df)

    chart, data = create_price_band_chart(df, category)

    return jsonify({
        'chart': chart,
        'data': data,
        'category': category
    })


@app.route('/api/price_band/<category>/<product_category>')
def get_price_band_by_double_filter(category, product_category):
    """按类目和商品分类双重筛选价格带分析数据"""
    df = load_data()
    if df.empty:
        return jsonify({'error': '数据加载失败'})

    df = preprocess_data(df)
    df, _, _ = classify_products(df)

    chart, data = create_price_band_chart(df, category, product_category)

    return jsonify({
        'chart': chart,
        'data': data,
        'category': category,
        'product_category': product_category
    })


if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    os.makedirs('templates/charts', exist_ok=True)

    analyze_and_cache()

    app.run(debug=True, host='0.0.0.0', port=5000)
