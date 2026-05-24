---
AIGC:
    ContentProducer: Minimax Agent AI
    ContentPropagator: Minimax Agent AI
    Label: AIGC
    ProduceID: "00000000000000000000000000000000"
    PropagateID: "00000000000000000000000000000000"
    ReservedCode1: 3046022100a149e98b1d1779744cd7ed71c34372f56dc6504ed24da90823b9e975780878d3022100ed3945977cd95ed268dfd03c96e344a6c0d1c304616aa0ac50303e760d1b160b
    ReservedCode2: 30460221009e3f20d420e5ff4ea97c959198e6b2856dc2fb76966ac44819f8e355a937e02902210082e5eb691f053055794c97c61b5bacf656bd93a1ceb5e7d5547a1a969c8899bf
---

# 软件架构设计

## 系统概述

代码依赖图分析系统用于分析 C++ 多仓库项目中的代码依赖关系，支持 Visual Studio 解决方案的精确解析。

## 架构图

```
┌─────────────────────────────────────────────────────────┐
│                     前端 (Static HTML)                    │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌───────────┐  │
│  │ 搜索面板 │  │ 依赖图   │  │ 详情面板 │  │ 设置面板  │  │
│  └────┬────┘  └────┬────┘  └────┬────┘  └─────┬─────┘  │
│       └──────────┬┴──────────┬┴──────────────┘         │
└─────────────────│───────────│────────────────────────┘
                  │   REST API  │ (JSON)
┌─────────────────│───────────│────────────────────────┐
│                 ▼           ▼                        │
│  ┌────────────────────────────────────────────────┐   │
│  │              FastAPI Backend                   │   │
│  │  ┌──────────┐ ┌──────────┐ ┌────────────────┐  │   │
│  │  │ 仓库管理  │ │ 层级管理  │ │   LLM 接口     │  │   │
│  │  └────┬─────┘ └────┬─────┘ └───────┬────────┘  │   │
│  │       │           │              │           │   │
│  │  ┌────▼───────────▼──────────────▼────────┐   │   │
│  │  │            数据库 (SQLite)             │   │   │
│  │  │  ┌────────┐ ┌────────┐ ┌────────────┐  │   │   │
│  │  │  │repos   │ │ symbols │ │dependencies│  │   │   │
│  │  │  └────────┘ └────────┘ └────────────┘  │   │   │
│  │  └────────────────────────────────────────┘   │   │
│  └────────────────────────────────────────────────┘   │
│                         │                              │
│  ┌──────────────────────▼──────────────────────────┐   │
│  │            Tree-sitter C++ Parser               │   │
│  │  ┌────────────┐  ┌────────────┐  ┌───────────┐  │   │
│  │  │ VS Project │  │ File Parser │  │ Hash Gen │  │   │
│  │  │  Resolver  │  │            │  │          │  │   │
│  │  └────────────┘  └────────────┘  └───────────┘  │   │
│  └────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────┘
```

## 核心模块

### 1. 后端服务 (main.py)

FastAPI 驱动的 REST API 服务，处理所有业务逻辑。

**职责**：
- 提供 REST API 接口
- 协调数据库和解析器
- 处理请求验证和响应格式化

**主要端点**：
- 仓库管理：`/api/repositories`
- 代码解析：`/api/repositories/{id}/parse`
- VS 解析：`/api/repositories/{id}/parse-vs`
- 符号搜索：`/api/symbols`
- 依赖图：`/api/graph`
- 层级管理：`/api/layers`
- LLM 接口：`/api/llm/*`

### 2. 数据模型 (models.py)

定义核心数据结构和枚举。

**数据结构**：

```
Repository
├── id: int
├── name: str
├── path: str
├── layer: str (SDK/LOGIC/BUSINESS/UI)
├── sln_path: str (可选，指定 .sln 文件)
├── remote_url: str
└── branch: str

Symbol
├── id: int
├── repository_id: int
├── name: str
├── kind: str (function/class/struct/enum)
├── file_path: str
├── line_number: int
├── namespace: str
├── signature: str
└── hash_value: str (注释无关的哈希)

Dependency
├── source_symbol_id: int
├── target_symbol_id: int
├── dependency_type: str (include/inheritance/call)
└── source_file/line
```

### 3. 数据库操作 (database.py)

