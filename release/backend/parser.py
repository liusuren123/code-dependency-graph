"""
Tree-sitter 多仓库代码解析器
"""
import os
import re
import json
import glob
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple, Callable
from dataclasses import dataclass, asdict

# 创建解析器专用日志器
logger = logging.getLogger("code-dependency-graph.parser")

try:
    from tree_sitter import Language, Parser
    import tree_sitter_cpp as tscpp
    CPP_LANGUAGE = Language(tscpp.language())
    TREE_SITTER_AVAILABLE = True
except ImportError:
    try:
        from tree_sitter import Language, Parser
        from tree_sitter_languages import get_parser
        CPP_LANGUAGE = None
        TREE_SITTER_AVAILABLE = True
    except ImportError:
        TREE_SITTER_AVAILABLE = False

from models import Symbol, Dependency, Repository, SymbolKind, DependencyType

# 增强的调用提取器
try:
    from enhanced_call_extractor import EnhancedCallExtractor
    ENHANCED_EXTRACTOR_AVAILABLE = True
except ImportError:
    ENHANCED_EXTRACTOR_AVAILABLE = False

# 数据流提取器
try:
    from enhanced_data_flow_extractor import DataFlowExtractor
    DATA_FLOW_EXTRACTOR_AVAILABLE = True
except ImportError:
    DATA_FLOW_EXTRACTOR_AVAILABLE = False

# 控制流分支分析器
try:
    from control_flow_extractor import ControlFlowExtractor
    CONTROL_FLOW_EXTRACTOR_AVAILABLE = True
except ImportError:
    CONTROL_FLOW_EXTRACTOR_AVAILABLE = False

# 错误路径提取器
try:
    from error_path_extractor import ErrorPathExtractor
    ERROR_PATH_EXTRACTOR_AVAILABLE = True
except ImportError:
    ERROR_PATH_EXTRACTOR_AVAILABLE = False


@dataclass
class ParsedSymbol:
    """解析出的符号"""
    name: str
    kind: str
    file_path: str
    line_number: int
    namespace: str
    return_type: str
    parameters: List[Dict]
    signature: str
    hash_value: str


