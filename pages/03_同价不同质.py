"""同价不同质分析页面 — 两个合同的全维度对比"""
import os
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from engine.config import ConfigManager
from engine.cache import CacheManager
from engine.comparator import compare_two
from engine.llm import create_provider

st.set_page_config(page_title="同价不同质", page_icon="⚖️", layout="wide")
st.title("⚖️ 同价不同质分析")
st.caption("价格相近的两个合同，服务质量差在哪里？")

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
    col_empty, col_btn, _ = st.columns([1, 1, 2])
    with col_btn:
        if st.button("前往首页"):
            st.switch_page("pages/01_首页.py")
    st.stop()

# -------- 加载数据 --------
results = cache_mgr.load_results()
contracts = cache_mgr.get_contracts()

from engine.loader import load_standards
standards = load_standards(standards_path) if os.path.exists(standards_path) else []

contract_names = [c.property_name for c in contracts]

# -------- 控件 --------
st.markdown("### 选择对比参数")

col1, col2, col3 = st.columns(3)
with col1:
    fee_type = st.selectbox(
        "费用类型",
        options=["住宅物业费", "商业物业费", "车位费"],
        format_func=lambda x: x,
    )
with col2:
    c_a_name = st.selectbox("合同A", options=contract_names, key="ca")
with col3:
    # 默认选择与A不同的合同
    default_b_idx = 1 if len(contract_names) > 1 else 0
    c_b_name = st.selectbox(
        "合同B",
        options=contract_names,
        index=default_b_idx if contract_names[default_b_idx] != c_a_name else 0,
        key="cb",
    )

# -------- 获取选中的合同 --------
c_a = next((c for c in contracts if c.property_name == c_a_name), None)
c_b = next((c for c in contracts if c.property_name == c_b_name), None)

if c_a and c_b and c_a_name == c_b_name:
    st.warning("⚠️ 请选择两个不同的合同进行对比")

