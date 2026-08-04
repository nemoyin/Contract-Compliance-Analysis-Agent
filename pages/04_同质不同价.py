"""同质不同价分析页面 — 批量聚类 + 价格异常检测"""
import os
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from engine.config import ConfigManager
from engine.cache import CacheManager
from engine.comparator import cluster_and_detect, calc_compliance_rate

st.set_page_config(page_title="同质不同价", page_icon="🔍", layout="wide")
st.title("🔍 同质不同价分析")
st.caption("服务质量相近的楼盘，谁的收费不合理？")

# -------- 路径初始化 --------
data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
cache_dir = os.path.join(data_dir, "cache")
config_path = os.path.join(data_dir, "config.json")
standards_path = os.path.join(data_dir, "standards.xlsx")

cfg = ConfigManager(config_path)
config = cfg.load()
cache_mgr = CacheManager(cache_dir)

if not cache_mgr.is_valid():
    st.warning("⚠️ 数据缓存未初始化，请先在首页执行初始化")
    if st.button("前往首页"):
        st.switch_page("pages/01_首页.py")
    st.stop()

# -------- 加载数据 --------
results = cache_mgr.load_results()
contracts = cache_mgr.get_contracts()

from engine.loader import load_standards
standards = load_standards(standards_path) if os.path.exists(standards_path) else []

if not contracts:
    st.error("没有可用的合同数据")
    st.stop()

# -------- 控件 --------
st.markdown("### 分析参数")

col1, col2 = st.columns(2)
with col1:
    fee_type = st.selectbox(
        "费用类型",
        options=["住宅物业费", "商业物业费", "车位费"],
    )
with col2:
    contract_names = [c.property_name for c in contracts]
    selected_contracts = st.multiselect(
        "分析范围",
        options=contract_names,
        default=contract_names,
        help="选择参与分析对比的合同",
    )

col3, col4 = st.columns(2)
with col3:
    quality_sim = st.slider(
        "同质相似度阈值",
        min_value=0.80, max_value=1.00,
        value=float(config["thresholds"].get("quality_similarity", 0.95)),
        step=0.01,
        help="服务满足度余弦相似度 >= 此值视为同质组",
    )
with col4:
    outlier_std = st.slider(
        "价格异常标准差倍数",
        min_value=0.5, max_value=5.0,
        value=float(config["thresholds"].get("price_outlier_std", 1.5)),
        step=0.1,
        help="价格偏离组均值 >= N 个标准差标记为异常",
    )

