"""首页 — 仪表盘"""
import os
import streamlit as st
from engine.config import ConfigManager
from engine.cache import CacheManager

st.title("🏠 物业合同分析智能体")
st.markdown("分析成都市天府新区物业合同，对比服务质量和价格")

# 数据状态
data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
cache_dir = os.path.join(data_dir, "cache")
standards_path = os.path.join(data_dir, "standards.xlsx")
meta_path = os.path.join(data_dir, "contracts_meta.xlsx")
contracts_dir = os.path.join(data_dir, "contracts")

config_path = os.path.join(data_dir, "config.json")
cache_mgr = CacheManager(cache_dir)
cfg = ConfigManager(config_path)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("📋 规范标准", "已就绪" if os.path.exists(standards_path) else "缺失")
with col2:
    pdf_count = len([f for f in os.listdir(contracts_dir) if f.endswith(".pdf")]) \
        if os.path.exists(contracts_dir) else 0
    st.metric("📄 合同PDF", f"{pdf_count} 份" if pdf_count else "缺失")
with col3:
    st.metric("📊 合同元数据", "已就绪" if os.path.exists(meta_path) else "缺失")
with col4:
    is_cached = cache_mgr.is_valid()
    st.metric("💾 缓存状态", "有效" if is_cached else "未初始化")

st.markdown("---")

# 快捷入口
st.subheader("快速开始")
qcol1, qcol2, qcol3 = st.columns(3)

with qcol1:
    st.page_link("pages/03_同价不同质.py", label="📊 同价不同质", icon="⚖️")
    st.caption("对比两个价格相近合同的物业服务差异")

with qcol2:
    st.page_link("pages/04_同质不同价.py", label="📊 同质不同价", icon="🔍")
    st.caption("批量分析找价格异常楼盘")

with qcol3:
    st.page_link("pages/05_满足率计算.py", label="📈 满足率计算", icon="📋")
    st.caption("计算合同对五级规范的满足率")

st.markdown("---")

# 数据初始化区域
st.subheader("⚡ 数据初始化")
st.info(
    "首次使用需初始化数据缓存。此操作将解析 PDF 合同、执行规则匹配和 LLM 判定，"
    "预计耗时 10-15 分钟，之后分析秒级响应。"
)

if st.button("🔄 初始化/刷新数据缓存", type="primary", use_container_width=True):
    config = cfg.load()

    if not config["llm"].get("api_key"):
        st.error("请先在「模型供应商配置」页面设置 API Key")
    else:
        with st.status("正在初始化...", expanded=True) as status:
            st.write("步骤 1/4: 加载规范标准和合同元数据...")
            st.write("步骤 2/4: 解析 PDF 合同...")
            st.write("步骤 3/4: 执行规则匹配...")
            st.write("步骤 4/4: LLM 语义判定...")
            try:
                from engine.preprocess import run_preprocessing
                stats = run_preprocessing(data_dir, config)
                status.update(label="初始化完成！", state="complete")
                st.success(
                    f"✅ {stats['contracts_loaded']} 份合同加载，"
                    f"{stats['pdfs_processed']} 份 PDF 处理，"
                    f"{stats['clauses_extracted']} 条服务条款提取，"
                    f"{stats['results_cached']} 份结果缓存"
                )
                st.rerun()
            except Exception as e:
                status.update(label="初始化失败", state="error")
                st.error(f"❌ 初始化失败: {e}")
