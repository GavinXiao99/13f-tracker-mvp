from __future__ import annotations

import pandas as pd
import streamlit as st

from src.db import fetch_holdings_by_institution, fetch_institutions, load_sample_data
from src.fetcher import health_check_dependencies

st.set_page_config(page_title="13F Tracker MVP", layout="wide")

st.title("13F Tracker MVP")
st.caption("Python + Streamlit + SQLite demo")

if st.button("载入示例数据"):
    load_sample_data()
    st.success("已载入 2 家机构的示例持仓数据。")

page = st.sidebar.radio("页面", ["首页（机构列表）", "机构详情页"])

if page == "首页（机构列表）":
    st.subheader("机构列表")
    institutions = fetch_institutions()
    if not institutions:
        st.info("暂无数据，请先点击“载入示例数据”。")
    else:
        st.dataframe(pd.DataFrame(institutions), use_container_width=True)

    with st.expander("技术栈依赖检查"):
        st.json(health_check_dependencies())

elif page == "机构详情页":
    st.subheader("机构详情")
    institutions = fetch_institutions()
    if not institutions:
        st.info("暂无机构，请先在首页点击“载入示例数据”。")
    else:
        options = {f"{item['name']} ({item['cik']})": item for item in institutions}
        selected_label = st.selectbox("选择机构", list(options.keys()))
        selected = options[selected_label]
        holdings = fetch_holdings_by_institution(selected["id"])

        st.markdown(f"**CIK:** `{selected['cik']}`")
        if holdings:
            df = pd.DataFrame(holdings)
            st.dataframe(df, use_container_width=True)
            st.metric("持仓总市值（USD）", f"{int(df['value_usd'].sum()):,}")
        else:
            st.warning("该机构暂无持仓数据。")
