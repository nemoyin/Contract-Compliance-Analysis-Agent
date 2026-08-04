"""物业合同分析智能体 — Streamlit 入口"""
import streamlit as st

st.set_page_config(
    page_title="物业合同分析智能体",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Streamlit 会自动发现 pages/ 目录下的页面文件
# 导航通过左侧 sidebar 的 pages 自动生成

st.sidebar.markdown("## 🏢 物业合同分析智能体")
st.sidebar.markdown("---")

# 重定向到首页
st.switch_page("pages/01_首页.py")
