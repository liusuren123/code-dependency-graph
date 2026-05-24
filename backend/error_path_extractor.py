"""
错误处理路径提取器
检测 try/catch/throw，标注函数调用的错误处理上下文
"""
from typing import List, Dict, Optional


class ErrorPathExtractor:
    """提取错误处理路径信息"""

    def extract(self, tree, content: bytes, file_path: str) -> Dict:
        """提取文件中的错误处理路径信息和调用标注

        Returns:
            {
                'error_paths': [...],      # try/catch/throw 记录
                'call_annotations': [...]  # 调用的错误上下文标注
            }
        """
        error_paths = []
        call_annotations = []

        def get_text(node) -> str:
            return node.text.decode('utf-8', errors='ignore')

        def get_line(node) -> int:
            return node.start_point[0] + 1

        def find_func_name(node):
            """向上查找当前所在的函数名"""
            n = node.parent
            while n:
                if n.type == 'function_definition':
                    for child in n.children:
                        if child.type == 'function_declarator':
                            for fc in child.children:
                                if fc.type == 'identifier':
                                    return get_text(fc)
                                elif fc.type == 'qualified_identifier':
                                    parts = get_text(fc).split('::')
                                    return parts[-1] if parts else ''
                        elif child.type == 'identifier':
                            return get_text(child)
                n = n.parent
            return ''

        def extract_caught_type(catch_node) -> str:
            """从 catch_clause 提取捕获的异常类型"""
            for child in catch_node.children:
                if child.type == 'parameter_declaration':
                    # 直接在 parameter_declaration 子节点中找类型
                    type_parts = []
                    for pc in child.children:
                        if pc.type in ('type_identifier', 'qualified_identifier',
                                       'qualified_name'):
                            type_parts.append(get_text(pc))
                        elif pc.type == 'type_qualifier':
                            type_parts.insert(0, get_text(pc).strip())
                        elif pc.type == 'pointer_declarator':
                            for ppc in pc.children:
                                if ppc.type in ('type_identifier', 'qualified_identifier'):
                                    type_parts.append(get_text(ppc))
                        elif pc.type == 'reference_declarator':
                            for ppc in pc.children:
                                if ppc.type in ('type_identifier', 'qualified_identifier'):
                                    type_parts.append(get_text(ppc))
                    return ' '.join(type_parts)
                elif child.type == 'parameter_list':
                    # 有些版本 catch 的参数在 parameter_list 内
                    for plc in child.children:
                        if plc.type == 'parameter_declaration':
                            return extract_caught_type_from_param(plc)
            return ''

        def extract_caught_type_from_param(param_node) -> str:
            """从 parameter_declaration 提取类型"""
            type_parts = []
            for pc in param_node.children:
                if pc.type in ('type_identifier', 'qualified_identifier',
                               'qualified_name'):
                    type_parts.append(get_text(pc))
                elif pc.type == 'type_qualifier':
                    type_parts.insert(0, get_text(pc).strip())
            return ' '.join(type_parts)

        def extract_thrown_expr(throw_node) -> str:
            """从 throw_statement 提取抛出表达式"""
            parts = []
            for child in throw_node.children:
                if child.type != 'throw':
                    parts.append(get_text(child))
            result = ' '.join(parts).strip()
            return result[:200] if result else ''

        def extract_callee_name(node) -> str:
            """提取调用表达式的被调用函数名"""
            for child in node.children:
                if child.type == 'identifier':
                    return get_text(child)
                elif child.type == 'field_expression':
                    for fc in child.children:
                        if fc.type == 'field_identifier':
                            return get_text(fc)
                    parts = get_text(child).split('.')
                    return parts[-1] if parts else ''
                elif child.type == 'qualified_name':
                    name = get_text(child)
                    return name.split('::')[-1] if '::' in name else name
            return ''

        error_context_stack = []  # 当前错误处理上下文栈

        def walk(node, depth=0):
            if depth > 80:
                return

            node_type = node.type

            # try 语句
            if node_type == 'try_statement':
                func_name = find_func_name(node)
                contained_calls = []

                ep = {
                    'error_type': 'try_block',
                    'function': func_name,
                    'file_path': file_path,
                    'line': get_line(node),
                    'caught_types': [],
                    'contained_calls': [],
                }

                error_context_stack.append({'type': 'try', 'ep': ep})
                for child in node.children:
                    walk(child, depth + 1)
                error_context_stack.pop()

                ep['contained_calls'] = contained_calls
                error_paths.append(ep)
                return

            # catch 子句
            elif node_type == 'catch_clause':
                caught_type = extract_caught_type(node)
                func_name = find_func_name(node)

                # 更新父 try_block 的捕获类型
                if error_context_stack:
                    parent = error_context_stack[-1]
                    if parent['type'] == 'try':
                        parent['ep']['caught_types'].append(caught_type)

                catch_ep = {
                    'error_type': 'catch_handler',
                    'function': func_name,
                    'file_path': file_path,
                    'line': get_line(node),
                    'caught_type': caught_type,
                }

                error_context_stack.append({'type': 'catch', 'caught_type': caught_type})
                for child in node.children:
                    walk(child, depth + 1)
                error_context_stack.pop()

                error_paths.append(catch_ep)
                return

            # throw 语句
            elif node_type == 'throw_statement':
                func_name = find_func_name(node)
                thrown_expr = extract_thrown_expr(node)

                error_paths.append({
                    'error_type': 'throw_statement',
                    'function': func_name,
                    'file_path': file_path,
                    'line': get_line(node),
                    'thrown_expression': thrown_expr,
                })

                # 如果在 try 块内，记录到 contained_calls
                if error_context_stack:
                    for ctx in reversed(error_context_stack):
                        if ctx['type'] == 'try':
                            ctx['ep']['contained_calls'].append({
                                'action': 'throw',
                                'expression': thrown_expr,
                                'line': get_line(node)
                            })
                            break

            # 调用表达式 — 标注错误上下文
            elif node_type == 'call_expression':
                callee = extract_callee_name(node)
                if callee and error_context_stack:
                    # 确定当前最内层的错误上下文
                    for ctx in reversed(error_context_stack):
                        if ctx['type'] == 'catch':
                            call_annotations.append({
                                'target': callee,
                                'source_line': get_line(node),
                                'error_context': 'catch_handler',
                                'caught_type': ctx.get('caught_type', ''),
                            })
                            # 记录到 catch handler 的 contained_calls
                            break
                        elif ctx['type'] == 'try':
                            call_annotations.append({
                                'target': callee,
                                'source_line': get_line(node),
                                'error_context': 'try_protected',
                                'caught_type': '',
                            })
                            ctx['ep']['contained_calls'].append({
                                'action': 'call',
                                'target': callee,
                                'line': get_line(node)
                            })
                            break

            for child in node.children:
                walk(child, depth + 1)

        root = tree.root_node if hasattr(tree, 'root_node') else tree
        walk(root)
        return {
            'error_paths': error_paths,
            'call_annotations': call_annotations,
        }
