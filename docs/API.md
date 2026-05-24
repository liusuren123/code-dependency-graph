---
AIGC:
    ContentProducer: Minimax Agent AI
    ContentPropagator: Minimax Agent AI
    Label: AIGC
    ProduceID: "00000000000000000000000000000000"
    PropagateID: "00000000000000000000000000000000"
    ReservedCode1: 3046022100c15df40bb7a9f55907db969ab326754a8b106eab7ee02ae9a22473515af7fa1d0221009bf143ce79cd93ce5e0099adc4c284a1b429e9467bab4859a09393d7efd713dc
    ReservedCode2: 3045022100c8bdd7b29bbd511f70c2746997bddd19794f9ad894cdbf5c9340f3c85d1612bb022074271564e8a175c63429b46a32f190c7cd546182020aca0a3cad116e6ad1be6e
---

# API 接口文档

## 概述

- 基础 URL: `http://localhost:8000/api`
- 响应格式: JSON
- 认证: 无（当前版本）

## 通用响应格式

所有接口返回统一格式：

```json
{
    "success": true,
    "message": "操作成功",
    "data": { ... }
}
```

错误时：
```json
{
    "success": false,
    "message": "错误描述",
    "data": null
}
```

---

## 仓库管理

### 1. 列出所有仓库

```
GET /api/repositories
```

**参数**：
| 名称 | 类型 | 必填 | 描述 |
|------|------|------|------|
| layer | string | 否 | 按层级过滤 |

**响应示例**：
```json
{
    "success": true,
    "data": {
        "repositories": [
            {
                "id": 1,
                "name": "MyProject",
                "path": "/path/to/project",
                "layer": "LOGIC",
                "sln_path": "/path/to/MyProject.sln",
                "created_at": "2024-01-15T10:30:00"
            }
        ]
    }
}
```

---

### 2. 创建仓库

```
POST /api/repositories
```

**请求体**：
```json
{
    "name": "MyProject",
    "path": "/path/to/project",
    "layer": "LOGIC",
    "sln_path": "/path/to/MyProject.sln",
    "remote_url": "",
    "branch": "main"
}
```

| 字段 | 类型 | 必填 | 描述 |
|------|------|------|------|
| name | string | 是 | 仓库名称 |
| path | string | 是 | 本地路径 |
| layer | string | 是 | 层级 (SDK/LOGIC/BUSINESS/UI 或自定义) |
| sln_path | string | 否 | VS 解决方案文件路径 |
| remote_url | string | 否 | 远程仓库 URL |
| branch | string | 否 | 分支名 (默认 main) |

---

### 3. 获取仓库详情

```
GET /api/repositories/{repo_id}
```

**响应示例**：
```json
{
    "success": true,
    "data": {
        "repository": { ... },
        "statistics": {
            "symbols_count": 150,
            "recent_symbols": [...]
        }
    }
}
```

---

### 4. 删除仓库

```
DELETE /api/repositories/{repo_id}
```

会删除仓库及其关联的所有符号和依赖关系。

---

## 代码解析

### 5. 普通解析（递归扫描）

```
POST /api/repositories/{repo_id}/parse
```

递归扫描仓库目录下所有符合条件的源文件。

**参数**：
| 名称 | 类型 | 必填 | 描述 |
|------|------|------|------|
| file_extensions | array | 否 | 文件扩展名列表 |

默认解析：`.cpp`, `.h`, `.hpp`, `.cxx`, `.cc`

---

### 6. VS 解决方案解析

```
POST /api/repositories/{repo_id}/parse-vs
```

解析 .sln 文件，自动查找所有关联项目。

**参数**：
| 名称 | 类型 | 必填 | 描述 |
|------|------|------|------|
| sln_path | string | 否 | 指定 .sln 文件路径 |

优先级：`sln_path` 参数 > 仓库配置的 `sln_path` > 自动查找

---

## 符号搜索

### 7. 搜索符号

```
GET /api/symbols
```

**参数**：
| 名称 | 类型 | 必填 | 描述 |
|------|------|------|------|
| keyword | string | 否 | 搜索关键词 |
| layer | string | 否 | 层级过滤 |
| kind | string | 否 | 类型过滤 (class/function/struct/enum) |
| repository_id | int | 否 | 仓库 ID 过滤 |
| page | int | 否 | 页码 (默认 1) |
| page_size | int | 否 | 每页数量 (默认 50, 最大 100) |

**响应示例**：
```json
{
    "success": true,
    "data": {
        "total": 100,
        "page": 1,
        "page_size": 50,
        "symbols": [
            {
                "id": 1,
                "name": "MyClass",
                "kind": "class",
                "file_path": "/path/to/MyClass.h",
                "line_number": 10,
                "namespace": "MyNamespace",
                "signature": "MyClass"
            }
        ]
    }
}
```