# -------- 分析 --------
if st.button("🔍 开始批量分析", type="primary", use_container_width=True):
    if len(selected_contracts) < 2:
        st.warning("请至少选择 2 个合同进行分析")
        st.stop()

    analysis_config = {
        "quality_similarity": quality_sim,
        "price_outlier_std": outlier_std,
    }
    ft = {"住宅物业费": "residential", "商业物业费": "commercial", "车位费": "parking"}[fee_type]

    with st.spinner("批量分析中，正在聚类..."):
        try:
            filtered = [c for c in contracts if c.property_name in selected_contracts]
            cluster_result = cluster_and_detect(filtered, results, standards, ft, analysis_config)
        except Exception as e:
            st.error(f"分析出错: {e}")
            st.stop()

    st.success(
        f"分析完成！发现 **{len(cluster_result.groups)}** 个同质组，"
        f"**{len(cluster_result.outliers)}** 个价格异常"
    )

    fee_attr = {"residential": "residential_fee", "commercial": "commercial_fee", "parking": "parking_fee"}[ft]

    # ====== 散点图 ======
    st.subheader("📈 满足率 x 价格 散点图")

    outlier_ids = {o.contract_id for o in cluster_result.outliers}

    scatter_data = []
    for c in filtered:
        c_results = results.get(c.id, [])
        report = calc_compliance_rate(c.id, c_results, standards)
        scatter_data.append({
            "物业名称": c.property_name,
            "满足率(%)": round(report.total_rate * 100, 1),
            "费用(元)": getattr(c, fee_attr),
            "类型": "⚠️ 异常" if c.id in outlier_ids else "✅ 正常",
        })
    df_scatter = pd.DataFrame(scatter_data)

    fig = px.scatter(
        df_scatter, x="满足率(%)", y="费用(元)",
        color="类型",
        hover_name="物业名称",
        color_discrete_map={"⚠️ 异常": "#e74c3c", "✅ 正常": "#3498db"},
        size=[15] * len(df_scatter),
    )
    fig.update_layout(
        margin=dict(l=40, r=40, t=20, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=-0.2),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ====== 同质分组 ======
    st.subheader(f"📦 同质分组（共 {len(cluster_result.groups)} 组）")

    for i, group in enumerate(cluster_result.groups):
        member_contracts = [c for c in filtered if c.id in group.contract_ids]
        member_names = [c.property_name for c in member_contracts]

        labels = []
        if len(member_names) > 1:
            stats = (
                f"均价 {group.avg_price:.2f} 元 | "
                f"满足率 {group.avg_satisfaction * 100:.1f}% | "
                f"标准差 {group.price_std:.2f}"
            )
        else:
            stats = f"均价 {group.avg_price:.2f} 元 | 满足率 {group.avg_satisfaction * 100:.1f}% (单楼盘组)"

        with st.expander(f"组 {i + 1}: {len(member_names)} 个楼盘 | {stats}"):
            group_data = []
            for c in member_contracts:
                fee_val = getattr(c, fee_attr)
                is_outlier = c.id in outlier_ids
                deviation = ""
                if is_outlier:
                    matched = [o for o in cluster_result.outliers if o.contract_id == c.id]
                    if matched:
                        deviation = f"{matched[0].deviation_pct:+.1f}%"

                group_data.append({
                    "物业名称": c.property_name,
                    "费用(元)": fee_val,
                    "偏离幅度": deviation if is_outlier else "-",
                    "状态": "⚠️ 价格异常" if is_outlier else "✅ 正常",
                })
            st.dataframe(pd.DataFrame(group_data), use_container_width=True, hide_index=True)

    # ====== 价格异常汇总 ======
    if cluster_result.outliers:
        st.subheader("🚨 价格异常详情")
        outlier_data = []
        for o in cluster_result.outliers:
            outlier_data.append({
                "物业名称": o.property_name,
                "所属组": f"组{o.group_id}",
                "费用": f"{o.fee:.2f} 元",
                "组均价": f"{o.group_avg_fee:.2f} 元",
                "偏离": f"{o.deviation_pct:+.1f}%",
            })
        st.dataframe(pd.DataFrame(outlier_data), use_container_width=True, hide_index=True)

    # ====== 满足度矩阵 ======
    st.subheader("📋 全部合同满足度矩阵")
    matrix_data = []
    for c in filtered:
        c_results = results.get(c.id, [])
        report = calc_compliance_rate(c.id, c_results, standards)
        row = {
            "物业名称": c.property_name,
            "总满足率": f"{report.total_rate * 100:.1f}%",
            "费用(元)": getattr(c, fee_attr),
            "类型": "⚠️ 异常" if c.id in outlier_ids else "✅ 正常",
        }
        for lv in range(1, 6):
            row[f"L{lv}"] = f"{report.level_rates.get(lv, 0) * 100:.0f}%"
        for cat in report.category_rates:
            row[cat] = f"{report.category_rates[cat] * 100:.0f}%"
        matrix_data.append(row)
    st.dataframe(pd.DataFrame(matrix_data), use_container_width=True, hide_index=True)

    # ====== 分组价格箱线图 ======
    if len(cluster_result.groups) > 1:
        st.subheader("📊 分组价格分布")
        box_data = []
        for i, group in enumerate(cluster_result.groups):
            for cid in group.contract_ids:
                c = next((cc for cc in filtered if cc.id == cid), None)
                if c:
                    box_data.append({
                        "同质组": f"组{i + 1}",
                        "费用(元)": getattr(c, fee_attr),
                    })
        if box_data:
            df_box = pd.DataFrame(box_data)
            fig_box = px.box(df_box, x="同质组", y="费用(元)", color="同质组")
            fig_box.update_layout(margin=dict(l=40, r=40, t=20, b=20), showlegend=False)
            st.plotly_chart(fig_box, use_container_width=True)
