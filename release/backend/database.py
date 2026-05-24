"""
SQLite 数据库操作
"""
import sqlite3
import json
from datetime import datetime
from typing import List, Optional, Tuple, Dict
from contextlib import contextmanager
from pathlib import Path

from models import Repository, Symbol, Dependency, LayerConfig, DEFAULT_LAYERS

DATABASE_PATH = Path(__file__).parent.parent / "data" / "dependency.db"

class Database:
    """SQLite 数据库管理类"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DATABASE_PATH)
        self._init_database()

    @contextmanager
    def _get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _init_database(self):
        """初始化数据库表结构"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 仓库表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS repositories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    layer TEXT NOT NULL,
                    remote_url TEXT DEFAULT '',
                    branch TEXT DEFAULT 'main',
                    parent_repo_id INTEGER,
                    parent_repo_branch TEXT DEFAULT 'main',
                    sln_path TEXT DEFAULT '',  -- VS 解决方案文件路径
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (parent_repo_id) REFERENCES repositories(id),
                    UNIQUE(name, branch)
                )
            """)

            # 符号表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS symbols (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repository_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line_number INTEGER DEFAULT 0,
                    namespace TEXT DEFAULT '',
                    return_type TEXT DEFAULT '',
                    parameters TEXT DEFAULT '[]',
                    signature TEXT DEFAULT '',
                    hash_value TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (repository_id) REFERENCES repositories(id),
                    UNIQUE(repository_id, name, file_path, line_number)
                )
            """)

            # 依赖关系表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dependencies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_symbol_id INTEGER NOT NULL,
                    target_symbol_id INTEGER NOT NULL,
                    dependency_type TEXT NOT NULL,
                    source_file TEXT DEFAULT '',
                    source_line INTEGER DEFAULT 0,
                    target_file TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    branch_type TEXT DEFAULT '',
                    branch_condition TEXT DEFAULT '',
                    error_context TEXT DEFAULT '',
                    FOREIGN KEY (source_symbol_id) REFERENCES symbols(id),
                    FOREIGN KEY (target_symbol_id) REFERENCES symbols(id),
                    UNIQUE(source_symbol_id, target_symbol_id, dependency_type, source_line)
                )
            """)

            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_symbols_repo ON symbols(repository_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_symbols_hash ON symbols(hash_value)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_deps_source ON dependencies(source_symbol_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_deps_target ON dependencies(target_symbol_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_deps_branch ON dependencies(branch_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_repos_layer ON repositories(layer)")

            # 层级配置表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS layers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    color TEXT DEFAULT '#666666',
                    description TEXT DEFAULT '',
                    layer_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 初始化默认层级（如果不存在）
            for i, layer in enumerate(DEFAULT_LAYERS):
                cursor.execute("""
                    INSERT OR IGNORE INTO layers (name, color, description, layer_order)
                    VALUES (?, ?, ?, ?)
                """, (layer['name'], layer['color'], layer['description'], i))

            # 数据流表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS data_flows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_symbol_id INTEGER NOT NULL,
                    target_symbol_id INTEGER,
                    flow_type TEXT NOT NULL,
                    source_param TEXT DEFAULT '',
                    target_param TEXT DEFAULT '',
                    detail TEXT DEFAULT '',
                    file_path TEXT DEFAULT '',
                    line_number INTEGER DEFAULT 0,
                    FOREIGN KEY (source_symbol_id) REFERENCES symbols(id),
                    FOREIGN KEY (target_symbol_id) REFERENCES symbols(id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_df_source ON data_flows(source_symbol_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_df_target ON data_flows(target_symbol_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_df_type ON data_flows(flow_type)")

            # 错误处理路径表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS error_paths (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol_id INTEGER,
                    error_type TEXT NOT NULL,
                    function TEXT DEFAULT '',
                    file_path TEXT NOT NULL,
                    line_number INTEGER DEFAULT 0,
                    caught_type TEXT DEFAULT '',
                    caught_types TEXT DEFAULT '[]',
                    thrown_expression TEXT DEFAULT '',
                    contained_calls TEXT DEFAULT '[]',
                    repository_id INTEGER,
                    FOREIGN KEY (symbol_id) REFERENCES symbols(id),
                    FOREIGN KEY (repository_id) REFERENCES repositories(id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ep_symbol ON error_paths(symbol_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ep_type ON error_paths(error_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ep_repo ON error_paths(repository_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_deps_error_ctx ON dependencies(error_context)")

    # ========== 仓库操作 ==========

    def create_repository(self, repo: Repository) -> int:
        """创建新仓库"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO repositories (name, path, layer, remote_url, branch, parent_repo_id, parent_repo_branch, sln_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (repo.name, repo.path, repo.layer, repo.remote_url, repo.branch,
                  repo.parent_repo_id, repo.parent_repo_branch, repo.sln_path))
            return cursor.lastrowid

    def get_repository(self, repo_id: int) -> Optional[Repository]:
        """获取仓库信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM repositories WHERE id = ?", (repo_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_repository(row)
            return None

    def get_repository_by_name_branch(self, name: str, branch: str) -> Optional[Repository]:
        """根据名称和分支获取仓库"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM repositories WHERE name = ? AND branch = ?",
                (name, branch)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_repository(row)
            return None

    def list_repositories(self, layer: str = None) -> List[Repository]:
        """列出所有仓库"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if layer:
                cursor.execute(
                    "SELECT * FROM repositories WHERE layer = ? ORDER BY layer, name",
                    (layer,)
                )
            else:
                cursor.execute("SELECT * FROM repositories ORDER BY layer, name")
            return [self._row_to_repository(row) for row in cursor.fetchall()]

    def delete_repository(self, repo_id: int):
        """删除仓库及其所有关联数据"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 先删除依赖关系到符号
            cursor.execute("""
                DELETE FROM dependencies
                WHERE source_symbol_id IN (SELECT id FROM symbols WHERE repository_id = ?)
                   OR target_symbol_id IN (SELECT id FROM symbols WHERE repository_id = ?)
            """, (repo_id, repo_id))
            # 删除符号
            cursor.execute("DELETE FROM symbols WHERE repository_id = ?", (repo_id,))
            # 删除仓库
            cursor.execute("DELETE FROM repositories WHERE id = ?", (repo_id,))

    def update_repository(self, repo_id: int, updates: dict):
        """更新仓库信息"""
        if not updates:
            return
        sets = [f"{k} = ?" for k in updates.keys()]
        values = list(updates.values()) + [repo_id]
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE repositories SET {', '.join(sets)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", values)

    # ========== 符号操作 ==========

    def create_symbol(self, symbol: Symbol) -> int:
        """创建符号"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO symbols
                (repository_id, name, kind, file_path, line_number, namespace,
                 return_type, parameters, signature, hash_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (symbol.repository_id, symbol.name, symbol.kind, symbol.file_path,
                  symbol.line_number, symbol.namespace, symbol.return_type,
                  symbol.parameters, symbol.signature, symbol.hash_value))
            return cursor.lastrowid

    def create_symbols_batch(self, symbols: List[Symbol]) -> int:
        """批量创建符号（优化版）"""
        if not symbols:
            return 0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 使用 executemany 进行真正的批量插入
            data = [
                (s.repository_id, s.name, s.kind, s.file_path, s.line_number,
                 s.namespace, s.return_type, s.parameters, s.signature, s.hash_value)
                for s in symbols
            ]
            cursor.executemany("""
                INSERT OR IGNORE INTO symbols
                (repository_id, name, kind, file_path, line_number, namespace,
                 return_type, parameters, signature, hash_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, data)
            return cursor.rowcount

    def get_symbol(self, symbol_id: int) -> Optional[Symbol]:
        """获取符号"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM symbols WHERE id = ?", (symbol_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_symbol(row)
            return None

    def get_symbol_by_hash(self, hash_value: str, repository_id: int = None) -> Optional[Symbol]:
        """根据 hash 获取符号"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if repository_id:
                cursor.execute(
                    "SELECT * FROM symbols WHERE hash_value = ? AND repository_id = ?",
                    (hash_value, repository_id)
                )
            else:
                cursor.execute("SELECT * FROM symbols WHERE hash_value = ?", (hash_value,))
            row = cursor.fetchone()
            if row:
                return self._row_to_symbol(row)
            return None

    def get_symbols_by_hashes(self, hash_values: List[str], repository_id: int) -> Dict[str, Symbol]:
        """批量根据 hash 获取符号（优化版）"""
        if not hash_values:
            return {}

        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join(['?'] * len(hash_values))
            cursor.execute(f"""
                SELECT * FROM symbols
                WHERE repository_id = ? AND hash_value IN ({placeholders})
            """, [repository_id] + hash_values)
            return {row['hash_value']: self._row_to_symbol(row) for row in cursor.fetchall()}

    def list_symbols(
        self,
        repository_id: int = None,
        layer: str = None,
        kind: str = None,
        keyword: str = None,
        limit: int = 1000,
        offset: int = 0
    ) -> List[Symbol]:
        """列出符号"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            conditions = []
            params = []

            if repository_id:
                conditions.append("s.repository_id = ?")
                params.append(repository_id)
            if layer:
                conditions.append("r.layer = ?")
                params.append(layer)
            if kind:
                kinds = [k.strip() for k in kind.split(',')]
                if len(kinds) == 1:
                    conditions.append("s.kind = ?")
                    params.append(kinds[0])
                else:
                    placeholders = ','.join(['?'] * len(kinds))
                    conditions.append(f"s.kind IN ({placeholders})")
                    params.extend(kinds)
            if keyword:
                conditions.append("s.name LIKE ? OR s.signature LIKE ?")
                params.extend([f"%{keyword}%", f"%{keyword}%"])

            query = """
                SELECT s.* FROM symbols s
                JOIN repositories r ON s.repository_id = r.id
            """
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY s.name LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            return [self._row_to_symbol(row) for row in cursor.fetchall()]

    def count_symbols(self, repository_id: int = None, layer: str = None) -> int:
        """统计符号数量"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            conditions = []
            params = []

            if repository_id:
                conditions.append("repository_id = ?")
                params.append(repository_id)
            if layer:
                conditions.append("repository_id IN (SELECT id FROM repositories WHERE layer = ?)")
                params.append(layer)

            query = "SELECT COUNT(*) FROM symbols"
            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            cursor.execute(query, params)
            return cursor.fetchone()[0]

    # ========== 依赖关系操作 ==========

    def create_dependency(self, dep: Dependency) -> int:
        """创建或更新依赖关系"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO dependencies
                (source_symbol_id, target_symbol_id, dependency_type, source_file, source_line, target_file, branch_type, branch_condition, error_context)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_symbol_id, target_symbol_id, dependency_type, source_line)
                DO UPDATE SET error_context = COALESCE(NULLIF(?, ''), error_context),
                              branch_type = COALESCE(NULLIF(?, ''), branch_type),
                              branch_condition = COALESCE(NULLIF(?, ''), branch_condition)
            """, (dep.source_symbol_id, dep.target_symbol_id, dep.dependency_type,
                  dep.source_file, dep.source_line, dep.target_file,
                  dep.branch_type, dep.branch_condition, dep.error_context,
                  dep.error_context, dep.branch_type, dep.branch_condition))
            return cursor.lastrowid

    def create_dependencies_batch(self, deps: List[Dependency]) -> int:
        """批量创建依赖关系（优化版）"""
        if not deps:
            return 0

        count = 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 使用 executemany 进行真正的批量插入
            data = [
                (dep.source_symbol_id, dep.target_symbol_id, dep.dependency_type,
                 dep.source_file, dep.source_line, dep.target_file,
                 dep.branch_type, dep.branch_condition, dep.error_context)
                for dep in deps
            ]
            cursor.executemany("""
                INSERT OR IGNORE INTO dependencies
                (source_symbol_id, target_symbol_id, dependency_type, source_file, source_line, target_file, branch_type, branch_condition, error_context)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, data)
            return cursor.rowcount

    def get_dependencies_by_symbol(self, symbol_id: int, direction: str = "outgoing") -> List[dict]:
        """获取符号的依赖关系"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if direction == "outgoing":
                cursor.execute("""
                    SELECT d.*, s_target.name as target_name, s_target.kind as target_kind,
                           r_target.layer as target_layer, s_target.signature as target_signature,
                           s_source.name as source_name
                    FROM dependencies d
                    JOIN symbols s_source ON d.source_symbol_id = s_source.id
                    JOIN repositories r_source ON s_source.repository_id = r_source.id
                    JOIN symbols s_target ON d.target_symbol_id = s_target.id
                    JOIN repositories r_target ON s_target.repository_id = r_target.id
                    WHERE d.source_symbol_id = ?
                """, (symbol_id,))
            else:
                cursor.execute("""
                    SELECT d.*, s_source.name as source_name, s_source.kind as source_kind,
                           r_source.layer as source_layer, s_source.signature as source_signature,
                           s_target.name as target_name
                    FROM dependencies d
                    JOIN symbols s_source ON d.source_symbol_id = s_source.id
                    JOIN repositories r_source ON s_source.repository_id = r_source.id
                    JOIN symbols s_target ON d.target_symbol_id = s_target.id
                    JOIN repositories r_target ON s_target.repository_id = r_target.id
                    WHERE d.target_symbol_id = ?
                """, (symbol_id,))
            return [dict(row) for row in cursor.fetchall()]

    # ========== 图数据操作 ==========

    def get_graph_data(
        self,
        repository_id: int = None,
        layer: str = None,
        max_nodes: int = 500
    ) -> dict:
        """获取图数据"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 获取节点 - 包括常规符号和虚拟 include 目标
            conditions = []
            params = []

            if repository_id:
                conditions.append("r.id = ?")
                params.append(repository_id)
            if layer:
                conditions.append("r.layer = ?")
                params.append(layer)

            # 获取常规符号节点
            query = """
                SELECT s.*, r.layer, r.name as repo_name
                FROM symbols s
                JOIN repositories r ON s.repository_id = r.id
            """
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += """
                ORDER BY (
                    SELECT COUNT(*) FROM dependencies d
                    WHERE d.source_symbol_id = s.id OR d.target_symbol_id = s.id
                ) DESC, s.kind DESC, s.name
            """
            query += f" LIMIT {max_nodes}"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            nodes = []
            node_id_map = {}  # symbol_id -> node_id
            symbol_id_to_data = {}
            included_ids = set()

            for row in rows:
                node_id = f"node_{row['id']}"
                node_id_map[row['id']] = node_id
                symbol_id_to_data[row['id']] = dict(row)
                included_ids.add(row['id'])

                nodes.append({
                    "id": node_id,
                    "label": row['name'],
                    "kind": row['kind'],
                    "layer": row['layer'],
                    "namespace": row['namespace'],
                    "file": row['file_path'],
                    "line": row['line_number'],
                    "signature": row['signature']
                })

            # 获取边 - 只要 source 或 target 在节点中就返回
            symbol_ids = list(node_id_map.keys())
            edges = []

            if symbol_ids:
                placeholders = ','.join(['?'] * len(symbol_ids))
                cursor.execute(f"""
                    SELECT d.*, s_source.name as source_name, s_target.name as target_name
                    FROM dependencies d
                    JOIN symbols s_source ON d.source_symbol_id = s_source.id
                    JOIN symbols s_target ON d.target_symbol_id = s_target.id
                    WHERE d.source_symbol_id IN ({placeholders})
                       OR d.target_symbol_id IN ({placeholders})
                """, symbol_ids + symbol_ids)

                for row in cursor.fetchall():
                    source_node = node_id_map.get(row['source_symbol_id'])
                    target_node = node_id_map.get(row['target_symbol_id'])

                    # 如果 target 不在节点列表中，创建虚拟节点
                    row_dict = dict(row)
                    if not target_node and row['target_symbol_id'] not in included_ids:
                        target_id = row['target_symbol_id']
                        node_id_map[target_id] = f"node_{target_id}"
                        nodes.append({
                            "id": f"node_{target_id}",
                            "label": row['target_name'],
                            "kind": "include",
                            "layer": "SDK",
                            "namespace": "",
                            "file": row_dict.get('target_file', ''),
                            "line": 0,
                            "signature": ""
                        })
                        included_ids.add(target_id)
                        target_node = f"node_{target_id}"

                    if source_node and target_node:
                        edges.append({
                            "source": source_node,
                            "target": target_node,
                            "type": row_dict['dependency_type'],
                            "source_file": row_dict['source_file'],
                            "source_line": row_dict['source_line']
                        })

            # 统计信息
            cursor.execute("""
                SELECT layer, COUNT(*) as count
                FROM repositories
                GROUP BY layer
            """)
            layer_stats = {row['layer']: row['count'] for row in cursor.fetchall()}

            cursor.execute("""
                SELECT r.layer, COUNT(*) as count
                FROM symbols s
                JOIN repositories r ON s.repository_id = r.id
                GROUP BY r.layer
            """)
            symbol_stats = {row['layer']: row['count'] for row in cursor.fetchall()}

            return {
                "nodes": nodes,
                "edges": edges,
                "layers": list(layer_stats.keys()),
                "statistics": {
                    "total_nodes": len(nodes),
                    "total_edges": len(edges),
                    "repositories_by_layer": layer_stats,
                    "symbols_by_layer": symbol_stats
                }
            }

    def get_layer_dependencies(self) -> List[dict]:
        """获取层级间的依赖关系"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT r1.layer as source_layer, r2.layer as target_layer,
                       COUNT(*) as dependency_count
                FROM dependencies d
                JOIN symbols s1 ON d.source_symbol_id = s1.id
                JOIN symbols s2 ON d.target_symbol_id = s2.id
                JOIN repositories r1 ON s1.repository_id = r1.id
                JOIN repositories r2 ON s2.repository_id = r2.id
                WHERE r1.layer != r2.layer
                GROUP BY r1.layer, r2.layer
                ORDER BY r1.layer, r2.layer
            """)
            return [dict(row) for row in cursor.fetchall()]

    # ========== 搜索操作 ==========

    def search_symbols(
        self,
        keyword: str = None,
        layer: str = None,
        kind: str = None,
        repository_id: int = None,
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[List[Symbol], int]:
        """搜索符号"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            conditions = []
            params = []

            if keyword:
                conditions.append("(s.name LIKE ? OR s.signature LIKE ? OR s.namespace LIKE ?)")
                params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
            if layer:
                conditions.append("r.layer = ?")
                params.append(layer)
            if kind:
                kinds = [k.strip() for k in kind.split(',')]
                if len(kinds) == 1:
                    conditions.append("s.kind = ?")
                    params.append(kinds[0])
                else:
                    placeholders = ','.join(['?'] * len(kinds))
                    conditions.append(f"s.kind IN ({placeholders})")
                    params.extend(kinds)
            if repository_id:
                conditions.append("s.repository_id = ?")
                params.append(repository_id)

            # 统计总数
            count_query = """
                SELECT COUNT(*) FROM symbols s
                JOIN repositories r ON s.repository_id = r.id
            """
            if conditions:
                count_query += " WHERE " + " AND ".join(conditions)
            cursor.execute(count_query, params)
            total = cursor.fetchone()[0]

            # 分页查询
            offset = (page - 1) * page_size
            query = """
                SELECT s.*, r.layer, r.name as repo_name
                FROM symbols s
                JOIN repositories r ON s.repository_id = r.id
            """
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY s.name LIMIT ? OFFSET ?"
            params.extend([page_size, offset])

            cursor.execute(query, params)
            symbols = [self._row_to_symbol(row) for row in cursor.fetchall()]

            return symbols, total

    # ========== 辅助方法 ==========

    def _row_to_repository(self, row) -> Repository:
        # 转换为字典以安全访问字段
        row_dict = dict(row) if hasattr(row, 'keys') else row
        return Repository(
            id=row_dict['id'],
            name=row_dict['name'],
            path=row_dict['path'],
            layer=row_dict['layer'],
            remote_url=row_dict['remote_url'],
            branch=row_dict['branch'],
            parent_repo_id=row_dict['parent_repo_id'],
            parent_repo_branch=row_dict['parent_repo_branch'],
            sln_path=row_dict.get('sln_path', ''),
            created_at=datetime.fromisoformat(row_dict['created_at']) if row_dict['created_at'] else None,
            updated_at=datetime.fromisoformat(row_dict['updated_at']) if row_dict['updated_at'] else None
        )

    def _row_to_symbol(self, row) -> Symbol:
        row_dict = dict(row) if hasattr(row, 'keys') else row
        return Symbol(
            id=row_dict['id'],
            repository_id=row_dict['repository_id'],
            name=row_dict['name'],
            kind=row_dict['kind'],
            file_path=row_dict['file_path'],
            line_number=row_dict['line_number'],
            namespace=row_dict['namespace'],
            return_type=row_dict['return_type'],
            parameters=row_dict['parameters'],
            signature=row_dict['signature'],
            hash_value=row_dict['hash_value'],
            created_at=datetime.fromisoformat(row_dict['created_at']) if row_dict['created_at'] else None
        )

    # ========== 层级管理 ==========

    def list_layers(self) -> List[dict]:
        """获取所有层级配置"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM layers ORDER BY layer_order")
            return [dict(row) for row in cursor.fetchall()]

    def get_layer(self, name: str) -> Optional[dict]:
        """获取单个层级配置"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM layers WHERE name = ?", (name,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def create_layer(self, name: str, color: str = "#666666",
                    description: str = "", layer_order: int = None) -> int:
        """创建新层级"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 如果没有指定顺序，放在最后
            if layer_order is None:
                cursor.execute("SELECT MAX(layer_order) as max_order FROM layers")
                result = cursor.fetchone()
                layer_order = (result['max_order'] or 0) + 1

            cursor.execute("""
                INSERT INTO layers (name, color, description, layer_order)
                VALUES (?, ?, ?, ?)
            """, (name, color, description, layer_order))
            return cursor.lastrowid

    def update_layer(self, name: str, updates: dict) -> bool:
        """更新层级配置"""
        if not updates:
            return False

        sets = [f"{k} = ?" for k in updates.keys()]
        values = list(updates.values()) + [name]

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE layers SET {', '.join(sets)} WHERE name = ?",
                values
            )
            return cursor.rowcount > 0

    def delete_layer(self, name: str) -> bool:
        """删除层级（如果有仓库使用则不允许删除）"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 检查是否有仓库使用此层级
            cursor.execute(
                "SELECT COUNT(*) as count FROM repositories WHERE layer = ?",
                (name,)
            )
            if cursor.fetchone()['count'] > 0:
                return False

            cursor.execute("DELETE FROM layers WHERE name = ?", (name,))
            return cursor.rowcount > 0

    def get_symbols_by_file(self, file_path: str) -> List[Symbol]:
        """获取指定文件中的所有符号"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM symbols WHERE file_path = ? ORDER BY line_number",
                (file_path,)
            )
            rows = cursor.fetchall()
            return [Symbol(**dict(row)) for row in rows]

    def get_symbols_by_names_across_repos(self, names: list, exclude_repo_id: int = None) -> List[Symbol]:
        """跨仓库按名称批量查找符号"""
        if not names:
            return []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join(['?'] * len(names))
            query = f"SELECT * FROM symbols WHERE name IN ({placeholders})"
            params = list(names)
            if exclude_repo_id:
                query += " AND repository_id != ?"
                params.append(exclude_repo_id)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [Symbol(**dict(row)) for row in rows]

    def get_class_members(self, class_symbol_id: int) -> List[Symbol]:
        """获取指定class的所有成员符号"""
        symbol = self.get_symbol(class_symbol_id)
        if not symbol or symbol.kind not in ('class', 'struct'):
            return []

        members = []
        seen_ids = set()
        class_name = symbol.name

        # 1. header 文件中类定义范围内的成员（声明）
        file_symbols = self.get_symbols_by_file(symbol.file_path)
        class_start = symbol.line_number
        class_end = class_start + 500

        for sym in file_symbols:
            if sym.id == class_symbol_id:
                continue
            if class_start < sym.line_number <= class_end:
                if sym.kind in ('function', 'method', 'variable', 'class', 'struct', 'enum', 'typedef'):
                    if sym.id not in seen_ids:
                        members.append(sym)
                        seen_ids.add(sym.id)

        # 2. 对应 .cpp 文件中的函数实现
        from pathlib import Path
        h_stem = Path(symbol.file_path).stem
        cpp_candidates = []

        # 方式1：直接 .h → .cpp 替换
        direct_cpp = symbol.file_path.replace('.h', '.cpp')
        if direct_cpp != symbol.file_path:
            cpp_candidates.append(direct_cpp)

        # 方式2：搜索数据库中同名 .cpp 文件（处理 include/src 分目录情况）
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT file_path FROM symbols WHERE file_path LIKE ? AND kind = 'function'",
                (f'%/{h_stem}.cpp',)
            )
            for row in cursor.fetchall():
                path = row['file_path'] if isinstance(row, dict) else row[0]
                if path not in cpp_candidates:
                    cpp_candidates.append(path)

            # Windows 路径也搜索
            cursor.execute(
                "SELECT DISTINCT file_path FROM symbols WHERE file_path LIKE ? AND kind = 'function'",
                (f'%\\{h_stem}.cpp',)
            )
            for row in cursor.fetchall():
                path = row['file_path'] if isinstance(row, dict) else row[0]
                if path not in cpp_candidates:
                    cpp_candidates.append(path)

        for cpp_path in cpp_candidates:
            cpp_stem = Path(cpp_path).stem
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM symbols WHERE file_path = ? AND kind = 'function' ORDER BY line_number",
                    (cpp_path,)
                )
                rows = cursor.fetchall()
                for row in rows:
                    sym = Symbol(**dict(row))
                    if sym.id in seen_ids:
                        continue
                    if cpp_stem == class_name:
                        members.append(sym)
                        seen_ids.add(sym.id)
                    else:
                        sig = sym.signature or ''
                        prefix = f"{class_name}::"
                        if sym.name == class_name or prefix in sig:
                            members.append(sym)
                            seen_ids.add(sym.id)

        return members

    # ========== 数据流操作 ==========

    def create_data_flow(self, flow) -> int:
        """创建数据流记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO data_flows (source_symbol_id, target_symbol_id, flow_type,
                    source_param, target_param, detail, file_path, line_number)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (flow.source_symbol_id, flow.target_symbol_id, flow.flow_type,
                  flow.source_param, flow.target_param, flow.detail,
                  flow.file_path, flow.line_number))
            return cursor.lastrowid

    def get_data_flows_by_source(self, symbol_id: int) -> List[dict]:
        """获取指定符号作为源的所有数据流"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT df.*, s.name as target_name
                FROM data_flows df
                LEFT JOIN symbols s ON df.target_symbol_id = s.id
                WHERE df.source_symbol_id = ?
                ORDER BY df.line_number
            """, (symbol_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_data_flows_by_target(self, symbol_id: int) -> List[dict]:
        """获取指定符号作为目标的所有数据流"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT df.*, s.name as source_name
                FROM data_flows df
                LEFT JOIN symbols s ON df.source_symbol_id = s.id
                WHERE df.target_symbol_id = ?
                ORDER BY df.line_number
            """, (symbol_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_log_outputs(self, symbol_id: int) -> List[dict]:
        """获取指定符号的日志输出"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM data_flows
                WHERE source_symbol_id = ? AND flow_type = 'log_output'
                ORDER BY line_number
            """, (symbol_id,))
            return [dict(row) for row in cursor.fetchall()]

    # ========== 错误处理路径操作 ==========

    def create_error_path(self, ep: dict) -> int:
        """创建错误处理路径记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO error_paths (symbol_id, error_type, function, file_path, line_number,
                    caught_type, caught_types, thrown_expression, contained_calls, repository_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ep.get('symbol_id'),
                ep.get('error_type', ''),
                ep.get('function', ''),
                ep.get('file_path', ''),
                ep.get('line', ep.get('line_number', 0)),
                ep.get('caught_type', ''),
                json.dumps(ep.get('caught_types', []), ensure_ascii=False),
                ep.get('thrown_expression', ''),
                json.dumps(ep.get('contained_calls', []), ensure_ascii=False),
                ep.get('repository_id'),
            ))
            return cursor.lastrowid

    def get_error_paths_by_symbol(self, symbol_id: int) -> List[dict]:
        """获取指定符号的错误处理路径"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM error_paths WHERE symbol_id = ?
                ORDER BY line_number
            """, (symbol_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_error_paths_by_file(self, file_path: str) -> List[dict]:
        """获取指定文件的错误处理路径"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM error_paths WHERE file_path = ?
                ORDER BY line_number
            """, (file_path,))
            return [dict(row) for row in cursor.fetchall()]

    def get_error_paths_by_repo(self, repo_id: int) -> List[dict]:
        """获取指定仓库的所有错误处理路径"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ep.*, s.name as symbol_name
                FROM error_paths ep
                LEFT JOIN symbols s ON ep.symbol_id = s.id
                WHERE ep.repository_id = ?
                ORDER BY ep.file_path, ep.line_number
            """, (repo_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_throw_to_catch_chain(self, symbol_id: int) -> dict:
        """获取从 throw 到 catch 的异常传播链"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM error_paths
                WHERE symbol_id = ? AND error_type = 'throw_statement'
                ORDER BY line_number
            """, (symbol_id,))
            throws = [dict(row) for row in cursor.fetchall()]
            if throws:
                repo_id = throws[0].get('repository_id')
                cursor.execute("""
                    SELECT * FROM error_paths
                    WHERE repository_id = ? AND error_type = 'catch_handler'
                    ORDER BY line_number
                """, (repo_id,))
                catches = [dict(row) for row in cursor.fetchall()]
                return {'throws': throws, 'catches': catches}
            return {'throws': throws, 'catches': []}
