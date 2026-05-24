"""
FastAPI 主服务
代码依赖图本地服务
"""
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from pathlib import Path
import uvicorn
import logging
import os
import hashlib
from datetime import datetime

from database import Database
from models import Repository, Symbol, Dependency
from parser import MultiLayerCodeParser
from database_manager import DatabaseManager
import asyncio

# ========== 日志配置 ==========
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 日志格式
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 配置根日志
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=DATE_FORMAT,
    handlers=[
        logging.StreamHandler(),  # 控制台输出
        logging.FileHandler(LOG_DIR / "app.log")  # 文件输出
    ]
)

# 创建专用日志器
logger = logging.getLogger("code-dependency-graph")
logger.setLevel(logging.INFO)

# 创建应用
app = FastAPI(
    title="Code Dependency Graph API",
    description="代码依赖图本地服务 - 支持多仓库、多层级依赖分析",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 数据库
DB_PATH = Path(__file__).parent.parent / "data" / "dependency.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
db = Database(str(DB_PATH))

# 多数据库管理器 - 每个仓库独立的数据库
db_manager = DatabaseManager(str(DB_PATH.parent))

# 解析器
parser = MultiLayerCodeParser(db)

# 解析进度跟踪器
_parse_progress: Dict[int, Dict] = {}


def get_repo_db_or_main(repo_id: int):
    """
    获取仓库数据库实例，如果不存在则返回主数据库
    用于查询时优先使用仓库独立的数据库
    """
    repo_db = db_manager._get_repo_db(repo_id)
    if repo_db:
        return repo_db
    return db


def get_symbols_from_repo(repo_id: int, repository_id: int = None):
    """
    从仓库数据库获取符号列表
    如果仓库有独立数据库则使用它，否则使用主数据库
    """
    repo_db = db_manager._get_repo_db(repo_id)
    if repo_db:
        with repo_db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM symbols ORDER BY id")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    else:
        # fallback to main db
        symbols, _ = db.search_symbols(repository_id=repo_id, page=1, page_size=10000)
        return symbols


# ========== 请求模型 ==========

class RepositoryCreate(BaseModel):
    name: str = Field(..., description="仓库名称")
    path: str = Field(..., description="仓库本地路径")
    layer: str = Field(..., description="层级: SDK, LOGIC, BUSINESS, UI")
    remote_url: str = Field(default="", description="远程仓库 URL")
    branch: str = Field(default="main", description="分支名")
    parent_repo_id: Optional[int] = Field(default=None, description="依赖的上游仓库 ID")
    parent_repo_branch: str = Field(default="main", description="上游仓库分支")
    sln_path: str = Field(default="", description="VS 解决方案文件路径（可选）")


class RepositoryUpdate(BaseModel):
    path: Optional[str] = None
    remote_url: Optional[str] = None
    branch: Optional[str] = None
    parent_repo_id: Optional[int] = None
    parent_repo_branch: Optional[str] = None
    sln_path: Optional[str] = None


class ParseRequest(BaseModel):
    repository_id: int = Field(..., description="要解析的仓库 ID")
    file_extensions: Optional[List[str]] = Field(
        default=['.cpp', '.h', '.hpp', '.cxx', '.cc'],
        description="要解析的文件扩展名"
    )


class SearchQuery(BaseModel):
    keyword: Optional[str] = Field(default=None, description="搜索关键词")
    layer: Optional[str] = Field(default=None, description="层级过滤")
    kind: Optional[str] = Field(default=None, description="符号类型过滤")
    repository_id: Optional[int] = Field(default=None, description="仓库 ID 过滤")
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=50, ge=1, le=100, description="每页数量")


# ========== 响应模型 ==========

class ApiResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None


class ParseResult(BaseModel):
    repository_id: int
    symbols_count: int
    dependencies_count: int
    layers: List[str]


# ========== 仓库管理接口 ==========

@app.get("/api/repositories", response_model=ApiResponse)
async def list_repositories(layer: Optional[str] = None):
    """列出所有已注册的仓库"""
    repos = db.list_repositories(layer)
    return ApiResponse(
        success=True,
        message="获取成功",
        data={
            "repositories": [
                {
                    "id": r.id,
                    "name": r.name,
                    "path": r.path,
                    "layer": r.layer,
                    "remote_url": r.remote_url,
                    "branch": r.branch,
                    "parent_repo_id": r.parent_repo_id,
                    "parent_repo_branch": r.parent_repo_branch,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None
                }
                for r in repos
            ]
        }
    )


@app.post("/api/repositories", response_model=ApiResponse)
async def create_repository(repo: RepositoryCreate):
    """注册新仓库"""
    logger.info(f"创建仓库: name={repo.name}, layer={repo.layer}, path={repo.path}")

    # 检查是否已存在
    existing = db.get_repository_by_name_branch(repo.name, repo.branch)
    if existing:
        logger.warning(f"仓库已存在: {repo.name}:{repo.branch}")
        raise HTTPException(status_code=400, detail=f"仓库 {repo.name}:{repo.branch} 已存在")

    repo_model = Repository(
        name=repo.name,
        path=repo.path,
        layer=repo.layer,
        remote_url=repo.remote_url,
        branch=repo.branch,
        parent_repo_id=repo.parent_repo_id,
        parent_repo_branch=repo.parent_repo_branch,
        sln_path=repo.sln_path
    )

    repo_id = db.create_repository(repo_model)
    logger.info(f"仓库创建成功: id={repo_id}, name={repo.name}")

    # 为仓库创建独立的数据库（存储在仓库目录下的 .codegraph/ 目录）
    try:
        repo_db = db_manager.create_repo_db(repo_id, repo.path)
        db_file = "codegraph.db"
        db_manager.register_repo(
            repo_id=repo_id,
            name=repo.name,
            path=repo.path,
            layer=repo.layer,
            db_file=db_file,
            remote_url=repo.remote_url,
            branch=repo.branch
        )
        logger.info(f"仓库数据库创建成功: repo_id={repo_id}, db_file={db_file}")
    except Exception as e:
        logger.error(f"创建仓库数据库失败: {e}")

    return ApiResponse(
        success=True,
        message=f"仓库 {repo.name} 创建成功",
        data={"repository_id": repo_id, "sln_path": repo.sln_path}
    )


