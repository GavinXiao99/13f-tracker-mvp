from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from src.db import (
    fetch_filings_by_institution,
    fetch_holdings_by_filing,
    fetch_institutions,
    load_sample_data,
    save_filing_and_holdings,
)
from src.fetcher import (
    No13FFilingError,
    SecEdgarClient,
    SecEdgarError,
    download_latest_infotable_xml,
    fetch_latest_13f_metadata,
    health_check_dependencies,
    normalize_cik,
    parse_infotable_xml,
)

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

    st.divider()
    st.subheader("从 SEC 更新机构最新 13F")
    sec_user_agent = os.getenv("SEC_USER_AGENT", "").strip()
    if not sec_user_agent:
        st.error("未检测到 SEC_USER_AGENT 环境变量。请先设置后再请求 SEC 数据。")
    cik_input = st.text_input("CIK（可输入带/不带前导零）", placeholder="例如 1234 或 0000001234")

    if st.button("从 SEC 更新该机构最新 13F"):
        if not sec_user_agent:
            st.error("请先设置 SEC_USER_AGENT，例如：YourAppName youremail@example.com")
        else:
            try:
                cik = normalize_cik(cik_input)
                client = SecEdgarClient(user_agent=sec_user_agent)
                metadata = fetch_latest_13f_metadata(client, cik)
                xml_text = download_latest_infotable_xml(client, metadata)
                holdings_df = parse_infotable_xml(xml_text)
                if holdings_df.empty:
                    raise SecEdgarError("infotable 解析成功但没有持仓行。")

                save_filing_and_holdings(
                    cik=metadata.cik,
                    institution_name=metadata.institution_name,
                    accession=metadata.accession,
                    filing_date=metadata.filing_date,
                    report_period=metadata.report_period,
                    holdings_df=holdings_df,
                )

                st.success(
                    f"拉取成功：{metadata.institution_name} 最新 filing date = {metadata.filing_date}"
                )
                st.dataframe(holdings_df.head(10), use_container_width=True)
            except ValueError as exc:
                st.error(f"输入错误：{exc}")
            except No13FFilingError as exc:
                st.warning(str(exc))
            except SecEdgarError as exc:
                st.error(f"SEC 请求失败：{exc}")
            except Exception as exc:  # noqa: BLE001
                st.error(f"处理失败：{exc}")

    with st.expander("技术栈依赖检查"):
        st.json(health_check_dependencies())

elif page == "机构详情页":
    st.subheader("机构详情")
    institutions = fetch_institutions()
    if not institutions:
        st.info("暂无机构，请先在首页点击“载入示例数据”或从 SEC 拉取。")
    else:
        options = {f"{item['name']} ({item['cik']})": item for item in institutions}
        selected_label = st.selectbox("选择机构", list(options.keys()))
        selected = options[selected_label]

        filings = fetch_filings_by_institution(selected["id"])
        st.markdown(f"**CIK:** `{selected['cik']}`")

        if not filings:
            st.warning("该机构暂无 filing 数据。")
        else:
            filing_options = {
                f"{row['filing_date']} | {row['accession']}": row for row in filings
            }
            selected_filing_label = st.selectbox(
                "选择 filing（默认最新）",
                list(filing_options.keys()),
                index=0,
            )
            selected_filing = filing_options[selected_filing_label]
            holdings = fetch_holdings_by_filing(selected_filing["id"])
            if holdings:
                df = pd.DataFrame(holdings)
                st.dataframe(df, use_container_width=True)
                st.metric("持仓总市值（value）", f"{int(df['value'].sum()):,}")
            else:
                st.warning("该 filing 暂无持仓数据。")