SQLite 数据库管理，处理所有持久化操作。

**表结构**：
- `repositories`: 仓库信息
- `symbols`: 代码符号
- `dependencies`: 依赖关系
- `layers`: 可配置的层级定义

**核心操作**：
- CRUD 仓库、符号、层级
- 依赖关系查询
- 图数据聚合

### 4. 代码解析器 (parser.py)

Tree-sitter 驱动的 C++ 代码解析。

**子模块**：

#### VSProjectResolver
- `find_solution_files()`: 查找所有 .sln 文件
- `parse_solution()`: 解析 .sln 获取项目映射
- `parse_vcxproj()`: 解析 .vcxproj 获取源文件列表

#### MultiLayerCodeParser
- `parse_repository()`: 递归扫描解析
- `parse_vs_solution()`: VS 解决方案解析
- `parse_file()`: 单文件解析
- `_extract_symbols()`: 从 AST 提取符号
- `_generate_hash()`: 生成注释无关的哈希

**解析流程**：

```
1. 定位源文件
   ├── 自动发现 .sln 文件
   └── 解析 .vcxproj 获取 ClCompile/ClInclude

2. Tree-sitter AST 解析
   ├── 类/结构体定义
   ├── 函数定义/声明
   ├── 枚举定义
   └── 命名空间

3. 依赖提取
   ├── #include 解析
   └── 类型引用追踪

4. 哈希生成（注释无关）
   └── 基于 AST 结构
```

### 5. 前端 (static/index.html)

原生 HTML + D3.js 单页应用。

**组件**：
- 搜索面板：符号搜索和选择
- 依赖图：D3.js 力导向图可视化
- 详情面板：符号详情和依赖列表
- 设置弹窗：层级管理和仓库管理

**状态管理**：
```javascript
graphData      // 当前图数据
selectedSymbol // 选中的符号
LAYER_COLORS   // 层级颜色配置
```

## 数据流

### 1. 仓库解析流程

```
用户请求 parse-vs
    │
    ▼
main.py::parse_vs_solution()
    │
    ├── 获取仓库配置
    │
    ├── VSProjectResolver.find_solution_files()
    │       │
    │       └── glob("**/*.sln")
    │
    ├── VSProjectResolver.parse_solution()
    │       │
    │       ├── 解析 .sln 文件
    │       └── 调用 parse_vcxproj()
    │
    ├── MultiLayerCodeParser.parse_file() × N
    │       │
    │       ├── Tree-sitter 解析 AST
    │       ├── _extract_symbols()
    │       └── _extract_dependencies()
    │
    ├── db.create_symbols_batch()
    │
    └── db.create_dependency() × N
```

### 2. 符号搜索流程

```
用户输入关键词
    │
    ▼
searchSymbols()
    │
    └── GET /api/symbols?keyword=xxx
            │
            ▼
        db.search_symbols()
            │
            ├── 模糊匹配 name
            ├── 层级过滤 (可选)
            └── 类型过滤 (可选)
            │
            ▼
        返回 symbol 列表
            │
            ▼
    selectSymbol(symbolId)
        │
        ├── GET /api/symbols/{id}
        │
        ├── GET /api/graph/symbol/{id}?depth=1
        │
        ├── renderGraph()  // D3.js 渲染
        │
        └── renderDetail() // 详情面板
```

## 层级设计

系统支持可配置的代码层级：

| 层级 | 用途 | 默认颜色 |
|------|------|---------|
| SDK | 底层 SDK/库 | #4CAF50 |
| LOGIC | 业务逻辑层 | #2196F3 |
| BUSINESS | 业务层 | #FF9800 |
| UI | 用户界面层 | #9C27B0 |

用户可通过 API 添加自定义层级。

## 性能考虑

1. **节点限制**：前端限制最多 200 个节点
2. **Tick 节流**：D3 力模拟每 3 帧更新一次 DOM
3. **异步解析**：大仓库使用后台任务处理
4. **缓存机制**：已解析的文件不重复解析

## 扩展点

1. **更多语言支持**：添加 JavaScript/TypeScript 解析器
2. **依赖类型增强**：支持继承、组合等更细粒度依赖
3. **影响分析**：代码变更影响范围分析
4. **循环检测**：自动检测循环依赖