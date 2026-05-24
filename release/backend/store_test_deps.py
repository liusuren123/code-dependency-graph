#!/usr/bin/env python3
"""存储测试项目的依赖关系 - 修复版"""
import sys
sys.path.insert(0, 'backend')
from database import Database
from parser import MultiLayerCodeParser
from models import Dependency

db = Database('data/dependency.db')
parser = MultiLayerCodeParser(db)

def store_repo_deps(repo_id):
    """存储单个仓库的依赖"""
    repo = db.get_repository(repo_id)
    if not repo:
        return 0, 0

    symbols, deps = parser.parse_repository(repo)
    print(f"  Parsed: {len(symbols)} symbols, {len(deps)} deps")

    # 存储符号
    for s in symbols:
        db.create_symbol(s)

    # 重新从数据库获取符号，建立映射
    repo_symbols = db.list_symbols(repository_id=repo_id, limit=500)
    name_to_ids = {}  # name -> [ids]
    fname_name_to_id = {}  # "filename:name" -> id

    for s in repo_symbols:
        if s.name not in name_to_ids:
            name_to_ids[s.name] = []
        name_to_ids[s.name].append(s.id)
        fname = s.file_path.split('/')[-1]
        fname_name_to_id[f"{fname}:{s.name}"] = s.id

    print(f"  Stored {len(symbols)} symbols, mapped {len(repo_symbols)} symbols")

    # 函数调用依赖
    call_deps = [d for d in deps if d.get('type') == 'calls']
    print(f"  Found {len(call_deps)} function call dependencies")

    stored = 0
    for dep in call_deps:
        source_name = dep.get('source', '')
        target = dep.get('target', '')
        source_file = dep.get('source_file', '')
        fname = source_file.split('/')[-1]

        # 提取目标函数名
        target_func = target.split('.')[-1] if '.' in target else target
        target_func = target_func.split('->')[-1] if '->' in target_func else target_func

        # 查找源符号
        source_id = fname_name_to_id.get(f"{fname}:{source_name}")
        if not source_id and source_name in name_to_ids:
            source_id = name_to_ids[source_name][0]

        # 查找目标符号
        target_id = fname_name_to_id.get(f"{fname}:{target_func}")
        if not target_id and target_func in name_to_ids:
            target_id = name_to_ids[target_func][0]

        if source_id and target_id and source_id != target_id:
            dep_obj = Dependency(
                source_symbol_id=source_id,
                target_symbol_id=target_id,
                dependency_type='calls',
                source_file=source_file,
                source_line=dep.get('source_line', 0),
                target_file=''
            )
            try:
                db.create_dependency(dep_obj)
                stored += 1
            except:
                pass

    print(f"  Stored {stored} call dependencies")
    return len(symbols), stored

if __name__ == '__main__':
    total_syms = 0
    total_deps = 0
    for repo_id in [8, 9, 10]:
        repo = db.get_repository(repo_id)
        print(f"Processing {repo.name} (ID={repo_id})...")
        syms, deps = store_repo_deps(repo_id)
        total_syms += syms
        total_deps += deps

    print(f"\nTotal: {total_syms} symbols, {total_deps} call dependencies stored")

    # 验证
    print("\n=== Verifying ===")
    symbols = db.list_symbols(repository_id=10, limit=500)
    for s in symbols:
        if s.name == 'executeWorkflow':
            print(f"executeWorkflow: id={s.id}, file={s.file_path.split('/')[-1]}")
            deps = db.get_dependencies_by_symbol(s.id, 'outgoing')
            print(f"  Outgoing deps: {len(deps)}")
            for d in deps:
                print(f"    -> {d.get('target_name', 'unknown')} (type={d.get('dependency_type')})")
