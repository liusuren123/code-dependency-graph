"""
多数据库管理器
支持每个仓库独立的数据库文件，实现完全的符号隔离
"""
import sqlite3
import os
from pathlib import Path
from typing import Dict, Optional
from contextlib import contextmanager

class RepoDatabase:
    """单个仓库的数据库"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_database()

    @contextmanager
    def _get_connection(self):
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
        """初始化仓库数据库表结构"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 符号表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS symbols (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                    UNIQUE(name, file_path, line_number)
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
                    UNIQUE(source_symbol_id, target_symbol_id, dependency_type, source_line)
                )
            """)

            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_symbols_hash ON symbols(hash_value)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_deps_source ON dependencies(source_symbol_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_deps_target ON dependencies(target_symbol_id)")

    def insert_symbol(self, name: str, kind: str, file_path: str, line_number: int = 0,
                      namespace: str = '', return_type: str = '', parameters: str = '[]',
                      signature: str = '', hash_value: str = '') -> int:
        """插入符号并返回ID"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO symbols
                (name, kind, file_path, line_number, namespace, return_type, parameters, signature, hash_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (name, kind, file_path, line_number, namespace, return_type, parameters, signature, hash_value))
            cursor.execute("SELECT last_insert_rowid() as id")
            return cursor.fetchone()['id']

    def insert_symbols_batch(self, symbols: list) -> int:
        """批量插入符号"""
        if not symbols:
            return 0
        count = 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for sym in symbols:
                if isinstance(sym, dict):
                    cursor.execute("""
                        INSERT OR IGNORE INTO symbols
                        (name, kind, file_path, line_number, namespace, return_type, parameters, signature, hash_value)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (sym.get('name'), sym.get('kind'), sym.get('file_path'),
                          sym.get('line_number', 0), sym.get('namespace', ''),
                          sym.get('return_type', ''), sym.get('parameters', '[]'),
                          sym.get('signature', ''), sym.get('hash_value', '')))
                else:
                    cursor.execute("""
                        INSERT OR IGNORE INTO symbols
                        (name, kind, file_path, line_number, namespace, return_type, parameters, signature, hash_value)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (sym.name, sym.kind, sym.file_path, sym.line_number,
                          sym.namespace, sym.return_type, sym.parameters,
                          sym.signature, sym.hash_value))
                count += 1
        return count

    def get_symbol_by_hash(self, hash_value: str):
        """通过hash获取符号"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM symbols WHERE hash_value = ?", (hash_value,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_symbols_by_hashes(self, hash_values: list) -> dict:
        """批量通过hash获取符号"""
        if not hash_values:
            return {}
        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join(['?'] * len(hash_values))
            cursor.execute(f"SELECT * FROM symbols WHERE hash_value IN ({placeholders})", hash_values)
            return {row['hash_value']: dict(row) for row in cursor.fetchall()}

    def insert_dependency(self, source_symbol_id: int, target_symbol_id: int,
                          dependency_type: str, source_file: str = '',
                          source_line: int = 0, target_file: str = '',
                          branch_type: str = '', branch_condition: str = '',
                          error_context: str = '') -> int:
        """插入依赖关系"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO dependencies
                (source_symbol_id, target_symbol_id, dependency_type, source_file, source_line,
                 target_file, branch_type, branch_condition, error_context)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (source_symbol_id, target_symbol_id, dependency_type, source_file,
                  source_line, target_file, branch_type, branch_condition, error_context))
            cursor.execute("SELECT last_insert_rowid() as id")
            return cursor.fetchone()['id']

    def get_dependencies_by_symbol(self, symbol_id: int, direction: str = "outgoing") -> list:
        """获取符号的依赖关系"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if direction == "outgoing":
                cursor.execute("""
                    SELECT d.*, s.name as target_name, s.file_path as target_file_path
                    FROM dependencies d
                    LEFT JOIN symbols s ON d.target_symbol_id = s.id
                    WHERE d.source_symbol_id = ?
                """, (symbol_id,))
            else:
                cursor.execute("""
                    SELECT d.*, s.name as source_name, s.file_path as source_file_path
                    FROM dependencies d
                    LEFT JOIN symbols s ON d.source_symbol_id = s.id
                    WHERE d.target_symbol_id = ?
                """, (symbol_id,))
            return [dict(row) for row in cursor.fetchall()]


class DatabaseManager:
    """
    多数据库管理器
    - 维护一个中心注册表，跟踪所有仓库数据库
    - 每个仓库有独立的数据库文件
    - 提供统一的接口访问
    """

    _instance = None

    def __new__(cls, data_dir: str = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, data_dir: str = None):
        if self._initialized:
            return

        self.data_dir = Path(data_dir) if data_dir else Path(__file__).parent.parent / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 中心注册数据库
        self.registry_db_path = str(self.data_dir / "_registry.db")
        self._init_registry()

        # 缓存已打开的仓库数据库连接
        self._repo_dbs: Dict[int, RepoDatabase] = {}

        self._initialized = True

    def _init_registry(self):
        """初始化中心注册数据库"""
        conn = sqlite3.connect(self.registry_db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()

            # 注册表 - 跟踪所有仓库数据库
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS repo_registry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    path TEXT NOT NULL,
                    layer TEXT NOT NULL,
                    db_file TEXT NOT NULL,
                    remote_url TEXT DEFAULT '',
                    branch TEXT DEFAULT 'main',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def _get_repo_db(self, repo_id: int) -> Optional[RepoDatabase]:
        """获取仓库数据库实例"""
        if repo_id not in self._repo_dbs:
            # 从注册表查找数据库文件位置
            conn = sqlite3.connect(self.registry_db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT path, db_file FROM repo_registry WHERE id = ?", (repo_id,))
                row = cursor.fetchone()
                if row:
                    repo_path = row['path']
                    db_file = row['db_file']
                    # 数据库存储在仓库目录下的 .codegraph 子目录
                    full_path = Path(repo_path) / ".codegraph" / db_file
                    if full_path.exists():
                        self._repo_dbs[repo_id] = RepoDatabase(str(full_path))
            finally:
                conn.close()

        return self._repo_dbs.get(repo_id)

    @contextmanager
    def get_repo_connection(self, repo_id: int):
        """获取仓库数据库连接"""
        repo_db = self._get_repo_db(repo_id)
        if repo_db:
            yield repo_db._get_connection()
        else:
            raise ValueError(f"Repository {repo_id} not found or not initialized")

    def register_repo(self, repo_id: int, name: str, path: str, layer: str, db_file: str, remote_url: str = "", branch: str = "main"):
        """注册新仓库到注册表"""
        conn = sqlite3.connect(self.registry_db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO repo_registry (id, name, path, layer, db_file, remote_url, branch)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (repo_id, name, path, layer, db_file, remote_url, branch))
            conn.commit()
        finally:
            conn.close()

    def unregister_repo(self, repo_id: int):
        """取消注册仓库"""
        # 关闭并移除缓存的数据库连接
        if repo_id in self._repo_dbs:
            del self._repo_dbs[repo_id]

        # 从注册表删除
        conn = sqlite3.connect(self.registry_db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM repo_registry WHERE id = ?", (repo_id,))
            conn.commit()
        finally:
            conn.close()

    def get_all_repos(self):
        """获取所有注册的仓库"""
        conn = sqlite3.connect(self.registry_db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM repo_registry ORDER BY id")
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def create_repo_db(self, repo_id: int, repo_path: str = None) -> RepoDatabase:
        """为仓库创建独立的数据库

        Args:
            repo_id: 仓库ID
            repo_path: 仓库本地路径，数据库将存储在 {repo_path}/.codegraph/ 目录下
        """
        if repo_path:
            # 存储在仓库目录下的 .codegraph 子目录
            codegraph_dir = Path(repo_path) / ".codegraph"
            codegraph_dir.mkdir(parents=True, exist_ok=True)
            db_file = "codegraph.db"
            full_path = codegraph_dir / db_file
        else:
            # 降级到 data 目录
            db_file = f"repo_{repo_id}.db"
            full_path = self.data_dir / db_file

        repo_db = RepoDatabase(str(full_path))
        self._repo_dbs[repo_id] = repo_db
        return repo_db

    def delete_repo_db(self, repo_id: int):
        """删除仓库数据库"""
        # 关闭连接
        if repo_id in self._repo_dbs:
            del self._repo_dbs[repo_id]

        # 从注册表获取仓库路径
        conn = sqlite3.connect(self.registry_db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT path FROM repo_registry WHERE id = ?", (repo_id,))
            row = cursor.fetchone()
            if row and row['path']:
                # 删除仓库目录下的 .codegraph/codegraph.db
                full_path = Path(row['path']) / ".codegraph" / "codegraph.db"
                if full_path.exists():
                    os.remove(full_path)
                # 可选：删除整个 .codegraph 目录（如果为空）
                codegraph_dir = full_path.parent
                if codegraph_dir.exists() and not any(codegraph_dir.iterdir()):
                    codegraph_dir.rmdir()
        finally:
            conn.close()

    def init_repo_from_main_db(self, repo_id: int, main_db_path: str):
        """
        从现有主数据库迁移仓库数据到独立数据库
        将指定 repo_id 的所有数据导出到独立数据库
        """
        repo_db = self.create_repo_db(repo_id)

        # 从主数据库读取数据
        conn_main = sqlite3.connect(main_db_path)
        conn_main.row_factory = sqlite3.Row
        try:
            cursor = conn_main.cursor()

            # 导出符号
            cursor.execute("SELECT * FROM symbols WHERE repository_id = ?", (repo_id,))
            symbols = cursor.fetchall()
            if symbols:
                with repo_db._get_connection() as conn_repo:
                    cursor_repo = conn_repo.cursor()
                    for sym in symbols:
                        cursor_repo.execute("""
                            INSERT OR IGNORE INTO symbols
                            (name, kind, file_path, line_number, namespace, return_type, parameters, signature, hash_value)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (sym['name'], sym['kind'], sym['file_path'], sym['line_number'],
                             sym['namespace'], sym['return_type'], sym['parameters'],
                             sym['signature'], sym['hash_value']))

            conn_main.commit()
        finally:
            conn_main.close()

        return repo_db
