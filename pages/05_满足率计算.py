"""满足率计算页面 — 合规卡片、进度条、多合同对比"""
import os
import tempfile
import streamlit as st
import pandas as pd
import plotly.express as px
from engine.config import ConfigManager
from engine.cache import CacheManager
from engine.comparator import calc_compliance_rate

st.set_page_config(page_title="满足率计算", page_icon="📈", layout="wide")
st.title("📈 规范满足率计算")
st.caption("逐合同查看对五级规范的满足情况，支持多合同横向对比")

# -------- 路径初始化 --------
data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
cache_dir = os.path.join(data_dir, "cache")
config_path = os.path.join(data_dir, "config.json")
standards_path = os.path.join(data_dir, "standards.xlsx")

cfg = ConfigManager(config_path)
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
col_sel, col_filter = st.columns([2, 1])
with col_sel:
    selected = st.multiselect(
        "选择合同（可多选）",
        options=[c.property_name for c in contracts],
        default=[contracts[0].property_name] if contracts else [],
    )
with col_filter:
    level_filter = st.selectbox(
        "筛选举报等级（可选）",
        options=["全部"] + [f"{i}级" for i in range(1, 6)],
    )

# -------- 计算 --------
if selected and st.button("📊 计算满足率", type="primary", use_container_width=True):
    level_map = {f"{i}级": i for i in range(1, 6)}

    for name in selected:
        c = next((cc for cc in contracts if cc.property_name == name), None)
        if c is None:
            continue

        st.markdown(f"### 🏢 {name}")

        c_results = results.get(c.id, [])
        if not c_results:
            st.warning(f"该合同无匹配结果数据")
            continue

        # 如果有等级筛选，仅保留对应等级的结果
        if level_filter != "全部":
            filter_level = level_map[level_filter]
            filtered_standards = [s for s in standards if s.level == filter_level]
            filtered_ids = {s.id for s in filtered_standards}
            filtered_results = [r for r in c_results if r.standard_item_id in filtered_ids]
            report = calc_compliance_rate(c.id, filtered_results, filtered_standards)
        else:
            report = calc_compliance_rate(c.id, c_results, standards)

        # ====== 卡片 ======
        st.markdown("#### 满足率概览")
        cols = st.columns(6)
        cols[0].metric("总满足率", f"{report.total_rate * 100:.1f}%",
                       delta=f"{report.matched_count}/{report.total_count} 项")
        for i, lv in enumerate(range(1, 6)):
            rate = report.level_rates.get(lv, 0)
            cols[i + 1].metric(f"{lv}级", f"{rate * 100:.0f}%",
                               help=f"等级{lv}的满足率")

        # ====== 按大类分解（进度条 + 条形图） ======
        st.markdown("#### 按大类分解")

        cat_data = []
        for cat, rate in report.category_rates.items():
            cat_data.append({"大类": cat, "满足率": rate, "进度": int(rate * 100)})
        df_cat = pd.DataFrame(cat_data).sort_values("满足率", ascending=False)

        if not df_cat.empty:
            # 进度条列表
            cat_col1, cat_col2 = st.columns([1, 1])
            with cat_col1:
                for _, row in df_cat.iterrows():
                    cat_name = f"{row['大类']}"
                    pct = int(row["满足率"] * 100)
                    st.text(f"{cat_name}: {pct}%")
                    st.progress(row["满足率"])

            # 水平条形图
            with cat_col2:
                fig_bar = px.bar(
                    df_cat, x="满足率", y="大类",
                    orientation='h',
                    text=df_cat["满足率"].apply(lambda x: f"{x * 100:.0f}%"),
                    color="满足率",
                    color_continuous_scale="RdYlGn",
                    range_color=[0, 1],
                )
                fig_bar.update_layout(
                    xaxis=dict(title="满足率", range=[0, 1], tickformat=".0%"),
                    yaxis=dict(title=""),
                    margin=dict(l=10, r=10, t=10, b=10),
                    height=250,
                    coloraxis_showscale=False,
                )
                fig_bar.update_traces(textposition="outside")
                st.plotly_chart(fig_bar, use_container_width=True)

        # ====== 未满足条款 ======
        st.markdown("#### 未满足/部分满足条款")
        unmet = [r for r in c_results if r.verdict != "满足"]

        if not unmet:
            st.success("🎉 全部满足！")
        else:
            unmet_by_verdict = {}
            for r in unmet:
                unmet_by_verdict.setdefault(r.verdict, []).append(r)

            for verdict, items in unmet_by_verdict.items():
                icon = {"部分满足": "🟡", "不满足": "🔴", "不确定": "🟠"}.get(verdict, "⚪")
                with st.expander(f"{icon} {verdict} — {len(items)} 项"):
                    for r in items[:30]:
                        item_label = r.standard_item_id
                        # 查找对应规范条款的内容
                        std_item = next((s for s in standards if s.id == r.standard_item_id), None)
                        if std_item:
                            item_label += f" | {std_item.category} | L{std_item.level}"
                        st.markdown(f"**{item_label}**")
                        st.text(f"证据: {r.evidence[:200]}")
                        st.caption(f"置信度: {r.confidence:.0%} | 方法: {r.method}")
                        st.markdown("---")
                    if len(items) > 30:
                        st.caption(f"... 还有 {len(items) - 30} 项未显示")

        # ====== 导出按钮 ======
        st.markdown("#### 导出")
        from engine.report import export_compliance_report
        try:
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
                tmp_path = f.name
            export_compliance_report(report, tmp_path)
            with open(tmp_path, "rb") as fread:
                st.download_button(
                    label=f"📥 导出 {name} 满足率报告",
                    data=fread.read(),
                    file_name=f"{name}_满足率报告.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_{c.id}",
                )
            os.unlink(tmp_path)
        except Exception as e:
            st.error(f"导出失败: {e}")

        st.markdown("---")

    # ====== 多合同横向对比 ======
    if len(selected) > 1:
        st.markdown("### 📊 多合同横向对比")

        compare_data = []
        for name in selected:
            c = next((cc for cc in contracts if cc.property_name == name), None)
            if c:
                if level_filter != "全部":
                    fl = level_map[level_filter]
                    f_standards = [s for s in standards if s.level == fl]
                    f_ids = {s.id for s in f_standards}
                    f_results = [r for r in results.get(c.id, []) if r.standard_item_id in f_ids]
                    report = calc_compliance_rate(c.id, f_results, f_standards)
                else:
                    report = calc_compliance_rate(c.id, results.get(c.id, []), standards)

                row = {"物业名称": name, "总满足率": f"{report.total_rate * 100:.1f}%"}
                for lv in range(1, 6):
                    row[f"{lv}级"] = f"{report.level_rates.get(lv, 0) * 100:.0f}%"
                compare_data.append(row)

        df_compare = pd.DataFrame(compare_data)
        st.dataframe(df_compare, use_container_width=True, hide_index=True)

        # 对比条形图
        st.markdown("#### 满足率对比图")
        # 准备绘图数据
        plot_data = []
        for row_data in compare_data:
            for lv in range(1, 6):
                plot_data.append({
                    "物业名称": row_data["物业名称"],
                    "等级": f"{lv}级",
                    "满足率(%)": float(row_data[f"{lv}级"].replace("%", "")),
                })

        if plot_data:
            df_plot = pd.DataFrame(plot_data)
            fig_compare = px.bar(
                df_plot, x="等级", y="满足率(%)", color="物业名称",
                barmode="group",
                color_discrete_sequence=px.colors.qualitative.Set2,
            )
            fig_compare.update_layout(
                yaxis=dict(range=[0, 100]),
                margin=dict(l=40, r=40, t=20, b=20),
                legend=dict(orientation="h", yanchor="bottom", y=-0.25),
            )
            st.plotly_chart(fig_compare, use_container_width=True)

elif not selected:
    st.info("👈 请选择至少一个合同，然后点击「计算满足率」")
