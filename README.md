# 13F Tracker MVP

一个可运行的 13F Tracker 最小可行产品（MVP），技术栈为 **Python 3.11 + Streamlit + SQLite**。

## 项目结构

```text
.
├── app.py
├── requirements.txt
├── README.md
├── tests/
│   ├── fixtures/
│   │   └── infotable_sample.xml
│   └── test_fetcher.py
└── src/
    ├── __init__.py
    ├── db.py
    └── fetcher.py
```

## 从零到运行

> 下面命令在仓库根目录执行。

1) 创建并激活虚拟环境（Python 3.11）

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

2) 安装依赖

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

3) 设置 SEC User-Agent（必需）

```bash
export SEC_USER_AGENT="YourAppName youremail@example.com"
```

> `SEC_USER_AGENT` 需要包含可联系信息；请勿将真实邮箱硬编码进源码。

4) 启动应用

```bash
streamlit run app.py
```

## SEC 拉取流程

首页输入 CIK（支持带/不带前导零），点击 **“从 SEC 更新该机构最新 13F”** 后会：

1. 使用 `data.sec.gov/submissions` 查找最新 `13F-HR` / `13F-HR/A`。
2. 构造 Archives 路径并定位 `infotable.xml`（优先 `index.json`，失败则回退 `-index.html`）。
3. 解析 XML 持仓并写入 SQLite：`institutions` / `filings` / `holdings`。
4. 在页面展示最新 filing 的 Top holdings。

请求层包含：
- 全局限流（<= 10 req/s）
- 429/5xx 重试与指数退避
- 默认 15 秒超时

## 页面说明

- **首页（机构列表）**：显示机构基础信息、CIK 输入与 SEC 拉取入口。
- **机构详情页**：查看机构所有 filings，按 `filing_date` 切换并查看 holdings。
- 点击页面顶部 **“载入示例数据”** 可写入 2 家机构的 mock 数据。

## 测试

```bash
pytest
```

包含：
- `test_parser_infotable_xml`
- `test_cik_padding`
- 网络相关流程的 mock 测试（不依赖外网）