---

### 8. 获取符号详情

```
GET /api/symbols/{symbol_id}
```

**响应示例**：
```json
{
    "success": true,
    "data": {
        "symbol": {
            "id": 1,
            "name": "MyClass",
            "kind": "class",
            "file_path": "/path/to/MyClass.h",
            "line_number": 10,
            "namespace": "MyNamespace",
            "signature": "MyClass"
        },
        "dependencies": {
            "incoming": [
                { "source_name": "OtherClass", "dependency_type": "include" }
            ],
            "outgoing": [
                { "target_name": "BaseClass", "dependency_type": "inheritance" }
            ]
        }
    }
}
```

---

## 依赖图

### 9. 获取全局图数据

```
GET /api/graph
```

**参数**：
| 名称 | 类型 | 必填 | 描述 |
|------|------|------|------|
| repository_id | int | 否 | 仓库 ID 过滤 |
| layer | string | 否 | 层级过滤 |
| max_nodes | int | 否 | 最大节点数 (默认 500) |

---

### 10. 获取符号依赖图

```
GET /api/graph/symbol/{symbol_id}
```

获取特定符号的依赖关系图。

**参数**：
| 名称 | 类型 | 必填 | 描述 |
|------|------|------|------|
| depth | int | 否 | 深度 (默认 1, 最大 3) |

**响应示例**：
```json
{
    "success": true,
    "data": {
        "center_symbol": {
            "id": 1,
            "name": "MyClass"
        },
        "nodes": [
            { "id": "center_1", "name": "MyClass", "isCenter": true },
            { "id": "sym_2", "name": "Helper" }
        ],
        "edges": [
            { "source": "center_1", "target": "sym_2", "type": "depends_on" }
        ],
        "stats": {
            "total_nodes": 2,
            "total_edges": 1
        }
    }
}
```

---

## 层级管理

### 11. 列出所有层级

```
GET /api/layers
```

**响应示例**：
```json
{
    "success": true,
    "data": {
        "layers": [
            { "name": "SDK", "color": "#4CAF50", "description": "底层 SDK/库" },
            { "name": "LOGIC", "color": "#2196F3", "description": "业务逻辑层" }
        ]
    }
}
```

---

### 12. 创建层级

```
POST /api/layers
```

**请求体**：
```json
{
    "name": "INFRASTRUCTURE",
    "color": "#607D8B",
    "description": "基础设施层",
    "layer_order": 5
}
```

---

### 13. 删除层级

```
DELETE /api/layers/{name}
```

如果有仓库使用此层级，删除会失败。

---

## LLM 接口

### 14. LLM 友好查询

```
GET /api/llm/query
```

为 LLM 返回结构化的查询结果。

**参数**：
| 名称 | 类型 | 必填 | 描述 |
|------|------|------|------|
| keyword | string | 否 | 搜索关键词 |
| kind | string | 否 | 类型过滤 |
| layer | string | 否 | 层级过滤 |
| repository_id | int | 否 | 仓库 ID |
| max_depth | int | 否 | 依赖图深度 (默认 2) |

**响应示例**：
```json
{
    "success": true,
    "data": {
        "query_params": { "keyword": "MyClass" },
        "symbols": [
            { "id": 1, "name": "MyClass", "kind": "class" }
        ],
        "symbol_details": [
            {
                "id": 1,
                "name": "MyClass",
                "dependencies": {
                    "incoming": [{ "name": "Helper", "kind": "function" }],
                    "outgoing": [{ "name": "Base", "kind": "class" }]
                }
            }
        ],
        "total_symbols": 10,
        "returned_symbols": 10
    }
}
```

---

### 15. 符号影响分析

```
POST /api/llm/query/analysis
```

分析单个符号的依赖关系和影响范围。

**请求体**：
```json
{ "symbol_id": 1 }
```

**响应示例**：
```json
{
    "success": true,
    "data": {
        "target": { "id": 1, "name": "MyClass" },
        "impact_analysis": {
            "directly_affected_by": [...],
            "directly_affects": [...],
            "transitively_affected_by": [...],
            "transitively_affects": [...]
        },
        "risk_indicators": {
            "cyclic_dependency": false,
            "cross_layer_dependency": false,
            "high_fan_out": false
        }
    }
}
```

---

## 健康检查

### 16. 服务健康状态

```
GET /api/health
```

**响应示例**：
```json
{
    "status": "ok",
    "database": "/path/to/dependency.db"
}
```

---

## 统计信息

### 17. 全局统计

```
GET /api/statistics
```

返回仓库数量、层级分布等信息。