if c_a and c_b and c_a_name != c_b_name:
    fee_map = {"住宅物业费": "residential", "商业物业费": "commercial", "车位费": "parking"}
    ft = fee_map[fee_type]
    fee_attr = {
        "residential": "residential_fee",
        "commercial": "commercial_fee",
        "parking": "parking_fee",
    }[ft]

    fee_a = getattr(c_a, fee_attr)
    fee_b = getattr(c_b, fee_attr)

    st.markdown(f"**{c_a_name}**: {fee_a} 元 | **{c_b_name}**: {fee_b} 元")

    # 同价判定
    price_pct = float(config["thresholds"].get("similar_price_pct", 5))
    if fee_a > 0:
        diff_pct = abs(fee_a - fee_b) / fee_a * 100
        if diff_pct > price_pct:
            st.warning(f"⚠️ 价格差异 {diff_pct:.1f}%，超出同价阈值 ±{price_pct}%，但仍可对比")

    # 构建 LLM provider (可选)
    provider = None
    try:
        provider = create_provider(config)
    except Exception:
        pass

    if st.button("🔍 开始对比分析", type="primary", use_container_width=True):
        with st.spinner("分析中，正在对比条款..."):
            try:
                result = compare_two(c_a, c_b, ft, results, standards, config["thresholds"], provider)
            except Exception as e:
                st.error(f"分析出错: {e}")
                st.stop()

        st.success(f"分析完成！共对比 {result.a_report.total_count} 条规范")

        tab1, tab2, tab3, tab4 = st.tabs(["📊 对比总表", "🎯 雷达图", "📋 差异明细", "🤖 AI总结"])

        # ---- Tab 1: 对比总表 ----
        with tab1:
            col_a, col_b = st.columns(2)
            with col_a:
                st.metric(f"📊 {c_a_name}", f"{result.a_report.total_rate * 100:.1f}%")
            with col_b:
                st.metric(f"📊 {c_b_name}", f"{result.b_report.total_rate * 100:.1f}%")

            comp_df = pd.DataFrame([
                {"指标": "总满足率",
                 c_a_name: f"{result.a_report.total_rate * 100:.1f}%",
                 c_b_name: f"{result.b_report.total_rate * 100:.1f}%"},
                {"指标": "满足条款数",
                 c_a_name: result.a_report.matched_count,
                 c_b_name: result.b_report.matched_count},
                {"指标": "总条款数",
                 c_a_name: result.a_report.total_count,
                 c_b_name: result.b_report.total_count},
            ])
            st.dataframe(comp_df, use_container_width=True, hide_index=True)

            st.subheader("分等级满足率")
            level_data = []
            for lv in range(1, 6):
                level_data.append({
                    "等级": f"{lv}级",
                    c_a_name: f"{result.a_report.level_rates.get(lv, 0) * 100:.1f}%",
                    c_b_name: f"{result.b_report.level_rates.get(lv, 0) * 100:.1f}%",
                })
            st.dataframe(pd.DataFrame(level_data), use_container_width=True, hide_index=True)

            # 分大类对比
            st.subheader("分大类满足率")
            cat_data = []
            for cat in result.a_report.category_rates:
                cat_data.append({
                    "大类": cat,
                    c_a_name: f"{result.a_report.category_rates.get(cat, 0) * 100:.1f}%",
                    c_b_name: f"{result.b_report.category_rates.get(cat, 0) * 100:.1f}%",
                })
            st.dataframe(pd.DataFrame(cat_data), use_container_width=True, hide_index=True)

        # ---- Tab 2: 雷达图 ----
        with tab2:
            categories = list(result.a_report.category_rates.keys())
            if categories:
                fig = go.Figure()
                fig.add_trace(go.Scatterpolar(
                    r=[result.a_report.category_rates.get(c, 0) * 100 for c in categories],
                    theta=categories,
                    fill='toself',
                    name=c_a_name,
                    line=dict(color='#1f77b4'),
                ))
                fig.add_trace(go.Scatterpolar(
                    r=[result.b_report.category_rates.get(c, 0) * 100 for c in categories],
                    theta=categories,
                    fill='toself',
                    name=c_b_name,
                    line=dict(color='#ff7f0e'),
                ))
                fig.update_layout(
                    polar=dict(radial=dict(range=[0, 100], tickformat=".0f")),
                    legend=dict(orientation="h", yanchor="bottom", y=-0.15),
                    margin=dict(l=40, r=40, t=20, b=60),
                )
                st.plotly_chart(fig, use_container_width=True)

            # 分等级柱状图对比
            st.subheader("分等级满足率对比")
            levels = list(range(1, 6))
            bar_fig = go.Figure()
            bar_fig.add_trace(go.Bar(
                name=c_a_name,
                x=[f"{lv}级" for lv in levels],
                y=[result.a_report.level_rates.get(lv, 0) * 100 for lv in levels],
                marker_color='#1f77b4',
            ))
            bar_fig.add_trace(go.Bar(
                name=c_b_name,
                x=[f"{lv}级" for lv in levels],
                y=[result.b_report.level_rates.get(lv, 0) * 100 for lv in levels],
                marker_color='#ff7f0e',
            ))
            bar_fig.update_layout(
                yaxis=dict(title="满足率 (%)", range=[0, 100]),
                legend=dict(orientation="h", yanchor="bottom", y=-0.2),
                margin=dict(l=40, r=40, t=20, b=60),
            )
            st.plotly_chart(bar_fig, use_container_width=True)

        # ---- Tab 3: 差异明细 ----
        with tab3:
            diff_col1, diff_col2 = st.columns(2)

            with diff_col1:
                st.subheader(f"🟢 {c_a_name} 独有满足")
                st.caption(f"共 {len(result.a_only_items)} 项")
                if result.a_only_items:
                    a_only_df = pd.DataFrame([
                        {"条款ID": i.standard_item_id, "证据": i.evidence[:120],
                         "置信度": f"{i.confidence:.0%}", "方法": i.method}
                        for i in result.a_only_items
                    ])
                    st.dataframe(a_only_df, use_container_width=True, hide_index=True)
                else:
                    st.info("无独有满足项")

            with diff_col2:
                st.subheader(f"🟢 {c_b_name} 独有满足")
                st.caption(f"共 {len(result.b_only_items)} 项")
                if result.b_only_items:
                    b_only_df = pd.DataFrame([
                        {"条款ID": i.standard_item_id, "证据": i.evidence[:120],
                         "置信度": f"{i.confidence:.0%}", "方法": i.method}
                        for i in result.b_only_items
                    ])
                    st.dataframe(b_only_df, use_container_width=True, hide_index=True)
                else:
                    st.info("无独有满足项")

            st.markdown("---")
            st.subheader(f"🔴 双方都不满足")
            st.caption(f"共 {len(result.both_missing)} 项")
            if result.both_missing:
                missing_df = pd.DataFrame([
                    {"条款ID": i.standard_item_id, "证据": i.evidence[:120]}
                    for i in result.both_missing[:50]
                ])
                st.dataframe(missing_df, use_container_width=True, hide_index=True)
                if len(result.both_missing) > 50:
                    st.caption(f"... 还有 {len(result.both_missing) - 50} 项未显示")
            else:
                st.success("没有双方都不满足的条款")

        # ---- Tab 4: AI 总结 ----
        with tab4:
            st.markdown("### 🤖 智能分析总结")
            st.info(result.summary)

            # 性价比评估
            st.markdown("### 📊 性价比评估")
            a_rate = result.a_report.total_rate
            b_rate = result.b_report.total_rate
            fee_a_val = fee_a if fee_a > 0 else 1
            fee_b_val = fee_b if fee_b > 0 else 1

            a_value = a_rate / fee_a_val * 100
            b_value = b_rate / fee_b_val * 100

            eval_col1, eval_col2 = st.columns(2)
            with eval_col1:
                st.metric(f"{c_a_name} 性价比指数", f"{a_value:.2f}",
                          delta=f"{a_value - b_value:+.2f}" if a_value != b_value else None)
            with eval_col2:
                st.metric(f"{c_b_name} 性价比指数", f"{b_value:.2f}",
                          delta=f"{b_value - a_value:+.2f}" if a_value != b_value else None)

            if a_value > b_value:
                st.success(f"🏆 {c_a_name} 的性价比更高")
            elif b_value > a_value:
                st.success(f"🏆 {c_b_name} 的性价比更高")
            else:
                st.info("两个合同的性价比相当")
