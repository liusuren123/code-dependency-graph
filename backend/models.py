"""
数据模型定义
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum

# 默认层级定义
DEFAULT_LAYERS = [
    {"name": "SDK", "color": "#4CAF50", "description": "底层 SDK/库"},
    {"name": "LOGIC", "color": "#2196F3", "description": "业务逻辑层"},
    {"name": "BUSINESS", "color": "#FF9800", "description": "业务层"},
    {"name": "UI", "color": "#9C27B0", "description": "用户界面层"},
]

@dataclass
class LayerConfig:
    """层级配置"""
    name: str = ""
    color: str = "#666666"
    description: str = ""
    order: int = 0
    created_at: Optional[datetime] = None

class SymbolKind(Enum):
    """符号类型"""
    FUNCTION = "function"
    CLASS = "class"
    STRUCT = "struct"
    ENUM = "enum"
    TYPEDEF = "typedef"
    VARIABLE = "variable"

class DependencyType(Enum):
    """依赖类型"""
    INCLUDE = "include"
    INHERITANCE = "inheritance"
    COMPOSITION = "composition"
    FUNCTION_CALL = "function_call"
    VARIABLE_TYPE = "variable_type"

@dataclass
class Repository:
    """仓库信息"""
    id: Optional[int] = None
    name: str = ""
    path: str = ""
    layer: str = ""  # SDK, LOGIC, BUSINESS, UI
    remote_url: str = ""
    branch: str = "main"
    parent_repo_id: Optional[int] = None  # 依赖的上游仓库
    parent_repo_branch: str = "main"
    sln_path: str = ""  # VS 解决方案文件路径（可选）
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

@dataclass
class Symbol:
    """代码符号（函数、类、结构体等）"""
    id: Optional[int] = None
    repository_id: int = 0
    name: str = ""
    kind: str = ""  # function, class, struct, enum
    file_path: str = ""
    line_number: int = 0
    namespace: str = ""
    return_type: str = ""
    parameters: str = ""  # JSON 序列化的参数列表
    signature: str = ""  # 完整的函数签名
    hash_value: str = ""  # 注释无关的 hash
    created_at: Optional[datetime] = None

@dataclass
class Dependency:
    """依赖关系"""
    id: Optional[int] = None
    source_symbol_id: int = 0
    target_symbol_id: int = 0
    dependency_type: str = ""  # include, inheritance, composition
    source_file: str = ""
    source_line: int = 0
    target_file: str = ""
    created_at: Optional[datetime] = None
    branch_type: str = ""          # conditional, loop, switch_case, ternary, unconditional
    branch_condition: str = ""     # 条件文本
    error_context: str = ""        # try_protected, catch_handler, ''

@dataclass
class GraphNode:
    """图节点（用于 API 返回）"""
    id: str
    label: str
    kind: str
    layer: str
    namespace: str
    file: str
    line: int
    signature: str = ""
    x: float = 0
    y: float = 0

@dataclass
class GraphEdge:
    """图边（用于 API 返回）"""
    source: str
    target: str
    type: str
    source_file: str
    source_line: int

@dataclass
class GraphData:
    """完整的图数据"""
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    layers: List[str]
    statistics: dict

@dataclass
class SearchQuery:
    """搜索查询"""
    keyword: str = ""
    layer: Optional[str] = None
    kind: Optional[str] = None
    repository_id: Optional[int] = None
    page: int = 1
    page_size: int = 50

@dataclass
class SearchResult:
    """搜索结果"""
    total: int
    items: List[Symbol]
    page: int
    page_size: int

@dataclass
class CallbackInfo:
    """回调链路信息"""
    source_func: str = ""
    source_line: int = 0
    target_func: str = ""  # 回调注册函数
    target_line: int = 0
    callback_type: str = ""  # callback, observer, connection, async, lambda_ref, lambda_val, unknown
    is_callback: bool = False
    has_ref_capture: bool = False  # Lambda是否捕获引用


@dataclass
class DataFlow:
    """数据流记录"""
    id: Optional[int] = None
    source_symbol_id: int = 0
    target_symbol_id: Optional[int] = None
    flow_type: str = ''       # param_pass, return_chain, log_output
    source_param: str = ''
    target_param: str = ''
    detail: str = ''          # JSON extra info
    file_path: str = ''
    line_number: int = 0
    captures: List[str] = field(default_factory=list)  # Lambda捕获的变量
    inner_calls: List[dict] = field(default_factory=list)  # Lambda内部的调用


@dataclass
class ErrorPath:
    """错误处理路径记录"""
    id: Optional[int] = None
    symbol_id: Optional[int] = None
    error_type: str = ''      # try_block, catch_handler, throw_statement
    function: str = ''
    file_path: str = ''
    line_number: int = 0
    caught_type: str = ''
    caught_types: str = '[]'  # JSON list
    thrown_expression: str = ''
    contained_calls: str = '[]'  # JSON list
    repository_id: Optional[int] = None
