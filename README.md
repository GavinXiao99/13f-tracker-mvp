# 13F Tracker MVP

一个可运行的 13F Tracker 最小可行产品（MVP），技术栈为 **Python 3.11 + Streamlit + SQLite**。

## 项目结构

```text
.
├── app.py
├── requirements.txt
├── README.md
├── data/
│   └── 13f.db   # 运行时自动创建（已加入 .gitignore）
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

3) 启动应用

```bash
streamlit run app.py
```

启动后浏览器会打开本地页面（默认 `http://localhost:8501`）。

## 页面说明

- **首页（机构列表）**：显示机构基础信息。
- **机构详情页**：选择机构后查看其持仓明细和总市值。
- 点击页面顶部 **“载入示例数据”** 可写入 2 家机构的 mock holdings，用于演示 UI 与数据库流程。

## 数据库说明

- SQLite 文件路径固定：`data/13f.db`
- 数据库不存在时会自动创建并初始化表结构。
- `data/13f.db` 已加入 `.gitignore`，避免提交运行时数据库文件或潜在敏感信息。
