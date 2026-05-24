---
AIGC:
    ContentProducer: Minimax Agent AI
    ContentPropagator: Minimax Agent AI
    Label: AIGC
    ProduceID: "00000000000000000000000000000000"
    PropagateID: "00000000000000000000000000000000"
    ReservedCode1: 3045022045333e7715d2a1383318bc386f82a68a59aca072c4e03908b86aba03c81a7bf0022100c6bbb4248dd636b3d549f454e4ceb05fba9cb0c32730ed8c6b18980064a8ce05
    ReservedCode2: 304502202b559dbcb08e579395b9b818986ff2d5ec3570b9a34cdad354679e4813fe0701022100cc721ba35e7fe6ba3c02af111c86bade53e7e9c7bb7de4dfb95f12bf95f8999e
---

# 代码依赖图分析系统

用于 C++ 多仓库代码依赖分析和可视化。

## 功能特性

- **多仓库支持**：支持同时分析多个仓库（SDK、LOGIC、BUSINESS、UI 等层级）
- **VS 项目解析**：自动解析 `.sln` 和 `.vcxproj` 文件，精准定位源文件
- **符号提取**：使用 Tree-sitter 解析 C++ 代码，提取类、函数、结构体等符号
- **依赖关系**：自动分析 `#include` 依赖和函数调用关系
- **可视化展示**：D3.js 力导向图展示依赖关系
- **LLM 友好**：提供结构化 API，便于 LLM 理解和调用
- **可配置层级**：支持自定义代码层级和颜色

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | FastAPI + SQLite |
| 代码解析 | Tree-sitter |
| 前端 | 原生 HTML + D3.js |
| 部署 | 静态文件服务 |

## 快速开始

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 启动服务

```bash
cd backend
python main.py
```

服务地址：`http://localhost:8000`

### 3. 日志文件

日志默认输出到 `backend/../logs/app.log`，包含：
- 仓库创建/删除操作
- 代码解析进度和结果
- 解析耗时统计
- 错误和警告信息

可使用 `tail -f logs/app.log` 实时查看日志。

### 4. 使用页面

1. 打开 `http://localhost:8000` 查看前端页面
2. 点击右上角 **"设置"** 按钮
3. 添加仓库，指定路径和层级
4. 点击 **"VS解析"** 解析仓库
5. 在左侧搜索符号，点击查看依赖图

## 项目结构

```
code-dependency-graph/
├── backend/              # 后端服务
│   ├── main.py          # FastAPI 主服务
│   ├── models.py         # 数据模型
│   ├── database.py       # SQLite 数据库操作
│   ├── parser.py         # Tree-sitter 代码解析器
│   └── requirements.txt  # Python 依赖
├── static/               # 前端静态文件（已部署）
│   └── index.html       # 主页面
└── frontend/            # 原始前端源码（未使用）
    └── src/
```

## API 接口

### 仓库管理

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/repositories` | GET | 列出所有仓库 |
| `/api/repositories` | POST | 创建仓库 |
| `/api/repositories/{id}` | DELETE | 删除仓库 |

### 代码解析

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/repositories/{id}/parse` | POST | 普通解析（递归扫描） |
| `/api/repositories/{id}/parse-vs` | POST | VS 解决方案解析 |

### 符号搜索

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/symbols` | GET | 搜索符号 |
| `/api/symbols/{id}` | GET | 获取符号详情 |

### 依赖图

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/graph` | GET | 获取全局图数据 |
| `/api/graph/symbol/{id}` | GET | 获取符号依赖图 |

### 层级管理

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/layers` | GET | 列出所有层级 |
| `/api/layers` | POST | 创建新层级 |
| `/api/layers/{name}` | DELETE | 删除层级 |

### LLM 接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/llm/query` | GET | LLM 友好查询 |
| `/api/llm/query/analysis` | POST | 符号影响分析 |

详细 API 文档见 `docs/API.md`