@app.get("/api/repositories/git-info", response_model=ApiResponse)
async def get_git_info(path: str = Query(..., description="仓库本地路径")):
    """
    自动获取仓库的 Git 信息
    返回当前分支、远程 URL 等信息
    """
    import subprocess

    result = {
        "current_branch": "main",
        "remote_url": "",
        "all_branches": ["main"],
        "success": False,
        "message": ""
    }

    try:
        repo_path = Path(path)
        if not repo_path.exists():
            return ApiResponse(
                success=False,
                message=f"路径不存在: {path}",
                data=result
            )

        # 获取当前分支
        try:
            branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5
            )
            if branch_result.returncode == 0:
                result["current_branch"] = branch_result.stdout.strip()
        except Exception as e:
            logger.warning(f"获取当前分支失败: {e}")

        # 获取远程 URL
        try:
            remote_result = subprocess.run(
                ["git", "config", "--get", "remote.origin.url"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5
            )
            if remote_result.returncode == 0:
                result["remote_url"] = remote_result.stdout.strip()
        except Exception as e:
            logger.warning(f"获取远程 URL 失败: {e}")

        # 获取所有本地和远程分支
        try:
            branches_result = subprocess.run(
                ["git", "branch", "-a", "--format=%(refname:short)"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5
            )
            if branches_result.returncode == 0:
                branches = [b.strip() for b in branches_result.stdout.strip().split('\n') if b.strip()]
                result["all_branches"] = list(set(branches))  # 去重
        except Exception as e:
            logger.warning(f"获取分支列表失败: {e}")

        result["success"] = True
        result["message"] = "Git 信息获取成功"

    except Exception as e:
        logger.error(f"获取 Git 信息失败: {e}")
        result["message"] = str(e)

    return ApiResponse(
        success=result["success"],
        message=result["message"],
        data=result
    )


@app.get("/api/repositories/{repo_id}", response_model=ApiResponse)
async def get_repository(repo_id: int):
    """获取仓库详情"""
    repo = db.get_repository(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")

    # 获取统计信息
    symbol_count = db.count_symbols(repository_id=repo_id)
    symbols = db.list_symbols(repository_id=repo_id, limit=1000)

    return ApiResponse(
        success=True,
        message="获取成功",
        data={
            "repository": {
                "id": repo.id,
                "name": repo.name,
                "path": repo.path,
                "layer": repo.layer,
                "remote_url": repo.remote_url,
                "branch": repo.branch,
                "parent_repo_id": repo.parent_repo_id,
                "parent_repo_branch": repo.parent_repo_branch,
                "created_at": repo.created_at.isoformat() if repo.created_at else None,
                "updated_at": repo.updated_at.isoformat() if repo.updated_at else None
            },
            "statistics": {
                "symbols_count": symbol_count,
                "recent_symbols": [
                    {"name": s.name, "kind": s.kind, "file": s.file_path}
                    for s in symbols[:10]
                ]
            }
        }
    )


@app.put("/api/repositories/{repo_id}", response_model=ApiResponse)
async def update_repository(repo_id: int, update: RepositoryUpdate):
    """更新仓库信息"""
    repo = db.get_repository(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")

    updates = {k: v for k, v in update.model_dump().items() if v is not None}
    if updates:
        db.update_repository(repo_id, updates)

    return ApiResponse(success=True, message="更新成功")


@app.delete("/api/repositories/{repo_id}", response_model=ApiResponse)
async def delete_repository(repo_id: int):
    """删除仓库及其所有数据"""
    repo = db.get_repository(repo_id)
    if not repo:
        logger.warning(f"删除仓库失败: 仓库不存在, id={repo_id}")
        raise HTTPException(status_code=404, detail="仓库不存在")

    db.delete_repository(repo_id)

    # 删除仓库的独立数据库
    try:
        db_manager.delete_repo_db(repo_id)
        db_manager.unregister_repo(repo_id)
        logger.info(f"仓库数据库已删除: repo_id={repo_id}")
    except Exception as e:
        logger.error(f"删除仓库数据库失败: {e}")

    logger.info(f"仓库已删除: id={repo_id}, name={repo.name}")

    return ApiResponse(success=True, message=f"仓库 {repo.name} 已删除")


# ========== 解析进度接口 ==========

@app.get("/api/repositories/{repo_id}/parse-progress")
async def get_parse_progress(repo_id: int):
    """
    SSE 端点：流式推送解析进度
    """
    async def event_generator():
        last_progress = -1
        while True:
            progress = _parse_progress.get(repo_id, None)
            if progress:
                # 发送进度更新
                data = f"data: {progress.get('stage', '')}|{progress.get('percent', 0)}|{progress.get('message', '')}\n\n"
                yield data
                last_progress = progress.get('percent', 0)
                # 如果完成或出错，发送最终状态后关闭
                if progress.get('status') in ('completed', 'error', 'cancelled'):
                    break
            else:
                # 还没有进度信息，发送等待状态
                yield f"data: waiting|0|等待解析开始...\n\n"
            await asyncio.sleep(0.5)

    return event_generator()


@app.get("/api/repositories/{repo_id}/parse-status")
async def get_parse_status(repo_id: int):
    """获取当前解析状态（轮询用）"""
    progress = _parse_progress.get(repo_id)
    if not progress:
        return {"status": "idle", "percent": 0, "stage": "", "message": ""}
    return progress


# ========== 代码解析接口 ==========

async def _run_parse_task(
    repo_id: int,
    repo: Repository,
    file_extensions: List[str],
    skip_dirs: List[str]
):
    """后台解析任务 - 在后台线程中执行"""
    from threading import Thread
    import asyncio

    def do_sync_parse():
        def update_progress(stage: str, current: int, total: int, message: str):
            percent = int((current / max(total, 1)) * 100) if total > 0 else 0
            _parse_progress[repo_id] = {
                'status': stage,
                'stage': stage,
                'percent': percent,
                'current': current,
                'total': total,
                'message': message
            }

        try:
            repo_model = Repository(
                id=repo.id,
                name=repo.name,
                path=repo.path,
                layer=repo.layer,
                remote_url=repo.remote_url,
                branch=repo.branch,
                parent_repo_id=repo.parent_repo_id,
                parent_repo_branch=repo.parent_repo_branch
            )

            update_progress('scanning', 0, 1, '开始解析...')
            start_time = datetime.now()

            # 获取已解析文件的缓存（用于增量解析）
            repo_db = db_manager._get_repo_db(repo_id)
            parsed_files_cache = {}
            changed_files = []
            if repo_db:
                try:
                    parsed_files_cache = repo_db.get_parsed_files()
                except Exception as e:
                    logger.warning(f"获取已解析文件缓存失败: {e}")

            def on_file_parsed(file_path: str):
                """文件被解析后的回调"""
                changed_files.append(file_path)

            def on_file_skipped_callback(file_path: str):
                """文件被跳过时的回调"""
                pass  # 静默跳过

            symbols, dependencies, data_flows, error_paths, changed_files = parser.parse_repository(
                repo_model, file_extensions, skip_dirs=skip_dirs,
                progress_callback=update_progress,
                incremental=True,
                parsed_files_cache=parsed_files_cache,
                on_file_skipped=on_file_skipped_callback
            )
            elapsed = (datetime.now() - start_time).total_seconds()

            logger.info(f"仓库解析完成: id={repo_id}, 耗时={elapsed:.2f}s, 符号数={len(symbols)}, 依赖数={len(dependencies)}")

            update_progress('storing', 0, 1, '存储数据到数据库...')
            db.create_symbols_batch(symbols)

            hash_values = [s.hash_value for s in symbols]
            symbols_by_hash = db.get_symbols_by_hashes(hash_values, repo_id)
            symbol_id_map = {}
            for sym in symbols:
                found = symbols_by_hash.get(sym.hash_value)
                if found:
                    key = (sym.name, sym.file_path, sym.line_number)
                    symbol_id_map[key] = found.id

            symbols_by_name = {}
            for key, sid in symbol_id_map.items():
                sym_name, sym_file, sym_line = key
                if sym_name not in symbols_by_name:
                    symbols_by_name[sym_name] = []
                symbols_by_name[sym_name].append((sid, sym_file))

            include_deps = []
            calls_deps = []
            inheritance_deps = []
            composition_deps = []

            for dep in dependencies:
                if isinstance(dep, dict):
                    dep_type = dep.get('type', 'include')
                else:
                    dep_type = dep.dependency_type

                if dep_type == 'calls':
                    calls_deps.append(dep)
                elif dep_type == 'inheritance':
                    inheritance_deps.append(dep)
                elif dep_type == 'composition':
                    composition_deps.append(dep)
                else:
                    include_deps.append(dep)

            cross_repo_names = set()
            for dep in calls_deps + inheritance_deps + composition_deps:
                if isinstance(dep, dict):
                    tgt = dep.get('target', '')
                    if '::' in tgt:
                        tgt = tgt.split('::')[-1]
                    if tgt and tgt not in symbols_by_name:
                        cross_repo_names.add(tgt)

            if cross_repo_names:
                cross_repo_syms = db.get_symbols_by_names_across_repos(list(cross_repo_names), exclude_repo_id=repo_id)
                for sym in cross_repo_syms:
                    if sym.name not in symbols_by_name:
                        symbols_by_name[sym.name] = []
                    symbols_by_name[sym.name].append((sym.id, sym.file_path))

            dep_count = 0
            seen_deps = set()
            for dep in calls_deps:
                if isinstance(dep, dict):
                    src_func = dep.get('source')
                    tgt_func = dep.get('target')
                    src_func_file = dep.get('source_file', '')
                    src_line = dep.get('line', 0)
                else:
                    continue

                if src_func and tgt_func:
                    src_base = src_func.split('::')[-1] if '::' in src_func else src_func
                    tgt_base = tgt_func.split('::')[-1] if '::' in tgt_func else tgt_func

                    source_id = None
                    for sid, sfile in symbols_by_name.get(src_func, symbols_by_name.get(src_base, [])):
                        if not src_func_file or sfile == src_func_file:
                            source_id = sid
                            break

                    target_id = None
                    for sid, sfile in symbols_by_name.get(tgt_func, symbols_by_name.get(tgt_base, [])):
                        if sid != source_id:
                            target_id = sid
                            break

                    if source_id and target_id:
                        dep_key = (source_id, target_id, src_line)
                        if dep_key not in seen_deps:
                            seen_deps.add(dep_key)
                            db.create_dependency(Dependency(
                                source_symbol_id=source_id,
                                target_symbol_id=target_id,
                                dependency_type='calls',
                                source_file=src_func_file,
                                source_line=src_line,
                                target_file=tgt_func
                            ))
                            dep_count += 1

            # 处理 include 依赖
            for dep in include_deps:
                if isinstance(dep, dict):
                    src_file = dep.get('source', '')
                    src_line = dep.get('line', 0)
                    tgt_file = dep.get('target', '')
                else:
                    continue

                import hashlib
                target_basename = os.path.basename(tgt_file)
                target_name = target_basename.replace('.h', '').replace('.hpp', '').replace('.cpp', '')
                target_hash = hashlib.sha256(f"{target_name}:include:{tgt_file}".encode()).hexdigest()[:16]

                existing = db.get_symbol_by_hash(target_hash, repo_id)
                if not existing:
                    existing = Symbol(
                        repository_id=repo_id,
                        name=target_name,
                        kind='include',
                        file_path=tgt_file,
                        line_number=0,
                        namespace='',
                        return_type='',
                        parameters='[]',
                        signature=target_name,
                        hash_value=target_hash
                    )
                    db.create_symbol(existing)
                    existing = db.get_symbol_by_hash(target_hash, repo_id)

                source_id = None
                for key, sid in symbol_id_map.items():
                    if os.path.basename(key[0]) == os.path.basename(src_file):
                        source_id = sid
                        break
                if not source_id:
                    for s in symbols:
                        if s.file_path == src_file:
                            key = (s.name, s.file_path, s.line_number)
                            source_id = symbol_id_map.get(key)
                            if source_id:
                                break

                if source_id and existing:
                    dep_key = (source_id, existing.id, src_line)
                    if dep_key not in seen_deps:
                        seen_deps.add(dep_key)
                        db.create_dependency(Dependency(
                            source_symbol_id=source_id,
                            target_symbol_id=existing.id,
                            dependency_type='include',
                            source_file=src_file,
                            source_line=src_line,
                            target_file=tgt_file
                        ))
                        dep_count += 1

            # 存储到 per-repo 数据库
            repo_db = db_manager._get_repo_db(repo_id)
            if repo_db:
                try:
                    repo_db.insert_symbols_batch(symbols)
                    if symbols:
                        hashes = [s.hash_value for s in symbols]
                        repo_symbols_by_hash = repo_db.get_symbols_by_hashes(hashes)
                        repo_symbol_id_map = {}
                        for sym in symbols:
                            found = repo_symbols_by_hash.get(sym.hash_value)
                            if found:
                                key = (sym.name, sym.file_path, sym.line_number)
                                repo_symbol_id_map[key] = found['id']

                        for dep in dependencies:
                            if isinstance(dep, dict):
                                src_func = dep.get('source')
                                tgt_func = dep.get('target')
                                src_file = dep.get('source_file', '')
                                src_line = dep.get('line', 0)
                                dep_type = dep.get('type', 'include')
                                tgt_file = dep.get('target', '')
                            else:
                                continue

                            if src_func and tgt_func:
                                src_base = src_func.split('::')[-1] if '::' in src_func else src_func
                                tgt_base = tgt_func.split('::')[-1] if '::' in tgt_func else tgt_func

                                source_id = None
                                for key, sid in repo_symbol_id_map.items():
                                    if key[0] == src_func or key[0] == src_base:
                                        if key[1] == src_file or not src_file:
                                            source_id = sid
                                            break

                                target_id = None
                                for key, sid in repo_symbol_id_map.items():
                                    if key[0] == tgt_func or key[0] == tgt_base:
                                        target_id = sid
                                        break

                                if source_id and target_id:
                                    dep_key = (source_id, target_id, src_line)
                                    if dep_key not in seen_deps:
                                        seen_deps.add(dep_key)
                                        repo_db.insert_dependency(
                                            source_symbol_id=source_id,
                                            target_symbol_id=target_id,
                                            dependency_type=dep_type,
                                            source_file=src_file,
                                            source_line=src_line,
                                            target_file=tgt_file
                                        )
                    logger.info(f"per-repo数据库存储完成: repo_id={repo_id}")
                except Exception as e:
                    logger.error(f"per-repo数据库存储失败: {e}")

            # 更新已解析文件缓存（增量解析支持）
            if repo_db and changed_files:
                try:
                    # 计算当前仓库中所有文件的哈希
                    from pathlib import Path
                    repo_path = Path(repo.path)
                    all_current_files = set()
                    for root, dirs, files in os.walk(repo_path):
                        dirs[:] = [d for d in dirs if d.lower() not in ['build', 'bin', 'obj', '.git', '.svn', 'node_modules', 'third_party', 'dependencies', 'extern', '__pycache__', '.vs', 'debug', 'release', 'x64', 'arm64']]
                        for file in files:
                            if any(file.endswith(ext) for ext in file_extensions):
                                all_current_files.add(os.path.join(root, file))

                    # 更新本次解析的文件
                    for fp in changed_files:
                        file_hash = parser._get_file_hash(fp)
                        repo_db.update_parsed_file(fp, file_hash)

                    # 移除已删除文件的记录
                    cached_files = set(parsed_files_cache.keys())
                    deleted_files = cached_files - all_current_files
                    for deleted_fp in deleted_files:
                        repo_db.remove_parsed_file(deleted_fp)
                        removed_count = repo_db.remove_symbols_by_file(deleted_fp)
                        logger.info(f"移除已删除文件的符号: {deleted_fp}, 移除 {removed_count} 个符号")

                    logger.info(f"已解析文件缓存更新完成: repo_id={repo_id}, 本次解析 {len(changed_files)} 文件, 移除 {len(deleted_files)} 文件")
                except Exception as e:
                    logger.warning(f"更新已解析文件缓存失败: {e}")

            # 更新最终进度
            _parse_progress[repo_id] = {
                'status': 'completed',
                'stage': 'completed',
                'percent': 100,
                'current': len(symbols),
                'total': len(symbols),
                'message': f'解析完成: {len(symbols)} 符号, {dep_count} 依赖'
            }

            logger.info(f"仓库解析任务完成: repo_id={repo_id}")

        except Exception as e:
            logger.error(f"仓库解析失败: repo_id={repo_id}, error={e}")
            _parse_progress[repo_id] = {
                'status': 'error',
                'stage': 'error',
                'percent': 0,
                'current': 0,
                'total': 0,
                'message': f'解析失败: {str(e)}'
            }

    # 在新线程中执行同步解析任务
    thread = Thread(target=do_sync_parse)
    thread.start()
    thread.join()


@app.post("/api/repositories/{repo_id}/parse", response_model=ApiResponse)
async def parse_repository(
    repo_id: int,
    background_tasks: BackgroundTasks,
    file_extensions: Optional[List[str]] = Query(default=['.cpp', '.h', '.hpp', '.cxx', '.cc']),
    ignore_patterns: Optional[str] = Query(default=None)
):
    """解析仓库代码（异步，后台执行）"""
    repo = db.get_repository(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")

    # 解析忽略模式
    skip_dirs = None
    if ignore_patterns:
        skip_dirs = [p.strip() for p in ignore_patterns.split(',') if p.strip()]

    # 初始化进度状态
    _parse_progress[repo_id] = {
        'status': 'running',
        'stage': 'starting',
        'percent': 0,
        'current': 0,
        'total': 0,
        'message': '准备解析...'
    }

    # 添加后台任务
    background_tasks.add_task(_run_parse_task, repo_id, repo, file_extensions or ['.cpp', '.h', '.hpp', '.cxx', '.cc'], skip_dirs)

    return ApiResponse(
        success=True,
        message=f"解析任务已启动: {repo.name}",
        data={'repository_id': repo_id, 'status': 'started'}
    )

@app.post("/api/repositories/parse-all", response_model=ApiResponse)
async def parse_all_repositories():
    """
    按层级顺序解析所有仓库（SDK → LOGIC → BUSINESS → UI）
    确保底层先解析，上层可以正确建立跨仓库依赖
    """
    layer_order = ['SDK', 'LOGIC', 'BUSINESS', 'UI']
    repos = db.list_repositories()
    results = []

    for layer in layer_order:
        for repo in repos:
            if repo.layer == layer:
                repo_model = Repository(
                    id=repo.id, name=repo.name, path=repo.path,
                    layer=repo.layer, remote_url=repo.remote_url,
                    branch=repo.branch, parent_repo_id=repo.parent_repo_id,
                    parent_repo_branch=repo.parent_repo_branch, sln_path=repo.sln_path
                )
                try:
                    symbols, dependencies, data_flows_raw, error_paths_raw = parser.parse_repository(repo_model)
                    db.create_symbols_batch(symbols)
                    hash_values = [s.hash_value for s in symbols]
                    symbols_by_hash = db.get_symbols_by_hashes(hash_values, repo.id)
                    symbol_id_map = {}
                    for sym in symbols:
                        found = symbols_by_hash.get(sym.hash_value)
                        if found:
                            key = (sym.name, sym.file_path, sym.line_number)
                            symbol_id_map[key] = found.id

                    dep_count = 0
                    calls_deps = [d for d in dependencies if (isinstance(d, dict) and d.get('type') == 'calls') or (not isinstance(d, dict) and d.dependency_type == 'calls')]
                    include_deps = [d for d in dependencies if d not in calls_deps]

                    symbols_by_name_idx = {}
                    for key, sid in symbol_id_map.items():
                        n = key[0]
                        if n not in symbols_by_name_idx:
                            symbols_by_name_idx[n] = []
                        symbols_by_name_idx[n].append((sid, key[1]))

                    cross_names = set()
                    for dep in calls_deps:
                        if isinstance(dep, dict):
                            t = dep.get('target', '')
                            if '::' in t: t = t.split('::')[-1]
                            if t and t not in symbols_by_name_idx:
                                cross_names.add(t)
                    if cross_names:
                        for sym in db.get_symbols_by_names_across_repos(list(cross_names), exclude_repo_id=repo.id):
                            if sym.name not in symbols_by_name_idx:
                                symbols_by_name_idx[sym.name] = []
                            symbols_by_name_idx[sym.name].append((sym.id, sym.file_path))

                    seen_deps = set()
                    for dep in calls_deps:
                        if not isinstance(dep, dict): continue
                        src_func = dep.get('source', '')
                        tgt_func = dep.get('target', '')
                        src_file = dep.get('source_file', '')
                        src_line = dep.get('line', 0)
                        if not src_func or not tgt_func: continue

                        src_base = src_func.split('::')[-1] if '::' in src_func else src_func
                        tgt_base = tgt_func.split('::')[-1] if '::' in tgt_func else tgt_func

                        source_id = None
                        for sid, sf in symbols_by_name_idx.get(src_func, symbols_by_name_idx.get(src_base, [])):
                            if not src_file or sf == src_file:
                                source_id = sid; break

                        target_id = None
                        tgt_cands = symbols_by_name_idx.get(tgt_func, symbols_by_name_idx.get(tgt_base, []))
                        call_type = dep.get('call_type', '')
                        for sid, sf in tgt_cands:
                            if sf == src_file: target_id = sid; break
                        if target_id and source_id and target_id == source_id and call_type != 'recursive':
                            target_id = None
                        if not target_id:
                            for sid, sf in tgt_cands:
                                if sid != source_id or call_type == 'recursive':
                                    target_id = sid; break

                        if source_id and target_id:
                            dk = (source_id, target_id, src_line)
                            if dk not in seen_deps:
                                seen_deps.add(dk)
                                db.create_dependency(Dependency(
                                    source_symbol_id=source_id, target_symbol_id=target_id,
                                    dependency_type='calls', source_file=src_file,
                                    source_line=src_line, target_file=tgt_func,
                                    branch_type=dep.get('branch_type', ''),
                                    branch_condition=dep.get('branch_condition', '')
                                ))
                                dep_count += 1

                    for dep in include_deps:
                        if isinstance(dep, dict):
                            tgt_file = dep.get('target', '')
                            src_file = dep.get('source', '')
                            src_line = dep.get('line', 0)
                            import os, hashlib
                            tgt_basename = os.path.basename(tgt_file)
                            tgt_name = tgt_basename.replace('.h','').replace('.hpp','').replace('.cpp','')
                            tgt_hash = hashlib.sha256(f"{tgt_name}:include:{tgt_file}".encode()).hexdigest()[:16]
                            source_id = None
                            for key, sid in symbol_id_map.items():
                                if key[0] == os.path.basename(src_file).replace('.cpp','').replace('.h',''):
                                    source_id = sid; break
                            if not source_id:
                                for s in symbols:
                                    if s.file_path == src_file:
                                        key = (s.name, s.file_path, s.line_number)
                                        source_id = symbol_id_map.get(key)
                                        if source_id: break
                            existing = db.get_symbol_by_hash(tgt_hash, repo.id)
                            if not existing:
                                existing_sym = Symbol(
                                    repository_id=repo.id, name=tgt_name, kind='include',
                                    file_path=tgt_file, line_number=0, namespace='',
                                    return_type='', parameters='[]', signature=tgt_name,
                                    hash_value=tgt_hash
                                )
                                db.create_symbol(existing_sym)
                                existing = db.get_symbol_by_hash(tgt_hash, repo.id)
                            if source_id and existing:
                                dk = (source_id, existing.id, src_line)
                                if dk not in seen_deps:
                                    seen_deps.add(dk)
                                    db.create_dependency(Dependency(
                                        source_symbol_id=source_id, target_symbol_id=existing.id,
                                        dependency_type='include', source_file=src_file,
                                        source_line=src_line, target_file=tgt_file
                                    ))
                                    dep_count += 1

                    results.append({"repository": repo.name, "layer": repo.layer,
                                    "symbols": len(symbols), "dependencies": dep_count})
                    logger.info(f"批量解析 {repo.name} ({repo.layer}): {len(symbols)} 符号, {dep_count} 依赖")
                except Exception as e:
                    results.append({"repository": repo.name, "layer": repo.layer, "error": str(e)})
                    logger.error(f"批量解析 {repo.name} 失败: {e}")

    return ApiResponse(success=True, message=f"批量解析完成: {len(results)} 个仓库", data={"repositories": results})


@app.post("/api/repositories/{repo_id}/parse-vs", response_model=ApiResponse)
async def parse_vs_solution(
    repo_id: int,
    sln_path: Optional[str] = Query(default=None, description="指定 .sln 文件路径")
):
    """
    解析 VS 解决方案
    优先使用仓库配置中指定的 sln_path，否则使用请求参数
    """
    repo = db.get_repository(repo_id)
    if not repo:
        logger.warning(f"VS解析失败: 仓库不存在, id={repo_id}")
        raise HTTPException(status_code=404, detail="仓库不存在")

    # 优先级：请求参数 > 仓库配置 > 自动查找
    effective_sln_path = sln_path or repo.sln_path
    logger.info(f"开始VS解析: id={repo_id}, name={repo.name}, sln_path={effective_sln_path or 'auto'}")

    repo_model = Repository(
        id=repo.id,
        name=repo.name,
        path=repo.path,
        layer=repo.layer,
        remote_url=repo.remote_url,
        branch=repo.branch,
        parent_repo_id=repo.parent_repo_id,
        parent_repo_branch=repo.parent_repo_branch,
        sln_path=effective_sln_path
    )

    # 进度回调函数
    def update_vs_progress(stage: str, current: int, total: int, message: str):
        percent = int((current / max(total, 1)) * 100) if total > 0 else 0
        _parse_progress[repo_id] = {
            'status': stage,
            'stage': stage,
            'percent': percent,
            'current': current,
            'total': total,
            'message': message
        }

    # 更新进度：开始解析
    update_vs_progress('scanning', 0, 1, '开始VS解析...')

    start_time = datetime.now()
    # 使用 VS 解决方案解析器
    symbols, dependencies, data_flows, error_paths = parser.parse_vs_solution(repo_model, effective_sln_path)
    elapsed = (datetime.now() - start_time).total_seconds()

    # 更新进度：存储数据
    update_vs_progress('storing', 0, 1, '存储数据到数据库...')

    logger.info(f"VS解析完成: id={repo_id}, 耗时={elapsed:.2f}s, 符号数={len(symbols)}, 依赖数={len(dependencies)}, 数据流={len(data_flows)}, 错误路径={len(error_paths)}")

    # 存储到数据库
    db.create_symbols_batch(symbols)

    # 批量更新符号 ID（优化版）
    hash_values = [s.hash_value for s in symbols]
    symbols_by_hash = db.get_symbols_by_hashes(hash_values, repo_id)
    symbol_id_map = {}
    for sym in symbols:
        found = symbols_by_hash.get(sym.hash_value)
        if found:
            key = (sym.name, sym.file_path, sym.line_number)
            symbol_id_map[key] = found.id

    dep_count = 0
    calls_deps = []
    include_deps = []

    for dep in dependencies:
        if isinstance(dep, dict):
            dep_type = dep.get('type', 'include')
        else:
            dep_type = dep.dependency_type

        if dep_type == 'calls':
            calls_deps.append(dep)
        else:
            include_deps.append(dep)

    # 预建名称索引
    vs_symbols_by_name = {}
    for key, sid in symbol_id_map.items():
        sym_name, sym_file, sym_line = key
        if sym_name not in vs_symbols_by_name:
            vs_symbols_by_name[sym_name] = []
        vs_symbols_by_name[sym_name].append((sid, sym_file))

    # 跨仓库补充
    cross_repo_names = set()
    for dep in calls_deps:
        if isinstance(dep, dict):
            tgt = dep.get('target', '')
            if '::' in tgt:
                tgt = tgt.split('::')[-1]
            if tgt and tgt not in vs_symbols_by_name:
                cross_repo_names.add(tgt)

    if cross_repo_names:
        cross_repo_syms = db.get_symbols_by_names_across_repos(
            list(cross_repo_names), exclude_repo_id=repo_id
        )
        for sym in cross_repo_syms:
            if sym.name not in vs_symbols_by_name:
                vs_symbols_by_name[sym.name] = []
            vs_symbols_by_name[sym.name].append((sym.id, sym.file_path))
        logger.info(f"VS解析跨仓库补充 {len(cross_repo_syms)} 个符号到名称索引")

    # 处理函数调用依赖（使用索引）
    seen_deps = set()
    for dep in calls_deps:
        if isinstance(dep, dict):
            src_func = dep.get('source')
            tgt_func = dep.get('target')
            src_func_file = dep.get('source_file', '')
            src_line = dep.get('line', 0)
        else:
            src_func = None
            tgt_func = None
            src_func_file = ''
            src_line = 0

        if src_func and tgt_func:
            source_id = None
            target_id = None

            def get_base_name(name):
                if '::' in name:
                    return name.split('::')[-1]
                return name

            src_base = get_base_name(src_func)
            tgt_base = get_base_name(tgt_func)

            src_candidates = vs_symbols_by_name.get(src_func, [])
            if not src_candidates:
                src_candidates = vs_symbols_by_name.get(src_base, [])

            for sid, sfile in src_candidates:
                if not src_func_file or sfile == src_func_file:
                    source_id = sid
                    break

            tgt_candidates = vs_symbols_by_name.get(tgt_func, [])
            if not tgt_candidates:
                tgt_candidates = vs_symbols_by_name.get(tgt_base, [])

            call_type = dep.get('call_type', '') if isinstance(dep, dict) else ''

            for sid, sfile in tgt_candidates:
                if sfile == src_func_file:
                    target_id = sid
                    break
            if target_id and source_id and target_id == source_id and call_type != 'recursive':
                target_id = None
            if not target_id:
                for sid, sfile in tgt_candidates:
                    if sid != source_id or call_type == 'recursive':
                        target_id = sid
                        break

            if source_id and target_id:
                dep_key = (source_id, target_id, src_line)
                if dep_key in seen_deps:
                    continue
                seen_deps.add(dep_key)
                dep_obj = Dependency(
                    source_symbol_id=source_id,
                    target_symbol_id=target_id,
                    dependency_type='calls',
                    source_file=src_func_file,
                    source_line=src_line,
                    target_file=tgt_func,
                    branch_type=dep.get('branch_type', '') if isinstance(dep, dict) else '',
                    branch_condition=dep.get('branch_condition', '') if isinstance(dep, dict) else '',
                    error_context=dep.get('error_context', '') if isinstance(dep, dict) else ''
                )
                db.create_dependency(dep_obj)
                dep_count += 1

    # 处理 include 依赖
    seen_deps = set()
    for dep in include_deps:
        if isinstance(dep, dict):
            src_file = dep.get('source', '')
            src_line = dep.get('line', 0)
            tgt_file = dep.get('target', '')
            dep_type = dep.get('type', 'include')
        else:
            src_file = dep.source_file
            src_line = dep.source_line
            tgt_file = dep.target_file
            dep_type = dep.dependency_type

        source_id = symbol_id_map.get((src_file, src_line))
        target_id = symbol_id_map.get((tgt_file, 0))
        if source_id and target_id:
            dep_key = (source_id, target_id, src_line)
            if dep_key in seen_deps:
                continue
            seen_deps.add(dep_key)
            dep_obj = Dependency(
                source_symbol_id=source_id,
                target_symbol_id=target_id,
                dependency_type=dep_type,
                source_file=src_file,
                source_line=src_line,
                target_file=tgt_file
            )
            db.create_dependency(dep_obj)
            dep_count += 1

    logger.info(f"VS数据入库完成: id={repo_id}, 符号={len(symbols)}, 依赖={dep_count}")

    # 存储数据流
    if data_flows:
        from models import DataFlow
        flow_count = 0
        for flow in data_flows:
            if not isinstance(flow, dict):
                continue
            src_name = flow.get('source_symbol', '')
            tgt_name = flow.get('target_symbol', '')
            src_base = src_name.split('::')[-1] if '::' in src_name else src_name
            source_id = None
            for sid, sfile in vs_symbols_by_name.get(src_name, []) or vs_symbols_by_name.get(src_base, []):
                source_id = sid
                break
            target_id = None
            if tgt_name and flow.get('flow_type') != 'log_output':
                tgt_base = tgt_name.split('::')[-1] if '::' in tgt_name else tgt_name
                for sid, sfile in vs_symbols_by_name.get(tgt_name, []) or vs_symbols_by_name.get(tgt_base, []):
                    target_id = sid
                    break
            if source_id:
                detail = {}
                if flow.get('log_level'):
                    detail['log_level'] = flow['log_level']
                import json as json_mod
                df = DataFlow(
                    source_symbol_id=source_id,
                    target_symbol_id=target_id,
                    flow_type=flow.get('flow_type', ''),
                    source_param=flow.get('source_param', ''),
                    target_param=flow.get('target_param', ''),
                    detail=json_mod.dumps(detail) if detail else '',
                    file_path=flow.get('file_path', ''),
                    line_number=flow.get('source_line', 0)
                )
                db.create_data_flow(df)
                flow_count += 1
        logger.info(f"VS数据流存储完成: {flow_count} 条")

    # 存储错误处理路径
    ep_count = 0
    if error_paths:
        for ep in error_paths:
            func_name = ep.get('function', '')
            if func_name:
                base = func_name.split('::')[-1] if '::' in func_name else func_name
                for key, sid in symbol_id_map.items():
                    if key[0] == base:
                        ep['symbol_id'] = sid
                        break
            ep['repository_id'] = repo_id
            db.create_error_path(ep)
            ep_count += 1
        logger.info(f"VS错误路径存储完成: {ep_count} 条")

    # 同时存储到仓库独立的数据库
    repo_db = db_manager._get_repo_db(repo_id)
    if repo_db:
        try:
            repo_symbol_count = repo_db.insert_symbols_batch(symbols)
            logger.info(f"VS per-repo数据库存储: {repo_symbol_count} 个符号")

            if symbols:
                hashes = [s.hash_value for s in symbols]
                repo_symbols_by_hash = repo_db.get_symbols_by_hashes(hashes)
                repo_symbol_id_map = {}
                for sym in symbols:
                    found = repo_symbols_by_hash.get(sym.hash_value)
                    if found:
                        key = (sym.name, sym.file_path, sym.line_number)
                        repo_symbol_id_map[key] = found['id']

                seen_deps = set()
                for dep in dependencies:
                    if isinstance(dep, dict):
                        src_func = dep.get('source')
                        tgt_func = dep.get('target')
                        src_file = dep.get('source_file', '')
                        src_line = dep.get('line', 0)
                        dep_type = dep.get('type', 'include')
                        tgt_file = dep.get('target', '')
                    else:
                        continue

                    if src_func and tgt_func:
                        src_base = src_func.split('::')[-1] if '::' in src_func else src_func
                        tgt_base = tgt_func.split('::')[-1] if '::' in tgt_func else tgt_func

                        source_id = None
                        for key, sid in repo_symbol_id_map.items():
                            if key[0] == src_func or key[0] == src_base:
                                if key[1] == src_file or not src_file:
                                    source_id = sid
                                    break

                        target_id = None
                        for key, sid in repo_symbol_id_map.items():
                            if key[0] == tgt_func or key[0] == tgt_base:
                                target_id = sid
                                break

                        if source_id and target_id:
                            dep_key = (source_id, target_id, src_line)
                            if dep_key not in seen_deps:
                                seen_deps.add(dep_key)
                                repo_db.insert_dependency(
                                    source_symbol_id=source_id,
                                    target_symbol_id=target_id,
                                    dependency_type=dep_type,
                                    source_file=src_file,
                                    source_line=src_line,
                                    target_file=tgt_file
                                )

            logger.info(f"VS per-repo数据库存储完成: repo_id={repo_id}")
        except Exception as e:
            logger.error(f"VS per-repo数据库存储失败: {e}")

    # 解析完成，更新进度
    _parse_progress[repo_id] = {
        'status': 'completed',
        'stage': 'completed',
        'percent': 100,
        'current': len(symbols),
        'total': len(symbols),
        'message': f'VS解析完成: {len(symbols)} 符号, {dep_count} 依赖'
    }

    return ApiResponse(
        success=True,
        message=f"VS 解析完成：{len(symbols)} 个符号，{dep_count} 条依赖关系",
        data={
            "symbols_count": len(symbols),
            "dependencies_count": dep_count,
            "data_flows_count": len(data_flows),
            "error_paths_count": ep_count,
            "parsing_mode": "vs_solution",
            "sln_path_used": effective_sln_path or "auto_detect",
            "elapsed_seconds": elapsed
        }
    )


# ========== 图数据接口 ==========

@app.get("/api/graph", response_model=ApiResponse)
async def get_graph_data(
    repository_id: Optional[int] = None,
    layer: Optional[str] = None,
    max_nodes: int = Query(default=500, ge=100, le=2000)
):
    """获取图数据"""
    # 优先使用仓库独立的数据库进行查询
    if repository_id:
        repo_db = db_manager._get_repo_db(repository_id)
        if repo_db:
            with repo_db._get_connection() as conn:
                cursor = conn.cursor()

                # 获取符号（作为节点）
                cursor.execute("SELECT * FROM symbols ORDER BY id LIMIT ?", (max_nodes,))
                symbols = [dict(row) for row in cursor.fetchall()]

                nodes = []
                symbol_id_map = {}
                for sym in symbols:
                    node_id = f"sym_{sym['id']}"
                    nodes.append({
                        "id": node_id,
                        "symbol_id": sym['id'],
                        "name": sym['name'],
                        "kind": sym['kind'],
                        "file_path": sym['file_path']
                    })
                    symbol_id_map[sym['id']] = node_id

                # 获取依赖关系（作为边）
                cursor.execute("SELECT * FROM dependencies LIMIT ?", (max_nodes * 2,))
                deps = cursor.fetchall()

                edges = []
                for dep in deps:
                    source_node = symbol_id_map.get(dep['source_symbol_id'])
                    target_node = symbol_id_map.get(dep['target_symbol_id'])
                    if source_node and target_node:
                        edges.append({
                            "id": f"edge_{dep['id']}",
                            "source": source_node,
                            "target": target_node,
                            "type": dep['dependency_type']
                        })

                graph_data = {
                    "nodes": nodes,
                    "edges": edges,
                    "total_nodes": len(nodes),
                    "total_edges": len(edges)
                }

                return ApiResponse(
                    success=True,
                    message="获取成功",
                    data=graph_data
                )

    # Fallback to main database
    graph_data = db.get_graph_data(repository_id, layer, max_nodes)

    return ApiResponse(
        success=True,
        message="获取成功",
        data=graph_data
    )


@app.get("/api/graph/layers", response_model=ApiResponse)
async def get_layer_dependencies():
    """获取层级间的依赖关系"""
    layers = db.get_layer_dependencies()

    return ApiResponse(
        success=True,
        message="获取成功",
        data={"layer_dependencies": layers}
    )


# ========== 符号搜索接口 ==========

@app.get("/api/symbols", response_model=ApiResponse)
async def search_symbols(
    keyword: Optional[str] = None,
    layer: Optional[str] = None,
    kind: Optional[str] = None,
    repository_id: Optional[int] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100)
):
    """搜索符号"""
    # 优先使用仓库独立的数据库进行查询
    if repository_id:
        repo_db = db_manager._get_repo_db(repository_id)
        if repo_db:
            with repo_db._get_connection() as conn:
                cursor = conn.cursor()
                # 构建查询
                conditions = []
                params = []
                if keyword:
                    conditions.append("(name LIKE ? OR signature LIKE ?)")
                    params.extend([f"%{keyword}%", f"%{keyword}%"])
                if kind:
                    conditions.append("kind = ?")
                    params.append(kind)

                where_clause = " AND ".join(conditions) if conditions else "1=1"
                offset = (page - 1) * page_size

                # 查询总数
                cursor.execute(f"SELECT COUNT(*) as cnt FROM symbols WHERE {where_clause}", params)
                total = cursor.fetchone()['cnt']

                # 查询符号
                cursor.execute(
                    f"""SELECT * FROM symbols WHERE {where_clause}
                        ORDER BY id LIMIT ? OFFSET ?""",
                    params + [page_size, offset]
                )
                rows = cursor.fetchall()

                symbols = [dict(row) for row in rows]
                return ApiResponse(
                    success=True,
                    message="搜索成功",
                    data={
                        "total": total,
                        "page": page,
                        "page_size": page_size,
                        "symbols": [
                            {
                                "id": s['id'],
                                "name": s['name'],
                                "kind": s['kind'],
                                "file_path": s['file_path'],
                                "line_number": s['line_number'],
                                "namespace": s['namespace'],
                                "return_type": s['return_type'],
                                "signature": s['signature'],
                                "hash_value": s['hash_value']
                            }
                            for s in symbols
                        ],
                        "repository_id": repository_id,
                        "source": "per_repo_db"
                    }
                )

    # Fallback to main database
    symbols, total = db.search_symbols(
        keyword=keyword,
        layer=layer,
        kind=kind,
        repository_id=repository_id,
        page=page,
        page_size=page_size
    )

    return ApiResponse(
        success=True,
        message="搜索成功",
        data={
            "total": total,
            "page": page,
            "page_size": page_size,
            "symbols": [
                {
                    "id": s.id,
                    "name": s.name,
                    "kind": s.kind,
                    "file_path": s.file_path,
                    "line_number": s.line_number,
                    "namespace": s.namespace,
                    "return_type": s.return_type,
                    "signature": s.signature,
                    "hash_value": s.hash_value
                }
                for s in symbols
            ]
        }
    )


@app.get("/api/symbols/{symbol_id}", response_model=ApiResponse)
async def get_symbol_detail(symbol_id: int):
    """获取符号详情"""
    symbol = db.get_symbol(symbol_id)
    if not symbol:
        raise HTTPException(status_code=404, detail="符号不存在")

    # 获取依赖关系
    incoming = db.get_dependencies_by_symbol(symbol_id, "incoming")
    outgoing = db.get_dependencies_by_symbol(symbol_id, "outgoing")

    return ApiResponse(
        success=True,
        message="获取成功",
        data={
            "symbol": {
                "id": symbol.id,
                "name": symbol.name,
                "kind": symbol.kind,
                "file_path": symbol.file_path,
                "line_number": symbol.line_number,
                "namespace": symbol.namespace,
                "return_type": symbol.return_type,
                "parameters": symbol.parameters,
                "signature": symbol.signature,
                "hash_value": symbol.hash_value
            },
            "dependencies": {
                "incoming": incoming,
                "outgoing": outgoing
            }
        }
    )


@app.get("/api/symbols/{symbol_id}/source", response_model=ApiResponse)
async def get_symbol_source(
    symbol_id: int,
    context_lines: int = Query(default=5, ge=0, le=20, description="前后显示的行数")
):
    """获取符号所在位置的源代码片段"""
    symbol = db.get_symbol(symbol_id)
    if not symbol:
        raise HTTPException(status_code=404, detail="符号不存在")

    file_path = symbol.file_path
    line_number = symbol.line_number

    # 处理绝对路径
    src_root = Path(__file__).parent.parent
    if not Path(file_path).is_absolute():
        full_path = src_root / file_path
    else:
        full_path = Path(file_path)

    if not full_path.exists():
        return ApiResponse(
            success=False,
            message=f"源文件不存在: {file_path}",
            data=None
        )

    try:
        with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        total_lines = len(lines)
        start_line = max(0, line_number - context_lines - 1)
        end_line = min(total_lines, line_number + context_lines)

        snippet_lines = []
        for i in range(start_line, end_line):
            line_num = i + 1
            is_target = line_num == line_number
            snippet_lines.append({
                "line_number": line_num,
                "content": lines[i].rstrip('\n\r'),
                "is_target": is_target
            })

        return ApiResponse(
            success=True,
            message="获取成功",
            data={
                "file_path": str(full_path),
                "relative_path": file_path,
                "target_line": line_number,
                "total_lines": total_lines,
                "snippet": snippet_lines
            }
        )
    except Exception as e:
        return ApiResponse(
            success=False,
            message=f"读取文件失败: {str(e)}",
            data=None
        )


@app.get("/api/symbols/{symbol_id}/members", response_model=ApiResponse)
async def get_symbol_members(symbol_id: int):
    """获取class/struct的所有成员符号"""
    symbol = db.get_symbol(symbol_id)
    if not symbol:
        raise HTTPException(status_code=404, detail="符号不存在")

    if symbol.kind not in ('class', 'struct'):
        raise HTTPException(status_code=400, detail="只有class和struct类型有成员")

    members = db.get_class_members(symbol_id)

    return ApiResponse(
        success=True,
        message="获取成功",
        data={
            "class": {
                "id": symbol.id,
                "name": symbol.name,
                "kind": symbol.kind,
                "file_path": symbol.file_path,
                "line_number": symbol.line_number
            },
            "members": [
                {
                    "id": m.id,
                    "name": m.name,
                    "kind": m.kind,
                    "signature": m.signature,
                    "file_path": m.file_path,
                    "line_number": m.line_number
                }
                for m in members
            ],
            "total": len(members)
        }
    )


# ========== 符号级图数据接口 ==========

@app.get("/api/graph/symbol/{symbol_id}", response_model=ApiResponse)
async def get_symbol_graph(
    symbol_id: int,
    depth: int = Query(default=1, ge=1, le=3)
):
    """获取特定符号的依赖图（用于选中符号后展示）"""
    symbol = db.get_symbol(symbol_id)
    if not symbol:
        raise HTTPException(status_code=404, detail="符号不存在")

    # 获取该符号的直接依赖和被依赖关系
    outgoing = db.get_dependencies_by_symbol(symbol_id, "outgoing")
    incoming = db.get_dependencies_by_symbol(symbol_id, "incoming")

    # 构建节点和边
    nodes = []
    edges = []

    # 中心节点
    nodes.append({
        "id": f"center_{symbol.id}",
        "symbol_id": symbol.id,
        "name": symbol.name,
        "kind": symbol.kind,
        "layer": symbol.repository_id,
        "file_path": symbol.file_path,
        "isCenter": True
    })

    # 深度探索（递归获取依赖的依赖）
    def explore_symbols(symbol_ids, current_depth, visited):
        if current_depth >= depth:
            return

        for sym_id in symbol_ids:
            if sym_id in visited:
                continue
            visited.add(sym_id)

            sym = db.get_symbol(sym_id)
            if not sym:
                continue

            # 添加节点
            node_key = f"sym_{sym_id}"
            if not any(n.get("symbol_id") == sym_id for n in nodes):
                nodes.append({
                    "id": node_key,
                    "symbol_id": sym.id,
                    "name": sym.name,
                    "kind": sym.kind,
                    "layer": sym.repository_id,
                    "file_path": sym.file_path,
                    "depth": current_depth + 1
                })

            # 递归探索
            deps = db.get_dependencies_by_symbol(sym_id, "outgoing")
            next_ids = []
            for dep in deps:
                # 添加边
                edge_id = f"edge_{sym_id}_{dep.target_symbol_id}"
                if not any(e.get("id") == edge_id for e in edges):
                    edges.append({
                        "id": edge_id,
                        "source": node_key,
                        "target": f"sym_{dep.target_symbol_id}",
                        "type": dep.dependency_type
                    })
                next_ids.append(dep.target_symbol_id)

            if next_ids:
                explore_symbols(next_ids, current_depth + 1, visited)

    # 探索依赖和被依赖
    visited = set()
    out_ids = [d.target_symbol_id for d in outgoing]
    in_ids = [d.source_symbol_id for d in incoming]

    for sid in out_ids:
        sym = db.get_symbol(sid)
        if sym and not any(n.get("symbol_id") == sid for n in nodes):
            nodes.append({
                "id": f"sym_{sid}",
                "symbol_id": sid,
                "name": sym.name,
                "kind": sym.kind,
                "layer": sym.repository_id,
                "file_path": sym.file_path,
                "depth": 1
            })
        edges.append({
            "id": f"edge_{symbol_id}_{sid}",
            "source": f"center_{symbol_id}",
            "target": f"sym_{sid}",
            "type": "depends_on"
        })

    for sid in in_ids:
        sym = db.get_symbol(sid)
        if sym and not any(n.get("symbol_id") == sid for n in nodes):
            nodes.append({
                "id": f"sym_{sid}",
                "symbol_id": sid,
                "name": sym.name,
                "kind": sym.kind,
                "layer": sym.repository_id,
                "file_path": sym.file_path,
                "depth": 1
            })
        edges.append({
            "id": f"edge_{sid}_{symbol_id}",
            "source": f"sym_{sid}",
            "target": f"center_{symbol_id}",
            "type": "used_by"
        })

    return ApiResponse(
        success=True,
        message="获取成功",
        data={
            "center_symbol": {
                "id": symbol.id,
                "name": symbol.name,
                "kind": symbol.kind,
                "namespace": symbol.namespace,
                "signature": symbol.signature,
                "file_path": symbol.file_path,
                "line_number": symbol.line_number
            },
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "incoming_count": len(incoming),
                "outgoing_count": len(outgoing)
            }
        }
    )


# ========== LLM 查询接口 ==========

@app.get("/api/llm/query", response_model=ApiResponse)
async def llm_query(
    keyword: Optional[str] = Query(default=None, description="搜索关键词"),
    kind: Optional[str] = Query(default=None, description="符号类型: class, function, method, variable"),
    layer: Optional[str] = Query(default=None, description="层级: SDK, LOGIC, BUSINESS, UI"),
    repository_id: Optional[int] = Query(default=None, description="仓库 ID"),
    max_depth: int = Query(default=2, ge=1, le=3, description="依赖图深度")
):
    """
    LLM 友好查询接口 - 返回结构化数据便于 LLM 处理
    """
    results = {
        "query_params": {
            "keyword": keyword,
            "kind": kind,
            "layer": layer,
            "repository_id": repository_id,
            "max_depth": max_depth
        },
        "symbols": [],
        "symbol_details": [],
        "dependency_graphs": []
    }

    # 搜索符号
    symbols, total = db.search_symbols(
        keyword=keyword,
        layer=layer,
        kind=kind,
        repository_id=repository_id,
        page=1,
        page_size=10
    )

    # 构建简洁的符号列表
    for sym in symbols:
        results["symbols"].append({
            "id": sym.id,
            "name": sym.name,
            "kind": sym.kind,
            "signature": sym.signature or "",
            "file": sym.file_path,
            "namespace": sym.namespace or ""
        })

        # 获取详细信息
        incoming = db.get_dependencies_by_symbol(sym.id, "incoming")
        outgoing = db.get_dependencies_by_symbol(sym.id, "outgoing")

        # 获取依赖详情
        in_symbols = []
        for dep in incoming[:5]:  # 限制数量
            src_id = dep.get('source_symbol_id')
            if src_id:
                src = db.get_symbol(src_id)
                if src:
                    in_symbols.append({
                        "name": src.name,
                        "kind": src.kind,
                        "file": src.file_path
                    })

        out_symbols = []
        for dep in outgoing[:5]:
            tgt_id = dep.get('target_symbol_id')
            if tgt_id:
                tgt = db.get_symbol(tgt_id)
                if tgt:
                    out_symbols.append({
                        "name": tgt.name,
                        "kind": tgt.kind,
                        "file": tgt.file_path
                    })

        results["symbol_details"].append({
            "id": sym.id,
            "name": sym.name,
            "kind": sym.kind,
            "namespace": sym.namespace or "",
            "signature": sym.signature or "",
            "return_type": sym.return_type or "",
            "parameters": sym.parameters or "",
            "location": {
                "file": sym.file_path,
                "line": sym.line_number
            },
            "dependencies": {
                "incoming": in_symbols,
                "outgoing": out_symbols
            }
        })

        # 为前3个符号生成依赖图
        if len(results["dependency_graphs"]) < 3:
            graph = db.get_graph_data(
                repository_id=None,
                layer=None,
                max_nodes=100
            )
            # 筛选包含该符号的子图
            relevant_nodes = [n for n in graph.get("nodes", [])
                            if n.get("symbol_id") == sym.id]
            relevant_edges = [e for e in graph.get("edges", [])
                            if e.get("source", "").startswith(f"sym_{sym.id}")
                            or e.get("target", "").startswith(f"sym_{sym.id}")]

            if relevant_nodes or relevant_edges:
                results["dependency_graphs"].append({
                    "symbol_id": sym.id,
                    "symbol_name": sym.name,
                    "nodes": relevant_nodes[:50],
                    "edges": relevant_edges[:100]
                })

    results["total_symbols"] = total
    results["returned_symbols"] = len(symbols)

    return ApiResponse(
        success=True,
        message=f"找到 {total} 个符号，返回 {len(symbols)} 个",
        data=results
    )


@app.post("/api/llm/query/analysis", response_model=ApiResponse)
async def llm_analysis(symbol_id: int):
    """
    LLM 分析接口 - 分析单个符号的依赖关系和影响范围
    """
    symbol = db.get_symbol(symbol_id)
    if not symbol:
        raise HTTPException(status_code=404, detail="符号不存在")

    # 收集所有依赖信息
    analysis = {
        "target": {
            "id": symbol.id,
            "name": symbol.name,
            "kind": symbol.kind,
            "signature": symbol.signature or "",
            "file": symbol.file_path,
            "line": symbol.line_number,
            "namespace": symbol.namespace or ""
        },
        "impact_analysis": {
            "directly_affected_by": [],  # 直接影响该符号的符号
            "directly_affects": [],      # 该符号直接影响的符号
            "transitively_affected_by": [],  # 间接影响
            "transitively_affects": []   # 间接影响
        },
        "risk_indicators": {
            "cyclic_dependency": False,
            "cross_layer_dependency": False,
            "high_fan_out": False
        }
    }

    # 获取直接依赖
    outgoing = db.get_dependencies_by_symbol(symbol_id, "outgoing")
    incoming = db.get_dependencies_by_symbol(symbol_id, "incoming")

    for dep in outgoing:
        tgt = db.get_symbol(dep.target_symbol_id)
        if tgt:
            analysis["impact_analysis"]["directly_affects"].append({
                "id": tgt.id,
                "name": tgt.name,
                "kind": tgt.kind,
                "file": tgt.file_path,
                "type": dep.dependency_type
            })

    for dep in incoming:
        src = db.get_symbol(dep.source_symbol_id)
        if src:
            analysis["impact_analysis"]["directly_affected_by"].append({
                "id": src.id,
                "name": src.name,
                "kind": src.kind,
                "file": src.file_path,
                "type": dep.dependency_type
            })

    # 计算扇出
    if len(outgoing) > 20:
        analysis["risk_indicators"]["high_fan_out"] = True

    # 检测循环依赖
    def has_cycle(sym_id, visited, path):
        if sym_id in path:
            return True
        if sym_id in visited:
            return False
        visited.add(sym_id)
        path.add(sym_id)

        deps = db.get_dependencies_by_symbol(sym_id, "outgoing")
        for dep in deps:
            if has_cycle(dep.target_symbol_id, visited, path):
                return True
        path.remove(sym_id)
        return False

    if has_cycle(symbol_id, set(), set()):
        analysis["risk_indicators"]["cyclic_dependency"] = True

    return ApiResponse(
        success=True,
        message="分析完成",
        data=analysis
    )


@app.get("/api/symbols/{symbol_id}/call-table", response_model=ApiResponse)
async def get_call_table(
    symbol_id: int,
    direction: str = Query(default="outgoing", description="调用方向: outgoing(调用谁) / incoming(被谁调用)"),
    max_depth: int = Query(default=3, ge=1, le=30, description="最大深度")
):
    """
    获取符号的调用关系（制表符表格格式）
    返回示例:
    +----+----------+--------+----------+---------+
    | ID | Name     | Kind   | Line     | Type    |
    +====+==========+========+==========+=========+
    | 1  | func_a   | func   | 100      | include |
    | 2  | func_b   | func   | 50       | include |
    +----+----------+--------+----------+---------+
    """
    symbol = db.get_symbol(symbol_id)
    if not symbol:
        raise HTTPException(status_code=404, detail="符号不存在")

    # 构建调用树
    visited = set()
    tree_children = _build_call_tree(symbol_id, direction, max_depth, 1, visited)

    # 展平为表格数据
    table_rows = []
    def flatten_tree(children, path_prefix=""):
        for child in children:
            sym = child['symbol']
            table_rows.append([
                sym['id'],
                path_prefix + sym['name'],
                sym['kind'],
                sym['line'],
                sym.get('dep_type', ''),
                sym.get('dep_file', '').split('/')[-1] if sym.get('dep_file') else ''
            ])
            flatten_tree(child.get('children', []), path_prefix + "  ")

    flatten_tree(tree_children)

    # 生成表格
    headers = ["ID", "Name", "Kind", "Line", "Type", "From"]
    table_text = _format_table_text(headers, table_rows)

    # 统计
    total_count = len(table_rows)
    kind_counts = {}
    for row in table_rows:
        kind = row[2]
        kind_counts[kind] = kind_counts.get(kind, 0) + 1

    return ApiResponse(
        success=True,
        message="获取成功",
        data={
            "symbol": {
                "id": symbol.id,
                "name": symbol.name,
                "kind": symbol.kind,
                "file": symbol.file_path,
                "line": symbol.line_number
            },
            "direction": direction,
            "max_depth": max_depth,
            "table_headers": headers,
            "table_rows": table_rows,
            "table_text": table_text,
            "statistics": {
                "total": total_count,
                "by_kind": kind_counts
            }
        }
    )


@app.get("/api/symbols/{symbol_id}/call-tree", response_model=ApiResponse)
async def get_call_tree(
    symbol_id: int,
    direction: str = Query(default="outgoing", description="调用方向: outgoing(调用谁) / incoming(被谁调用)"),
    max_depth: int = Query(default=3, ge=1, le=30, description="最大深度")
):
    """
    获取符号的树形调用关系（制表符格式）
    返回示例:
    function_a
    \tfunction_b
    \t\tfunction_c
    \t\tfunction_d
    \tfunction_e
    """
    symbol = db.get_symbol(symbol_id)
    if not symbol:
        raise HTTPException(status_code=404, detail="符号不存在")

    # 构建树形结构
    tree = {
        "symbol": {
            "id": symbol.id,
            "name": symbol.name,
            "kind": symbol.kind,
            "signature": symbol.signature or "",
            "file": symbol.file_path,
            "line": symbol.line_number
        },
        "direction": direction,
        "depth": 0,
        "children": []
    }

    visited = set()
    tree['children'] = _build_call_tree(symbol_id, direction, max_depth, 1, visited)

    # 生成树形字符串
    tree_text = _format_tree_text(symbol.name, symbol.kind, tree['children'])

    # 统计信息
    total_nodes = 1
    def count_nodes(children):
        nonlocal total_nodes
        for child in children:
            total_nodes += 1
            count_nodes(child.get('children', []))

    count_nodes(tree['children'])

    return ApiResponse(
        success=True,
        message="获取成功",
        data={
            "tree": tree,
            "tree_text": tree_text,
            "statistics": {
                "total_nodes": total_nodes,
                "max_depth": max_depth,
                "direction": direction
            }
        }
    )


@app.get("/api/symbols/{symbol_id}/call-tree-text", response_model=ApiResponse)
async def get_call_tree_text(
    symbol_id: int,
    direction: str = Query(default="outgoing", description="调用方向: outgoing(调用谁) / incoming(被谁调用)"),
    max_depth: int = Query(default=3, ge=1, le=30, description="最大深度"),
    format: str = Query(default="compact", description="输出格式: compact(紧凑) / expanded(展开)")
):
    """
    获取符号的树形调用关系（扁平化文本格式，节省token）

    返回示例:
    executeWorkflow (function)
    ├── m_workflowCallback (callback)
    ├── processStep (function)
    │   └── executeInternalStep (function)
    │       └── DataProcessor.processData (function)
    │           ├── checkIntegrity (function)
    │           └── formatData (function)
    ├── m_workflowCallback (callback)
    └── notifyUICallback (function)
    """
    symbol = db.get_symbol(symbol_id)
    if not symbol:
        raise HTTPException(status_code=404, detail="符号不存在")

    # 构建树形结构
    visited = set()
    children = _build_call_tree(symbol_id, direction, max_depth, 1, visited)

    # 生成扁平化树形文本
    tree_text = _format_compact_tree(symbol.name, symbol.kind, children, format == "expanded")

    # 统计信息
    total_nodes = 1
    def count_nodes(child_list):
        nonlocal total_nodes
        for child in child_list:
            total_nodes += 1
            count_nodes(child.get('children', []))

    count_nodes(children)

    return ApiResponse(
        success=True,
        message="获取成功",
        data={
            "symbol": {
                "id": symbol.id,
                "name": symbol.name,
                "kind": symbol.kind,
                "file": symbol.file_path,
                "line": symbol.line_number
            },
            "direction": direction,
            "depth": max_depth,
            "tree_text": tree_text,
            "statistics": {
                "total_nodes": total_nodes,
                "max_depth": max_depth,
                "direction": direction,
                "format": format
            },
            "recursion_info": _detect_recursion_info(symbol_id, direction)
        }
    )


# ========== 类型流分析接口 ==========

@app.get("/api/types/{type_name}/usage", response_model=ApiResponse)
async def get_type_usage(type_name: str):
    """查找使用某类型的所有符号"""
    from type_flow_analyzer import TypeFlowAnalyzer
    analyzer = TypeFlowAnalyzer(db)
    result = analyzer.get_type_usage(type_name)
    return ApiResponse(success=True, message="获取成功", data=result)


@app.get("/api/symbols/{symbol_id}/type-chain", response_model=ApiResponse)
async def get_type_chain(symbol_id: int):
    """获取函数的类型流入/流出链"""
    symbol = db.get_symbol(symbol_id)
    if not symbol:
        raise HTTPException(status_code=404, detail="符号不存在")

    from type_flow_analyzer import TypeFlowAnalyzer
    analyzer = TypeFlowAnalyzer(db)
    result = analyzer.analyze_type_chain(symbol_id)
    return ApiResponse(success=True, message="获取成功", data=result)


# ========== 控制流分支分析接口 ==========

@app.get("/api/symbols/{symbol_id}/branch-paths", response_model=ApiResponse)
async def get_branch_paths(symbol_id: int):
    """获取函数的控制流分支路径"""
    symbol = db.get_symbol(symbol_id)
    if not symbol:
        raise HTTPException(status_code=404, detail="符号不存在")

    # 获取该函数的所有调用依赖
    deps = db.get_dependencies_by_symbol(symbol_id, "outgoing")
    calls = [d for d in deps if d.get('dependency_type') == 'calls']

    # 按分支条件分组
    unconditional = []
    branches = {}

    for dep in calls:
        bt = dep.get('branch_type', '')
        bc = dep.get('branch_condition', '')

        target_id = dep.get('target_symbol_id')
        target_sym = db.get_symbol(target_id) if target_id else None

        entry = {
            "id": target_id,
            "name": dep.get('target_name', target_sym.name if target_sym else 'unknown'),
            "kind": target_sym.kind if target_sym else '',
            "file": target_sym.file_path if target_sym else '',
            "line": dep.get('source_line', 0)
        }

        if not bt or bt == 'unconditional':
            unconditional.append(entry)
        else:
            key = f"{bt}:{bc}" if bc else bt
            if key not in branches:
                branches[key] = {
                    "branch_type": bt,
                    "branch_condition": bc,
                    "calls": []
                }
            branches[key]["calls"].append(entry)

    return ApiResponse(
        success=True,
        message="获取成功",
        data={
            "symbol": {
                "id": symbol.id,
                "name": symbol.name,
                "kind": symbol.kind,
                "file": symbol.file_path,
                "line": symbol.line_number
            },
            "unconditional_calls": unconditional,
            "branch_groups": list(branches.values())
        }
    )


# ========== 错误处理路径接口 ==========

@app.get("/api/symbols/{symbol_id}/error-paths", response_model=ApiResponse)
async def get_error_paths(symbol_id: int):
    """获取函数的错误处理路径信息"""
    symbol = db.get_symbol(symbol_id)
    if not symbol:
        raise HTTPException(status_code=404, detail="符号不存在")

    # 获取该函数的错误路径
    error_paths = db.get_error_paths_by_symbol(symbol_id)

    # 获取该函数调用依赖中的错误上下文
    deps = db.get_dependencies_by_symbol(symbol_id, "outgoing")
    calls_with_error_ctx = []
    for dep in deps:
        if dep.get('dependency_type') == 'calls' and dep.get('error_context'):
            target_id = dep.get('target_symbol_id')
            target_sym = db.get_symbol(target_id) if target_id else None
            calls_with_error_ctx.append({
                "target_id": target_id,
                "target_name": dep.get('target_name', target_sym.name if target_sym else 'unknown'),
                "error_context": dep.get('error_context', ''),
                "caught_type": dep.get('error_context', ''),
                "source_line": dep.get('source_line', 0)
            })

    return ApiResponse(
        success=True,
        message="获取成功",
        data={
            "symbol": {
                "id": symbol.id,
                "name": symbol.name,
                "kind": symbol.kind,
                "file": symbol.file_path,
                "line": symbol.line_number
            },
            "error_paths": error_paths,
            "calls_with_error_context": calls_with_error_ctx
        }
    )


@app.get("/api/error-propagation/{symbol_id}", response_model=ApiResponse)
async def get_error_propagation(symbol_id: int):
    """获取异常传播链：从 throw 到 catch"""
    symbol = db.get_symbol(symbol_id)
    if not symbol:
        raise HTTPException(status_code=404, detail="符号不存在")

    chain = db.get_throw_to_catch_chain(symbol_id)
    return ApiResponse(
        success=True,
        message="获取成功",
        data={
            "symbol": {
                "id": symbol.id,
                "name": symbol.name,
                "kind": symbol.kind,
                "file": symbol.file_path,
                "line": symbol.line_number
            },
            "propagation_chain": chain
        }
    )


def _build_call_tree(symbol_id: int, direction: str, max_depth: int, current_depth: int, visited: set, visiting: set = None) -> list:
    """递归构建调用树"""
    if current_depth > max_depth:
        return []

    # 关键：检查是否正在访问中（检测递归）
    is_recursive = symbol_id in visiting if visiting else False

    # 标记为"正在访问"
    if visiting is None:
        visiting = set()
    visiting.add(symbol_id)

    # 标记为"已访问"
    visited.add(symbol_id)

    children = []

    # 获取依赖关系
    deps = db.get_dependencies_by_symbol(symbol_id, direction)

    for dep in deps:
        if direction == "outgoing":
            target_id = dep.get('target_symbol_id')
        else:
            target_id = dep.get('source_symbol_id')

        if not target_id:
            continue

        # 自递归：目标函数就是自身
        if target_id == symbol_id:
            child_node = {
                "symbol": {
                    "id": target_id,
                    "name": db.get_symbol(symbol_id).name if db.get_symbol(symbol_id) else "unknown",
                    "kind": db.get_symbol(symbol_id).kind if db.get_symbol(symbol_id) else "",
                    "signature": db.get_symbol(symbol_id).signature or "" if db.get_symbol(symbol_id) else "",
                    "file": db.get_symbol(symbol_id).file_path if db.get_symbol(symbol_id) else "",
                    "line": db.get_symbol(symbol_id).line_number if db.get_symbol(symbol_id) else 0,
                    "dep_type": dep.get('dependency_type', ''),
                    "dep_file": dep.get('source_file', '') if direction == "outgoing" else dep.get('target_file', '')
                },
                "depth": current_depth,
                "is_recursive": True,
                "is_recursive_back_edge": True,
                "children": []
            }
            children.append(child_node)
            continue

        if target_id in visited:
            continue

        target = db.get_symbol(target_id)
        if not target:
            continue

        # 检测是否为回调注册函数
        is_callback = _is_callback_function(target.name)
        callback_type = _classify_callback_type(target.name) if is_callback else ""

        # 递归处理（用于检测深层递归）
        sub_children = _build_call_tree(target_id, direction, max_depth, current_depth + 1, visited, visiting)

        # 检测子节点中是否有回指当前节点的递归
        child_is_recursive = any(c.get('is_recursive_back_edge', False) for c in sub_children)
        # 检测是否是直接回指到祖先节点
        is_back_edge = target_id in visiting

        # 添加子节点
        child_node = {
            "symbol": {
                "id": target.id,
                "name": target.name,
                "kind": target.kind,
                "signature": target.signature or "",
                "file": target.file_path,
                "line": target.line_number,
                "dep_type": dep.get('dependency_type', ''),
                "dep_file": dep.get('source_file', '') if direction == "outgoing" else dep.get('target_file', '')
            },
            "depth": current_depth,
            "children": sub_children,
            "is_callback": is_callback,
            "callback_type": callback_type,
            "is_recursive_back_edge": is_back_edge,  # 标记是否回指到调用链中的节点
            "recursive_depth": _calculate_recursive_depth(target_id, symbol_id, direction) if is_back_edge else 0
        }

        children.append(child_node)

    # 移除当前节点，表示已完成访问
    visiting.discard(symbol_id)

    return children


def _calculate_recursive_depth(target_id: int, current_id: int, direction: str) -> int:
    """
    计算递归深度：从 target 回溯到 current 所在调用链的深度
    """
    depth = 1
    visited_path = {current_id}
    current_sym = db.get_symbol(current_id)

    while current_sym:
        deps = db.get_dependencies_by_symbol(current_sym.id, direction)
        found = False

        for dep in deps:
            if direction == "outgoing":
                next_id = dep.get('target_symbol_id')
            else:
                next_id = dep.get('source_symbol_id')

            if next_id == target_id:
                return depth

            if next_id and next_id not in visited_path:
                visited_path.add(next_id)
                next_sym = db.get_symbol(next_id)
                if next_sym:
                    current_sym = next_sym
                    found = True
                    depth += 1
                    break

        if not found:
            break

    return depth


def _detect_recursion_info(symbol_id: int, direction: str) -> dict:
    """
    检测并返回递归调用的详细信息
    """
    recursion_info = {
        "has_recursion": False,
        "recursive_paths": [],
        "max_recursion_depth": 0
    }

    visited = set()
    visiting = set()

    def find_recursive_calls(sym_id: int, path: list, visited: set, visiting: set):
        """DFS检测递归路径"""
        if sym_id in visiting:
            # 发现递归！path中的节点指向当前节点形成递归
            recursion_point = path.index(sym_id)
            recursion_path = path[recursion_point:] + [sym_id]
            recursion_info["has_recursion"] = True
            recursion_info["recursive_paths"].append({
                "path": [db.get_symbol(s).name for s in recursion_path],
                "depth": len(recursion_path) - 1,
                "cycle": [db.get_symbol(s).id for s in recursion_path]
            })
            recursion_info["max_recursion_depth"] = max(
                recursion_info["max_recursion_depth"],
                len(recursion_path) - 1
            )
            return

        if sym_id in visited:
            return

        visiting.add(sym_id)
        path.append(sym_id)

        deps = db.get_dependencies_by_symbol(sym_id, direction)
        for dep in deps:
            if direction == "outgoing":
                next_id = dep.get('target_symbol_id')
            else:
                next_id = dep.get('source_symbol_id')

            if next_id:
                find_recursive_calls(next_id, path.copy(), visited.copy(), visiting)

        visiting.discard(sym_id)
        visited.add(sym_id)

    # 从当前符号开始检测
    find_recursive_calls(symbol_id, [], set(), set())

    return recursion_info


def _is_callback_function(func_name: str) -> bool:
    """检测是否为回调注册函数"""
    func_lower = func_name.lower()
    callback_patterns = [
        'callback', 'cb', 'handler', 'on_', 'on', 'setcallback', 'registercallback',
        'addlistener', 'addobserver', 'sethandler', 'connect', 'subscribe',
        'register', 'attach', 'listen', 'observe'
    ]
    return any(p in func_lower for p in callback_patterns)


def _classify_callback_type(func_name: str) -> str:
    """分类回调类型"""
    func_lower = func_name.lower()

    # 观察者模式
    if any(p in func_lower for p in ['observer', 'listener', 'subscribe', 'observe', 'listen']):
        return 'observer'

    # 回调注册
    if any(p in func_lower for p in ['callback', 'cb', 'handler']):
        return 'callback'

    # 连接/绑定
    if any(p in func_lower for p in ['connect', 'attach', 'bind']):
        return 'connection'

    # 异步
    if any(p in func_lower for p in ['async', 'await', 'promise', 'future']):
        return 'async'

    return 'unknown'


def _format_tree_text(name: str, kind: str, children: list, prefix: str = "", is_last: bool = True) -> str:
    """生成树形文本（带ASCII树枝符号）"""
    # 树枝符号
    connector = "└── " if is_last else "├── "
    lines = [f"{prefix}{connector}{name} ({kind})"]

    # 为子节点准备前缀
    child_prefix = prefix + ("    " if is_last else "│   ")

    # 递归处理子节点
    for i, child in enumerate(children):
        sym = child['symbol']
        child_is_last = (i == len(children) - 1)
        child_text = _format_tree_text(
            sym['name'],
            sym['kind'],
            child.get('children', []),
            child_prefix,
            child_is_last
        )
        lines.append(child_text)

    return "\n".join(lines)


def _format_compact_tree(name: str, kind: str, children: list, expanded: bool = False, visited_stack: list = None) -> str:
    """
    生成紧凑的树形文本（使用Unicode制表符，节省token）

    返回示例:
    executeWorkflow (function)
    ├── m_workflowCallback (callback)
    ├── processStep (function)
    │   └── executeInternalStep (function)
    │       └── DataProcessor.processData (function)
    │           ├── checkIntegrity
    │           └── formatData
    ├── m_workflowCallback (callback)
    └── notifyUICallback (function)

    递归检测示例:
    function_a
    ├── function_b
    │   └── function_a ↺ (recursive: 2)
    └── function_c
    """
    lines = []

    if visited_stack is None:
        visited_stack = []

    def format_node(node_name: str, node_kind: str, node_children: list,
                    prefix: str = "", is_last: bool = True, is_root: bool = False,
                    is_recursive: bool = False, recursive_depth: int = 0):
        """递归格式化节点"""
        # 连接符
        if is_root:
            lines.append(node_name)
        else:
            connector = "└── " if is_last else "├── "
            branch = "    " if is_last else "│   "

            # 添加递归标记
            recursive_marker = ""
            if is_recursive:
                recursive_marker = f" ↺ (recursive: {recursive_depth})"

            lines.append(f"{prefix}{connector}{node_name}{recursive_marker}")

        # 子节点前缀
        if not is_root:
            prefix = prefix + branch

        # 处理子节点
        child_count = len(node_children)
        for i, child in enumerate(node_children):
            sym = child.get('symbol', {})
            child_name = sym.get('name', 'unknown')
            child_kind = sym.get('kind', '')
            child_is_last = (i == child_count - 1)

            # 检查是否递归回边
            child_is_recursive = child.get('is_recursive_back_edge', False)
            child_recursive_depth = child.get('recursive_depth', 0)

            # 紧凑模式：只显示关键类型
            if expanded:
                type_hint = f" ({child_kind})"
            else:
                # 根据名称判断类型
                if child.get('is_callback'):
                    type_hint = " (callback)"
                elif child_kind == 'class':
                    type_hint = " (class)"
                elif child_kind == 'function' and 'process' in child_name.lower():
                    type_hint = ""
                else:
                    type_hint = ""

            # 递归处理子节点
            format_node(
                child_name + type_hint,
                child_kind,
                child.get('children', []),
                prefix,
                child_is_last,
                False,
                child_is_recursive,
                child_recursive_depth
            )

    format_node(name, kind, children, "", True, True, False, 0)
    return "\n".join(lines)


def _format_table_text(headers: list, rows: list) -> str:
    """生成制表符格式的表格文本"""
    if not headers:
        return ""

    # 计算每列最大宽度
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))

    # 生成水平线
    separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"

    # 生成表头
    header_line = "|"
    for i, h in enumerate(headers):
        header_line += f" {h:<{col_widths[i]}} |"
    header_line = header_line.rstrip()

    # 生成数据行
    data_lines = []
    for row in rows:
        line = "|"
        for i, cell in enumerate(row):
            if i < len(col_widths):
                line += f" {str(cell):<{col_widths[i]}} |"
        line = line.rstrip()
        data_lines.append(line)

    # 组装完整表格
    lines = [separator, header_line, separator.replace('-', '=')]
    lines.extend(data_lines)
    lines.append(separator)

    return "\n".join(lines)


# ========== 继承层次接口 ==========

@app.get("/api/symbols/{symbol_id}/hierarchy", response_model=ApiResponse)
async def get_symbol_hierarchy(symbol_id: int):
    """获取 class/struct 的完整继承层次（向上基类 + 向下子类）"""
    symbol = db.get_symbol(symbol_id)
    if not symbol:
        return ApiResponse(success=False, message="符号不存在")

    if symbol.kind not in ('class', 'struct'):
        return ApiResponse(success=False, message="只有 class 或 struct 才有继承关系")

    def build_ancestors(sym_id, visited=None):
        """向上查找基类"""
        if visited is None:
            visited = set()
        if sym_id in visited:
            return []
        visited.add(sym_id)

        ancestors = []
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT target_symbol_id FROM dependencies WHERE source_symbol_id = ? AND dependency_type = 'inheritance'",
                (sym_id,)
            )
            for row in cursor.fetchall():
                target_id = row['target_symbol_id']
                target_sym = db.get_symbol(target_id)
                if target_sym:
                    ancestors.append({
                        'id': target_sym.id,
                        'name': target_sym.name,
                        'kind': target_sym.kind,
                        'namespace': target_sym.namespace,
                        'file_path': target_sym.file_path,
                        'base_classes': build_ancestors(target_id, visited)
                    })
        return ancestors

    def build_descendants(sym_id, visited=None):
        """向下查找子类"""
        if visited is None:
            visited = set()
        if sym_id in visited:
            return []
        visited.add(sym_id)

        descendants = []
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT source_symbol_id FROM dependencies WHERE target_symbol_id = ? AND dependency_type = 'inheritance'",
                (sym_id,)
            )
            for row in cursor.fetchall():
                source_id = row['source_symbol_id']
                source_sym = db.get_symbol(source_id)
                if source_sym:
                    descendants.append({
                        'id': source_sym.id,
                        'name': source_sym.name,
                        'kind': source_sym.kind,
                        'namespace': source_sym.namespace,
                        'file_path': source_sym.file_path,
                        'derived_classes': build_descendants(source_id, visited)
                    })
        return descendants

    result = {
        'symbol': {
            'id': symbol.id,
            'name': symbol.name,
            'kind': symbol.kind,
            'namespace': symbol.namespace,
            'file_path': symbol.file_path,
            'line_number': symbol.line_number
        },
        'base_classes': build_ancestors(symbol_id),
        'derived_classes': build_descendants(symbol_id)
    }

    return ApiResponse(success=True, message="继承层次查询成功", data=result)