class VSProjectResolver:
    """
    VS 解决方案解析器
    支持 .sln 和 .vcxproj 文件的解析
    """

    @staticmethod
    def find_solution_files(root_path: str) -> List[str]:
        """查找所有 .sln 文件"""
        sln_files = glob.glob(os.path.join(root_path, '**/*.sln'), recursive=True)
        return [f for f in sln_files if os.path.isfile(f)]

    @staticmethod
    def parse_solution(sln_path: str) -> Dict[str, List[str]]:
        """
        解析 .sln 文件，返回项目路径映射
        返回: { "项目名": ["源文件路径", ...] }
        """
        projects = {}
        if not os.path.exists(sln_path):
            return projects

        try:
            with open(sln_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # 解析项目引用
            # 格式: Project("{...}") = "项目名", "项目路径.vcxproj", "{...}"
            project_pattern = re.compile(
                r'Project\("[^"]+"\)\s*=\s*"([^"]+)"\s*,\s*"([^"]+\.vcxproj)"'
            )

            for match in project_pattern.finditer(content):
                project_name = match.group(1)
                vcxproj_path = match.group(2)
                # 解析 vcxproj 获取源文件
                source_files = VSProjectResolver.parse_vcxproj(vcxproj_path, os.path.dirname(sln_path))
                projects[project_name] = source_files

        except Exception as e:
            logger.warning(f"解析解决方案文件失败: {sln_path}, {e}")

        return projects

    @staticmethod
    def parse_vcxproj(vcxproj_path: str, base_dir: str = "") -> List[str]:
        """
        解析 .vcxproj 文件，获取源文件列表
        """
        source_files = []
        if not os.path.exists(vcxproj_path):
            return source_files

        try:
            with open(vcxproj_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # 解析源文件
            # ClCompile, ClInclude 等标签包含源文件
            compile_pattern = re.compile(
                r'<(ClCompile|ClInclude|None)\s+Include\s*=\s*"([^"]+)"'
            )

            for match in compile_pattern.finditer(content):
                src = match.group(2)
                # 转换相对路径为绝对路径
                if not os.path.isabs(src):
                    proj_dir = os.path.dirname(vcxproj_path)
                    src = os.path.join(proj_dir, src)
                source_files.append(os.path.normpath(src))

        except Exception as e:
            logger.warning(f"解析项目文件失败: {vcxproj_path}, {e}")

        return source_files

    @staticmethod
    def get_project_directories(root_path: str) -> List[str]:
        """
        从 .vcxproj 文件获取所有项目目录
        用于更精确地扫描源文件
        """
        vcxproj_files = glob.glob(os.path.join(root_path, '**/*.vcxproj'), recursive=True)

        project_dirs = set()
        for vcxproj in vcxproj_files:
            project_dirs.add(os.path.dirname(vcxproj))

        return list(project_dirs)


class MultiLayerCodeParser:
    """
    多层级代码解析器
    支持跨仓库、多层级的代码依赖分析
    """

    def __init__(self, db, code_graph=None):
        self.db = db
        self.code_graph = code_graph
        self.parser = None
        self.parsed_files: Set[str] = set()
        self.ts_available = TREE_SITTER_AVAILABLE
        self.enhanced_extractor = None
        self.data_flow_extractor = None
        self.control_flow_extractor = None
        self.error_path_extractor = None

        if self.ts_available:
            try:
                self.parser = Parser(CPP_LANGUAGE)
                if ENHANCED_EXTRACTOR_AVAILABLE:
                    self.enhanced_extractor = EnhancedCallExtractor()
                if DATA_FLOW_EXTRACTOR_AVAILABLE:
                    self.data_flow_extractor = DataFlowExtractor()
                if CONTROL_FLOW_EXTRACTOR_AVAILABLE:
                    self.control_flow_extractor = ControlFlowExtractor()
                if ERROR_PATH_EXTRACTOR_AVAILABLE:
                    self.error_path_extractor = ErrorPathExtractor()
            except Exception as e:
                logger.warning(f"无法获取 tree-sitter 解析器: {e}")
                try:
                    self.parser = Parser()
                    self.parser.language = CPP_LANGUAGE
                except Exception as e2:
                    logger.warning(f"Parser 初始化失败，降级到正则解析: {e2}")
                    self.ts_available = False

    def parse_repository(
        self,
        repo: Repository,
        file_extensions: List[str] = None,
        skip_dirs: List[str] = None,
        progress_callback: Callable[[str, int, int, str], None] = None,
        incremental: bool = False,
        parsed_files_cache: dict = None,
        on_file_skipped: Callable[[str], None] = None
    ) -> Tuple[List[Symbol], List[Dependency], List[Dict], List[str]]:
        """
        解析整个仓库

        Args:
            repo: 仓库信息
            file_extensions: 要解析的文件扩展名
            skip_dirs: 要跳过的目录
            progress_callback: 进度回调函数 (stage, current, total, message)
            incremental: 是否增量解析
            parsed_files_cache: 已解析文件的字典 {file_path: file_hash}
            on_file_skipped: 文件被跳过时的回调函数 (file_path)

        Returns:
            (symbols, dependencies, data_flows, error_paths, changed_files) 元组
            changed_files 是被解析（而非跳过）的文件列表
        """
        if file_extensions is None:
            file_extensions = ['.cpp', '.h', '.hpp', '.cxx', '.cc']

        if skip_dirs is None:
            skip_dirs = [
                'build', 'bin', 'obj', '.git', '.svn', 'node_modules',
                'third_party', 'dependencies', 'extern', '__pycache__',
                '.vs', 'Debug', 'Release', 'x64', 'ARM64'
            ]

        all_symbols = []
        all_dependencies = []
        all_data_flows = []
        all_error_paths = []
        changed_files = []  # 记录实际被解析的文件
        self.parsed_files.clear()

        repo_path = Path(repo.path)
        if not repo_path.exists():
            logger.warning(f"仓库路径不存在: {repo.path}")
            return [], [], [], [], []

        # 第一遍：扫描文件
        if progress_callback:
            progress_callback('scanning', 0, 1, '扫描文件中...')

        file_list = []
        for root, dirs, files in os.walk(repo_path):
            # 过滤目录
            dirs[:] = [d for d in dirs if d.lower() not in [x.lower() for x in skip_dirs]]

            for file in files:
                if any(file.endswith(ext) for ext in file_extensions):
                    file_list.append(os.path.join(root, file))

        total_files = len(file_list)
        logger.info(f"扫描完成: 路径={repo.path}, 待解析文件={total_files}")

        # 计算需要解析的文件数量
        if incremental and parsed_files_cache:
            files_to_parse = []
            for fp in file_list:
                file_hash = self._get_file_hash(fp)
                if file_hash != parsed_files_cache.get(fp):
                    files_to_parse.append(fp)
            parse_count = len(files_to_parse)
            logger.info(f"增量解析: {parse_count}/{total_files} 文件需要重新解析")
        else:
            files_to_parse = file_list
            parse_count = total_files

        if progress_callback:
            progress_callback('scanning', 1, 1, f'发现 {total_files} 个源文件, {parse_count} 个需要解析')

        # 第二遍：解析文件
        parsed_idx = 0
        for idx, file_path in enumerate(file_list):
            # 增量解析：检查文件是否变化
            if incremental and parsed_files_cache is not None:
                file_hash = self._get_file_hash(file_path)
                if file_hash == parsed_files_cache.get(file_path):
                    # 文件未变化，跳过
                    if on_file_skipped:
                        on_file_skipped(file_path)
                    continue

            # 文件变化或非增量模式，执行解析
            try:
                symbols, deps, flows, epaths = self.parse_file(file_path, repo)
                all_symbols.extend(symbols)
                all_dependencies.extend(deps)
                all_data_flows.extend(flows)
                all_error_paths.extend(epaths)
                changed_files.append(file_path)
            except Exception as e:
                logger.warning(f"解析文件失败: {file_path}, {e}")

            parsed_idx += 1
            # 报告进度
            if progress_callback and parsed_idx % 10 == 0:
                progress_callback('parsing', parsed_idx, parse_count, f'解析 {os.path.basename(file_path)}')

        if progress_callback:
            progress_callback('completed', parse_count, parse_count, f'解析完成: {len(all_symbols)} 符号 ({len(changed_files)} 文件)')

        logger.info(f"递归解析完成: 路径={repo.path}, 扫描文件={total_files}, 实际解析={len(changed_files)}, 符号={len(all_symbols)}, 依赖={len(all_dependencies)}, 数据流={len(all_data_flows)}, 错误路径={len(all_error_paths)}")
        return all_symbols, all_dependencies, all_data_flows, all_error_paths, changed_files

    def parse_vs_solution(
        self,
        repo: Repository,
        sln_path: str = None
    ) -> Tuple[List[Symbol], List[Dependency]]:
        """
        解析 VS 解决方案（.sln）
        自动查找 .sln 文件并解析所有关联项目

        Args:
            repo: 仓库信息
            sln_path: 可选，指定 .sln 文件路径

        Returns:
            (symbols, dependencies, data_flows) 元组
        """
        all_symbols = []
        all_dependencies = []
        all_data_flows = []
        self.parsed_files.clear()

        repo_path = Path(repo.path)
        if not repo_path.exists():
            logger.warning(f"仓库路径不存在: {repo.path}")
            return [], [], [], []

        # 查找或使用指定的 .sln 文件
        if sln_path:
            sln_files = [sln_path] if os.path.exists(sln_path) else []
        else:
            sln_files = VSProjectResolver.find_solution_files(str(repo_path))

        if not sln_files:
            logger.warning(f"未找到 .sln 文件: {repo.path}")
            return [], [], [], []

        logger.info(f"发现 {len(sln_files)} 个解决方案文件")

        # 已解析的源文件集合（避免重复）
        parsed_source_files = set()
        total_files = 0

        for sln_file in sln_files:
            logger.info(f"解析解决方案: {sln_file}")
            projects = VSProjectResolver.parse_solution(sln_file)

            for project_name, source_files in projects.items():
                logger.debug(f"  项目: {project_name}, 文件数={len(source_files)}")
                total_files += len(source_files)

                for src_file in source_files:
                    if src_file in parsed_source_files:
                        continue
                    if not os.path.exists(src_file):
                        continue

                    parsed_source_files.add(src_file)
                    try:
                        symbols, deps, flows, epaths = self.parse_file(src_file, repo)
                        all_symbols.extend(symbols)
                        all_dependencies.extend(deps)
                        all_data_flows.extend(flows)
                        all_error_paths.extend(epaths)
                    except Exception as e:
                        logger.warning(f"  解析文件失败: {src_file}, {e}")
        logger.info(f"VS解析完成: 解决方案数={len(sln_files)}, 总文件={total_files}, 符号={len(all_symbols)}, 依赖={len(all_dependencies)}, 数据流={len(all_data_flows)}")
        return all_symbols, all_dependencies, all_data_flows, all_error_paths

    def parse_project_directories(
        self,
        repo: Repository,
        directories: List[str] = None
    ) -> Tuple[List[Symbol], List[Dependency], List[Dict], List[Dict]]:
        """
        解析指定的项目目录列表
        用于处理没有 .sln 文件但有多个分散项目的情况

        Args:
            repo: 仓库信息
            directories: 目录列表，如果为 None 则自动查找所有 vcxproj 所在目录

        Returns:
            (symbols, dependencies, data_flows, error_paths) 元组
        """
        all_symbols = []
        all_dependencies = []
        all_data_flows = []
        all_error_paths = []
        self.parsed_files.clear()

        repo_path = Path(repo.path)
        if not repo_path.exists():
            return [], [], [], []

        # 如果没有指定目录，从 .vcxproj 文件获取
        if not directories:
            directories = VSProjectResolver.get_project_directories(str(repo_path))
            logger.info(f"发现 {len(directories)} 个项目目录")

        file_extensions = ['.cpp', '.h', '.hpp', '.cxx', '.cc']
        skip_dirs = {'build', 'bin', 'obj', '.git', '.svn', 'third_party', 'dependencies', '.vs'}

        # 从指定目录收集源文件
        source_files = []
        for directory in directories:
            if not os.path.isabs(directory):
                directory = os.path.join(str(repo_path), directory)

            for root, dirs, files in os.walk(directory):
                # 过滤目录
                dirs[:] = [d for d in dirs if d.lower() not in skip_dirs]

                for file in files:
                    if any(file.endswith(ext) for ext in file_extensions):
                        source_files.append(os.path.join(root, file))

        logger.info(f"收集到 {len(source_files)} 个源文件")

        # 解析所有源文件
        parsed = set()
        for src_file in source_files:
            if src_file in parsed:
                continue
            parsed.add(src_file)

            try:
                symbols, deps, flows, epaths = self.parse_file(src_file, repo)
                all_symbols.extend(symbols)
                all_dependencies.extend(deps)
                all_data_flows.extend(flows)
                all_error_paths.extend(epaths)
            except Exception as e:
                logger.warning(f"解析文件失败: {src_file}, {e}")

        logger.info(f"项目目录解析完成: 符号={len(all_symbols)}, 依赖={len(all_dependencies)}, 数据流={len(all_data_flows)}, 错误路径={len(all_error_paths)}")
        return all_symbols, all_dependencies, all_data_flows, all_error_paths

    def _get_file_hash(self, file_path: str) -> str:
        """计算文件的简单hash（基于修改时间和大小）"""
        import hashlib
        try:
            stat = os.stat(file_path)
            # 使用 mtime + size 作为hash基础
            hash_str = f"{stat.st_mtime}_{stat.st_size}"
            return hashlib.md5(hash_str.encode()).hexdigest()[:16]
        except Exception:
            return ""

    def parse_file(
        self,
        file_path: str,
        repo: Repository
    ) -> Tuple[List[Symbol], List[Dependency], List[Dict], List[Dict]]:
        """
        解析单个文件
        Returns: (symbols, dependencies, data_flows, error_paths)
        """
        if file_path in self.parsed_files:
            return [], [], [], []

        try:
            with open(file_path, 'rb') as f:
                content = f.read()
        except Exception as e:
            return [], [], [], []

        self.parsed_files.add(file_path)

        if not content:
            return [], [], [], []

        symbols = []
        dependencies = []
        data_flows = []

        if self.parser:
            try:
                tree = self.parser.parse(content)
                parsed_symbols = self._extract_symbols(tree.root_node, content, file_path)
                deps = self._extract_dependencies(tree.root_node, content, file_path)

                # 提取函数调用关系
                func_calls = self._extract_function_calls(tree.root_node, content, file_path)
                deps.extend(func_calls)

                # 提取继承关系和组合关系
                inheritance_deps = self._extract_inheritance(tree.root_node, content, file_path)
                deps.extend(inheritance_deps)
                composition_deps = self._extract_member_variables(tree.root_node, content, file_path)
                deps.extend(composition_deps)

                # 提取数据流
                if self.data_flow_extractor:
                    try:
                        data_flows = self.data_flow_extractor.extract_flows(tree, content, file_path)
                    except Exception as e:
                        logger.warning(f"数据流提取失败: {file_path}, {e}")

                # 提取控制流分支标注
                if self.control_flow_extractor:
                    try:
                        branch_annotations = self.control_flow_extractor.extract(tree, content, file_path)
                        # 合并分支标注到对应的调用依赖 dict
                        branch_index = {}
                        for ann in branch_annotations:
                            key = (ann['target'], ann['source_line'])
                            branch_index[key] = ann
                        for dep in deps:
                            if isinstance(dep, dict) and dep.get('type') == 'calls':
                                tgt = dep.get('target', '')
                                if '::' in tgt:
                                    tgt = tgt.split('::')[-1]
                                key = (tgt, dep.get('line', 0))
                                if key in branch_index:
                                    ann = branch_index[key]
                                    dep['branch_type'] = ann['branch_type']
                                    dep['branch_condition'] = ann['branch_condition']
                    except Exception as e:
                        logger.warning(f"控制流提取失败: {file_path}, {e}")

                # 提取错误处理路径
                error_paths = []
                if self.error_path_extractor:
                    try:
                        ep_result = self.error_path_extractor.extract(tree, content, file_path)
                        error_paths = ep_result.get('error_paths', [])
                        # 合并调用标注到 deps
                        for ann in ep_result.get('call_annotations', []):
                            for dep in deps:
                                if isinstance(dep, dict) and dep.get('type') == 'calls':
                                    tgt = dep.get('target', '')
                                    if '::' in tgt:
                                        tgt = tgt.split('::')[-1]
                                    if tgt == ann['target'] and dep.get('line', 0) == ann['source_line']:
                                        dep['error_context'] = ann['error_context']
                                        if ann.get('caught_type'):
                                            dep['error_caught_type'] = ann['caught_type']
                                        break
                    except Exception as e:
                        logger.warning(f"错误路径提取失败: {file_path}, {e}")

                for ps in parsed_symbols:
                    symbol = Symbol(
                        repository_id=repo.id,
                        name=ps.name,
                        kind=ps.kind,
                        file_path=ps.file_path,
                        line_number=ps.line_number,
                        namespace=ps.namespace,
                        return_type=ps.return_type,
                        parameters=json.dumps(ps.parameters, ensure_ascii=False),
                        signature=ps.signature,
                        hash_value=ps.hash_value
                    )
                    symbols.append(symbol)

                # 直接添加依赖关系，不依赖符号匹配
                for dep_info in deps:
                    # 存储为字典格式，后续在 main.py 中处理
                    dependencies.append(dep_info)

            except Exception as e:
                logger.warning(f"解析失败，降级到正则: {file_path}, {e}")
                # 降级到正则解析
                symbols, dependencies = self._parse_with_regex(content, file_path, repo)
        else:
            # 没有 tree-sitter，使用正则解析
            symbols, dependencies = self._parse_with_regex(content, file_path, repo)

        return symbols, dependencies, data_flows, error_paths

    def _extract_symbols(self, root, content: bytes, file_path: str) -> List[ParsedSymbol]:
        """从 AST 提取符号定义"""
        symbols = []
        namespace_stack = []

        def get_text(node) -> str:
            return node.text.decode('utf-8', errors='ignore')

        def walk(node):
            nonlocal namespace_stack

            node_type = node.type

            # 命名空间
            if node_type == 'namespace_alias':
                for child in node.children:
                    if child.type == 'identifier':
                        namespace_stack.append(get_text(child))
                        break
            elif node_type == 'namespace_specifier':
                # 处理 named namespace
                for child in node.children:
                    if child.type == 'identifier':
                        if not namespace_stack or namespace_stack[-1] != get_text(child):
                            namespace_stack.append(get_text(child))
                        break

            # 类定义
            if node_type in ('class_specifier', 'struct_specifier'):
                class_name = None
                for child in node.children:
                    if child.type == 'type_identifier':
                        class_name = get_text(child)
                        break
                    elif child.type == 'identifier' and child.prev_sibling is None:
                        class_name = get_text(child)
                        break

                if class_name:
                    namespace_stack.append(class_name)
                    symbols.append(ParsedSymbol(
                        name=class_name,
                        kind='class' if node_type == 'class_specifier' else 'struct',
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                        namespace='::'.join(namespace_stack[:-1]),
                        return_type='',
                        parameters=[],
                        signature=class_name,
                        hash_value=self._generate_hash(f"{class_name}:class:{file_path}")
                    ))

                    # 继续遍历类内部
                    for child in node.children:
                        walk(child)

                    namespace_stack.pop()
                    return

            # 函数定义/声明
            if node_type == 'function_definition':
                self._extract_function(node, file_path, namespace_stack, symbols, get_text)

            # 成员函数声明
            elif node_type == 'declaration':
                for child in node.children:
                    if child.type == 'function_declarator':
                        self._extract_function_from_declarator(
                            child, node, file_path, namespace_stack, symbols, get_text
                        )

            # 枚举
            elif node_type == 'enum_specifier':
                enum_name = None
                for child in node.children:
                    if child.type == 'type_identifier' or child.type == 'identifier':
                        enum_name = get_text(child)
                        break
                if enum_name:
                    symbols.append(ParsedSymbol(
                        name=enum_name,
                        kind='enum',
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                        namespace='::'.join(namespace_stack),
                        return_type='',
                        parameters=[],
                        signature=enum_name,
                        hash_value=self._generate_hash(f"{enum_name}:enum:{file_path}")
                    ))

            # 继续遍历子节点
            for child in node.children:
                if child.type not in ('comment', 'block_comment', 'line_comment'):
                    walk(child)

        walk(root)
        return symbols

    def _extract_param_type_name(self, param_node, get_text) -> tuple:
        """从 parameter_declaration 提取 (完整类型, 参数名)"""
        type_parts = []
        p_name = ''
        suffix = ''

        for child in param_node.children:
            ct = child.type
            if ct in ('primitive_type', 'type_identifier', 'qualified_identifier',
                      'qualified_name', 'template_type', 'sized_type_specifier'):
                type_parts.append(get_text(child))
            elif ct == 'type_qualifier':
                q = get_text(child).strip()
                if q not in type_parts:
                    type_parts.insert(0, q)
            elif ct == 'pointer_declarator':
                suffix += '*'
                for pc in child.children:
                    if pc.type == 'identifier':
                        p_name = get_text(pc)
            elif ct == 'reference_declarator':
                suffix += '&'
                for pc in child.children:
                    if pc.type == 'identifier':
                        p_name = get_text(pc)
            elif ct == 'identifier':
                p_name = get_text(child)

        p_type = ' '.join(type_parts) + suffix if type_parts else 'void'
        return p_type, p_name

    def _extract_full_type(self, node, get_text) -> str:
        """递归提取完整类型字符串，处理 const/&/*/模板等"""
        # 对于复合类型节点，直接返回完整文本
        if node.type in ('qualified_identifier', 'qualified_name', 'template_type'):
            return get_text(node)

        parts = []
        for child in node.children:
            ct = child.type
            if ct in ('primitive_type', 'type_identifier'):
                parts.append(get_text(child))
            elif ct in ('qualified_identifier', 'qualified_name', 'template_type'):
                parts.append(get_text(child))
            elif ct == 'type_qualifier':
                q = get_text(child).strip()
                if q == 'const':
                    parts.insert(0, 'const')
            elif ct == 'pointer_declarator':
                inner = self._extract_full_type(child, get_text)
                return inner + '*'
            elif ct == 'reference_declarator':
                inner = self._extract_full_type(child, get_text)
                return inner + '&'
            elif ct == 'sized_type_specifier':
                # long, long long, unsigned int 等
                parts.append(get_text(child))
            elif ct in ('identifier', 'field_identifier'):
                # 可能是变量名，不是类型
                pass
            elif ct in ('const', 'volatile', 'mutable', 'register', 'static',
                        'extern', 'inline', 'virtual', 'override', 'final'):
                if ct == 'const':
                    parts.insert(0, 'const')
            elif ct in ('*', '&', '&&'):
                parts.append(ct)
            elif ct not in ('(', ')', '[', ']', '{', '}', '=', ',', ';',
                            'parameter_list', 'argument_list', 'initializer_list',
                            'declaration', 'compound_statement'):
                # 递归处理其他子节点
                inner = self._extract_full_type(child, get_text)
                if inner:
                    parts.append(inner)
        return ' '.join(parts) if parts else ''

    def _extract_full_type_from_nodes(self, nodes, get_text) -> str:
        """从多个 AST 节点拼接类型字符串（用于返回类型）"""
        parts = []
        for node in nodes:
            t = self._extract_full_type(node, get_text)
            if t:
                parts.append(t)
        return ' '.join(parts) if parts else 'void'

    def _extract_function(self, node, file_path: str, namespace_stack: List[str],
                          symbols: List[ParsedSymbol], get_text) -> None:
        """提取函数定义"""
        func_name = None
        return_type = 'void'
        parameters = []

        # 递归查找 identifier（函数名可能在 function_declarator 内部）
        def find_identifier(n):
            if n.type == 'identifier':
                return get_text(n)
            for child in n.children:
                result = find_identifier(child)
                if result:
                    return result
            return None

        # 提取返回类型（从函数定义节点的非 declarator 子节点）
        type_children = []
        for child in node.children:
            if child.type in ('primitive_type', 'type_identifier', 'qualified_identifier',
                              'qualified_name', 'template_type', 'type_qualifier',
                              'sized_type_specifier'):
                type_children.append(child)
            elif child.type == 'function_declarator':
                break
        if type_children:
            return_type = self._extract_full_type_from_nodes(type_children, get_text)

        # 首先尝试在顶层 children 中找函数声明器
        func_declarator = None
        pointer_declarator_node = None
        for child in node.children:
            if child.type == 'function_declarator':
                func_declarator = child
                break
            elif child.type == 'pointer_declarator':
                # 处理返回类型为指针的函数，如 struct ggml_tensor * func(...)
                pointer_declarator_node = child
            elif child.type == 'identifier' and not func_name:
                func_name = get_text(child)

        # 如果找到 function_declarator，从中提取函数名
        if func_declarator:
            declarator_name = find_identifier(func_declarator)
            if declarator_name and not func_name:
                func_name = declarator_name

            # 从 function_declarator 提取参数
            for child in func_declarator.children:
                if child.type == 'parameter_list':
                    for param in child.children:
                        if param.type == 'parameter_declaration':
                            p_type, p_name = self._extract_param_type_name(param, get_text)
                            parameters.append({'type': p_type, 'name': p_name})
                        else:
                            continue  # Skip non-parameter nodes
        # 处理 pointer_declarator（如 struct ggml_tensor * func(...)）
        elif pointer_declarator_node:
            declarator_name = find_identifier(pointer_declarator_node)
            if declarator_name and not func_name:
                func_name = declarator_name

            # 从 pointer_declarator 提取参数
            for child in pointer_declarator_node.children:
                if child.type == 'parameter_list':
                    for param in child.children:
                        if param.type == 'parameter_declaration':
                            p_type, p_name = self._extract_param_type_name(param, get_text)
                            parameters.append({'type': p_type, 'name': p_name})
                elif child.type == 'function_declarator':
                    for param in child.children:
                        if param.type == 'parameter_list':
                            for p in param.children:
                                if p.type == 'parameter_declaration':
                                    p_type, p_name = self._extract_param_type_name(p, get_text)
                                    parameters.append({'type': p_type, 'name': p_name})

        if func_name and not func_name.startswith('_') and func_name not in (
            'if', 'else', 'elif', 'for', 'while', 'do', 'switch', 'case', 'default',
            'break', 'continue', 'return', 'goto', 'try', 'catch', 'throw', 'sizeof',
            'new', 'delete', 'delete[]', 'true', 'false', 'nullptr', 'this', 'auto'
        ):
            namespace = '::'.join(namespace_stack)
            signature = f"{return_type} {namespace}{':' * bool(namespace)}{func_name}({','.join(p['type'] for p in parameters)})"

            symbols.append(ParsedSymbol(
                name=func_name,
                kind='function',
                file_path=file_path,
                line_number=node.start_point[0] + 1,
                namespace=namespace,
                return_type=return_type,
                parameters=parameters,
                signature=signature,
                hash_value=self._generate_hash(f"{signature}:{file_path}:{node.start_point[0] + 1}")
            ))

    def _extract_function_from_declarator(self, declarator, declaration_node,
                                          file_path: str, namespace_stack: List[str],
                                          symbols: List[ParsedSymbol], get_text) -> None:
        """从声明器提取函数声明"""
        func_name = None
        return_type = 'auto'
        parameters = []

        # 获取返回类型
        for child in declaration_node.children:
            if child.type in ('primitive_type', 'type_identifier', 'qualified_name'):
                return_type = get_text(child)
                break

        for child in declarator.children:
            if child.type == 'identifier':
                func_name = get_text(child)
            if child.type == 'parameter_list':
                for param in child.children:
                    if param.type == 'parameter_declaration':
                        p_type = 'void'
                        p_name = ''
                        for pchild in param.children:
                            if pchild.type in ('primitive_type', 'type_identifier', 'qualified_name'):
                                p_type = get_text(pchild)
                            elif pchild.type == 'identifier':
                                p_name = get_text(pchild)
                        if p_type:
                            parameters.append({'type': p_type, 'name': p_name})

        if func_name:
            namespace = '::'.join(namespace_stack)
            signature = f"{return_type} {namespace}{':' * bool(namespace)}{func_name}({','.join(p['type'] for p in parameters)})"

            symbols.append(ParsedSymbol(
                name=func_name,
                kind='function',
                file_path=file_path,
                line_number=declaration_node.start_point[0] + 1,
                namespace=namespace,
                return_type=return_type,
                parameters=parameters,
                signature=signature,
                hash_value=self._generate_hash(f"{signature}:{file_path}:{declaration_node.start_point[0] + 1}")
            ))

    def _extract_dependencies(self, root, content: bytes, file_path: str) -> List[Dict]:
        """提取依赖关系"""
        dependencies = []

        def walk(node):
            node_type = node.type

            # #include 依赖
            if node_type == 'preproc_include':
                text = node.text.decode('utf-8', errors='ignore')
                # 提取 include 路径
                if '<' in text:
                    # #include <header.h>
                    path = text.split('<')[1]
                    if '>' in path:
                        path = path.split('>')[0]
                elif '"' in text:
                    # #include "header.h"
                    path = text.split('"')[1]
                else:
                    path = text.replace('#include', '').strip()

                dependencies.append({
                    'type': 'include',
                    'source': file_path,  # 当前文件作为 source
                    'target': path,
                    'line': node.start_point[0] + 1
                })

            # 继续遍历
            for child in node.children:
                walk(child)

        walk(root)
        return dependencies

    def _extract_inheritance(self, root, content: bytes, file_path: str) -> List[Dict]:
        """提取类继承关系"""
        dependencies = []

        def get_text(node) -> str:
            return node.text.decode('utf-8', errors='ignore')

        def walk(node):
            node_type = node.type

            if node_type in ('class_specifier', 'struct_specifier'):
                class_name = None
                base_classes = []

                for child in node.children:
                    if child.type in ('type_identifier', 'identifier') and not class_name:
                        if child.prev_sibling is None or child.type == 'type_identifier':
                            class_name = get_text(child)
                    elif child.type == 'base_class_clause':
                        for bc in child.children:
                            if bc.type in ('type_identifier', 'qualified_name', 'qualified_identifier'):
                                base_name = get_text(bc)
                                if '<' in base_name:
                                    base_name = base_name[:base_name.index('<')]
                                base_classes.append(base_name)

                if class_name and base_classes:
                    for base in base_classes:
                        # Strip namespace prefix for matching
                        base_simple = base.split('::')[-1] if '::' in base else base
                        dependencies.append({
                            'type': 'inheritance',
                            'source': class_name,
                            'source_file': file_path,
                            'target': base_simple,
                            'target_full': base,
                            'line': node.start_point[0] + 1
                        })

                # Continue walking inside the class
                for child in node.children:
                    walk(child)
                return

            for child in node.children:
                if child.type not in ('comment', 'block_comment', 'line_comment'):
                    walk(child)

        walk(root)
        return dependencies

    def _extract_member_variables(self, root, content: bytes, file_path: str) -> List[Dict]:
        """提取类成员变量类型（组合关系）"""
        dependencies = []
        current_class = [None]

        def get_text(node) -> str:
            return node.text.decode('utf-8', errors='ignore')

        def walk(node, depth=0):
            if depth > 60:
                return

            node_type = node.type

            if node_type in ('class_specifier', 'struct_specifier'):
                old_class = current_class[0]
                for child in node.children:
                    if child.type in ('type_identifier', 'identifier'):
                        if child.prev_sibling is None or child.type == 'type_identifier':
                            current_class[0] = get_text(child)
                            break

                for child in node.children:
                    walk(child, depth + 1)

                current_class[0] = old_class
                return

            # Member variable declaration inside a class
            if node_type == 'field_declaration' and current_class[0]:
                var_type = None
                for child in node.children:
                    if child.type in ('type_identifier', 'qualified_name'):
                        type_name = get_text(child)
                        # Skip basic types and STL types
                        if type_name not in ('string', 'vector', 'map', 'set', 'int', 'bool',
                                             'float', 'double', 'void', 'auto', 'size_t',
                                             'std::string', 'std::vector', 'std::map'):
                            var_type = type_name
                        break

                if var_type and current_class[0]:
                    # Strip template args
                    if '<' in var_type:
                        var_type = var_type[:var_type.index('<')]
                    simple_type = var_type.split('::')[-1] if '::' in var_type else var_type
                    dependencies.append({
                        'type': 'composition',
                        'source': current_class[0],
                        'source_file': file_path,
                        'target': simple_type,
                        'line': node.start_point[0] + 1
                    })

            for child in node.children:
                if child.type not in ('comment', 'block_comment', 'line_comment'):
                    walk(child, depth + 1)

        walk(root)
        return dependencies

    def _extract_function_calls(self, root, content: bytes, file_path: str) -> List[Dict]:
        """提取函数调用关系（增强版）"""
        calls = []

        # 如果有增强提取器，使用它
        if self.enhanced_extractor:
            try:
                enhanced_calls = self.enhanced_extractor.extract_calls(root, content, file_path)
                calls.extend(enhanced_calls)
                return calls
            except Exception as e:
                logger.warning(f"增强提取失败，回退到基础方法: {e}")

        # 回退到基础方法
        calls.extend(self._extract_function_calls_basic(root, content, file_path))
        return calls

    def _extract_function_calls_basic(self, root, content: bytes, file_path: str) -> List[Dict]:
        """基础函数调用提取"""
        calls = []

        def get_text(node) -> str:
            return node.text.decode('utf-8', errors='ignore')

        def get_line_number(node) -> int:
            return node.start_point[0] + 1

        # 跟踪当前函数上下文
        current_function = {'name': None, 'line': 0, 'full_name': None}

        def walk(node):
            nonlocal current_function

            node_type = node.type

            # 遇到函数定义，更新上下文
            if node_type == 'function_definition':
                func_name = None
                for child in node.children:
                    if child.type == 'identifier' and not func_name:
                        func_name = get_text(child)
                        break

                # 保存旧的上下文
                old_function = current_function.copy() if current_function['name'] else None

                # 设置新上下文
                current_function = {
                    'name': func_name,
                    'line': get_line_number(node),
                    'full_name': func_name
                }

                # 遍历所有子节点
                for child in node.children:
                    if child.type not in ('comment', 'block_comment', 'line_comment'):
                        walk(child)

                # 恢复旧上下文
                current_function = old_function if old_function else {'name': None, 'line': 0, 'full_name': None}
                return

            # 遇到 call_expression，记录调用
            if node_type == 'call_expression':
                # 获取被调用的函数名
                called_func = None
                for child in node.children:
                    if child.type == 'identifier':
                        called_func = get_text(child)
                        break
                    elif child.type == 'field_expression':
                        # 处理成员函数调用 like obj.method()
                        for field_child in child.children:
                            if field_child.type == 'field_identifier':
                                field_name = get_text(field_child)
                                # 尝试获取对象名
                                obj_name = None
                                for obj_child in child.children:
                                    if obj_child.type == 'identifier':
                                        obj_name = get_text(obj_child)
                                        break
                                if obj_name:
                                    called_func = f"{obj_name}.{field_name}"
                                else:
                                    called_func = field_name
                                break
                    elif child.type == 'qualified_name':
                        # 处理命名空间限定调用 like ns::func()
                        called_func = get_text(child)

                if called_func and current_function['name'] and called_func != current_function['name']:
                    calls.append({
                        'type': 'calls',
                        'source': current_function['name'],  # 调用者函数
                        'source_line': current_function['line'],
                        'source_file': file_path,
                        'target': called_func,  # 被调用的函数
                        'target_line': get_line_number(node),
                        'line': get_line_number(node)
                    })

            # 继续遍历子节点
            for child in node.children:
                if child.type not in ('comment', 'block_comment', 'line_comment'):
                    walk(child)

        walk(root)
        return calls

    def _find_symbol(self, ref: str, symbol_map: Dict) -> Optional[Symbol]:
        """在已知符号中查找引用"""
        # 简化实现：按名称匹配
        for symbols in symbol_map.values():
            for sym in symbols:
                if sym.name == ref:
                    return sym
        return None

    def _find_symbol_by_include(self, include_path: str, repo: Repository) -> Optional[Symbol]:
        """通过 include 路径查找符号"""
        # 从 include 路径推断头文件名
        header_name = os.path.basename(include_path).replace('.h', '').replace('.hpp', '')

        # 在数据库中查找
        symbols = self.db.list_symbols(repository_id=repo.id, keyword=header_name)
        for sym in symbols:
            if sym.kind in ('class', 'struct'):
                return sym
        return None

    def _parse_with_regex(self, content: bytes, file_path: str, repo: Repository) -> Tuple[List[Symbol], List[Dependency]]:
        """使用正则表达式解析（降级方案）"""
        text = content.decode('utf-8', errors='ignore')
        symbols = []
        dependencies = []

        # 函数模式
        func_pattern = re.compile(
            r'(?:(?:public|private|protected)\s+)?'
            r'((?:[\w:]+(?:\s*[*&]+)?\s+)+?)'  # 返回类型
            r'(\w+)\s*\('  # 函数名
            r'([^)]*)'  # 参数
            r'\)\s*(?:const)?\s*(?:override)?\s*(?:noexcept)?\s*'
            r'\{?'
        )

        # 类模式
        class_pattern = re.compile(
            r'(?:class|struct)\s+(\w+)\s*(?::\s*public\s+\w+\s*,?\s*)*\{?'
        )

        # Include 模式
        include_pattern = re.compile(r'#include\s*[<"]([^>"]+)[>"]')

        for match in func_pattern.finditer(text):
            return_type = match.group(1).strip()
            func_name = match.group(2)
            params = match.group(3).strip()

            # 解析参数
            param_list = []
            for p in params.split(','):
                p = p.strip()
                if p:
                    parts = p.rsplit(None, 1)
                    if len(parts) == 2:
                        param_list.append({'type': parts[0], 'name': parts[1]})
                    else:
                        param_list.append({'type': parts[0], 'name': ''})

            signature = f"{return_type} {func_name}({','.join(p['type'] for p in param_list)})"

            symbols.append(Symbol(
                repository_id=repo.id,
                name=func_name,
                kind='function',
                file_path=file_path,
                line_number=text[:match.start()].count('\n') + 1,
                namespace='',
                return_type=return_type,
                parameters=json.dumps(param_list, ensure_ascii=False),
                signature=signature,
                hash_value=self._generate_hash(f"{signature}:{file_path}:{text[:match.start()].count(chr(10)) + 1}")
            ))

        for match in class_pattern.finditer(text):
            class_name = match.group(1)
            symbols.append(Symbol(
                repository_id=repo.id,
                name=class_name,
                kind='class',
                file_path=file_path,
                line_number=text[:match.start()].count('\n') + 1,
                namespace='',
                return_type='',
                parameters='[]',
                signature=class_name,
                hash_value=self._generate_hash(f"{class_name}:class:{file_path}")
            ))

        for match in include_pattern.finditer(text):
            include_path = match.group(1)
            line_no = text[:match.start()].count('\n') + 1
            # 依赖关系稍后处理
            dependencies.append({
                'type': 'include',
                'source': file_path,
                'target': include_path,
                'line': line_no
            })

        return symbols, dependencies

    def _generate_hash(self, content: str) -> str:
        """生成注释无关的哈希值"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