# ========== 数据流模拟接口 ==========

from data_flow_simulator import DataFlowSimulator

simulator = DataFlowSimulator(db)


class SimulateRequest(BaseModel):
    symbol_id: int
    input_params: dict = {}
    max_depth: int = 30


@app.post("/api/simulate/trigger", response_model=ApiResponse)
async def simulate_trigger(request: SimulateRequest):
    """模拟从指定函数入口触发的完整数据流"""
    result = simulator.simulate(request.symbol_id, request.input_params, request.max_depth)
    if 'error' in result:
        return ApiResponse(success=False, message=result['error'])
    return ApiResponse(success=True, message="数据流模拟完成", data=result)


@app.get("/api/symbols/{symbol_id}/data-flow", response_model=ApiResponse)
async def get_symbol_data_flow(symbol_id: int):
    """获取指定函数的数据流入/流出关系"""
    result = simulator.trace_data_flow(symbol_id)
    if 'error' in result:
        return ApiResponse(success=False, message=result['error'])
    return ApiResponse(success=True, message="数据流查询成功", data=result)


@app.get("/api/symbols/{symbol_id}/impact", response_model=ApiResponse)
async def get_symbol_impact(symbol_id: int, max_depth: int = Query(default=6, ge=1, le=30)):
    """获取修改指定函数会影响的所有上游调用者"""
    symbol = db.get_symbol(symbol_id)
    if not symbol:
        return ApiResponse(success=False, message="符号不存在")

    impact = simulator._compute_impact(symbol_id, set(), max_depth)
    return ApiResponse(success=True, message="影响分析完成", data=impact)


@app.get("/api/data-flow/trace", response_model=ApiResponse)
async def trace_data_flow(symbol_id: int = Query(...), max_depth: int = Query(default=6, ge=1, le=30)):
    """从指定函数开始的数据流追踪链（轻量版）"""
    result = simulator.trace_data_flow(symbol_id, max_depth)
    if 'error' in result:
        return ApiResponse(success=False, message=result['error'])
    return ApiResponse(success=True, message="追踪完成", data=result)


# ========== 层级管理接口 ==========

@app.get("/api/layers", response_model=ApiResponse)
async def list_layers():
    """获取所有层级配置"""
    layers = db.list_layers()
    return ApiResponse(
        success=True,
        message="获取成功",
        data={"layers": layers}
    )


@app.get("/api/layers/{name}", response_model=ApiResponse)
async def get_layer(name: str):
    """获取单个层级配置"""
    layer = db.get_layer(name)
    if not layer:
        raise HTTPException(status_code=404, detail="层级不存在")
    return ApiResponse(success=True, message="获取成功", data={"layer": layer})


@app.post("/api/layers", response_model=ApiResponse)
async def create_layer(
    name: str = Body(..., description="层级名称"),
    color: str = Body(default="#666666", description="颜色"),
    description: str = Body(default="", description="描述"),
    layer_order: Optional[int] = Body(default=None, description="排序顺序")
):
    """创建新层级"""
    if db.get_layer(name):
        raise HTTPException(status_code=400, detail=f"层级 {name} 已存在")

    layer_id = db.create_layer(name, color, description, layer_order)
    return ApiResponse(
        success=True,
        message=f"层级 {name} 创建成功",
        data={"layer_id": layer_id}
    )


@app.put("/api/layers/{name}", response_model=ApiResponse)
async def update_layer(name: str, updates: dict = Body(...)):
    """更新层级配置"""
    if not db.get_layer(name):
        raise HTTPException(status_code=404, detail="层级不存在")

    success = db.update_layer(name, updates)
    return ApiResponse(success=success, message="更新成功")


@app.delete("/api/layers/{name}", response_model=ApiResponse)
async def delete_layer(name: str):
    """删除层级"""
    if not db.get_layer(name):
        raise HTTPException(status_code=404, detail="层级不存在")

    success = db.delete_layer(name)
    if not success:
        raise HTTPException(status_code=400, detail="无法删除：仍有仓库使用此层级")
    return ApiResponse(success=True, message=f"层级 {name} 已删除")


# ========== 统计接口 ==========

@app.get("/api/statistics", response_model=ApiResponse)
async def get_statistics():
    """获取全局统计信息"""
    repos = db.list_repositories()
    layers = {}

    for repo in repos:
        if repo.layer not in layers:
            layers[repo.layer] = {
                "repositories": [],
                "symbols_count": 0
            }
        layers[repo.layer]["repositories"].append(repo.name)
        layers[repo.layer]["symbols_count"] += db.count_symbols(repository_id=repo.id)

    return ApiResponse(
        success=True,
        message="获取成功",
        data={
            "total_repositories": len(repos),
            "layers": layers,
            "layer_dependencies": db.get_layer_dependencies()
        }
    )


# ========== 健康检查 ==========

@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "database": str(DB_PATH)}


# ========== 静态文件（必须放在所有 API 路由之后） ==========

from fastapi.staticfiles import StaticFiles
STATIC_DIR = Path(__file__).parent.parent / "frontend" / "dist"
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


# ========== 启动服务 ==========

def start_server(host: str = "0.0.0.0", port: int = 8000):
    """启动服务"""
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
