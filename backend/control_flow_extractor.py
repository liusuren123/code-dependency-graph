"""
控制流分支分析提取器
检测函数调用发生的条件（if/else/switch/for/while/ternary），标注分支信息
"""
from typing import List, Dict, Optional


class ControlFlowExtractor:
    """控制流分支分析器：提取调用表达式的控制流上下文"""

    def extract(self, tree, content: bytes, file_path: str) -> List[Dict]:
        """提取文件中所有调用的控制流分支标注"""
        annotations = []

        def get_text(node) -> str:
            return node.text.decode('utf-8', errors='ignore')

        def get_line(node) -> int:
            return node.start_point[0] + 1

        def extract_condition(node) -> str:
            """从控制流语句中提取条件文本"""
            for child in node.children:
                if child.type == 'condition_clause':
                    # tree-sitter: condition_clause 包含 ( expr )
                    inner = get_text(child).strip()
                    if inner.startswith('(') and inner.endswith(')'):
                        inner = inner[1:-1].strip()
                    return inner[:200]
                elif child.type == 'parenthesized_expression':
                    cond = get_text(child).strip()
                    if cond.startswith('(') and cond.endswith(')'):
                        cond = cond[1:-1].strip()
                    return cond[:200]
            return ''

        context_stack = []  # 当前控制流嵌套栈

        def get_branch_info():
            """从栈中获取最内层的分支信息"""
            if not context_stack:
                return 'unconditional', ''
            top = context_stack[-1]
            return top.get('branch_type', 'unconditional'), top.get('condition', '')

        def walk(node, depth=0):
            if depth > 80:
                return

            node_type = node.type

            # if 语句
            if node_type == 'if_statement':
                condition = extract_condition(node)
                frame = {
                    'branch_type': 'conditional',
                    'condition': condition,
                    'line': get_line(node),
                }
                context_stack.append(frame)
                # 先遍历 if 的 then-block（跳过 else_clause）
                for child in node.children:
                    if child.type != 'else_clause':
                        walk(child, depth + 1)
                context_stack.pop()

                # 再处理 else_clause
                for child in node.children:
                    if child.type == 'else_clause':
                        has_elif = any(c.type == 'if_statement' for c in child.children)
                        if has_elif:
                            # else if 链：内层 if_statement 递归走自己的处理逻辑
                            for ec in child.children:
                                if ec.type == 'if_statement':
                                    walk(ec, depth + 1)
                                elif ec.type != 'else':
                                    # else 子句中的非 if 内容
                                    else_frame = {
                                        'branch_type': 'conditional',
                                        'condition': f'!({condition})' if condition else 'else',
                                        'line': get_line(child),
                                    }
                                    context_stack.append(else_frame)
                                    walk(ec, depth + 1)
                                    context_stack.pop()
                        else:
                            # 纯 else
                            else_frame = {
                                'branch_type': 'conditional',
                                'condition': f'!({condition})' if condition else 'else',
                                'line': get_line(child),
                            }
                            context_stack.append(else_frame)
                            for ec in child.children:
                                walk(ec, depth + 1)
                            context_stack.pop()
                return

            # for 循环
            elif node_type == 'for_statement':
                condition = extract_condition(node)
                frame = {
                    'branch_type': 'loop',
                    'condition': f'for({condition})' if condition else 'for-loop',
                    'line': get_line(node),
                }
                context_stack.append(frame)
                for child in node.children:
                    walk(child, depth + 1)
                context_stack.pop()
                return

            # while 循环
            elif node_type == 'while_statement':
                condition = extract_condition(node)
                frame = {
                    'branch_type': 'loop',
                    'condition': f'while({condition})' if condition else 'while-loop',
                    'line': get_line(node),
                }
                context_stack.append(frame)
                for child in node.children:
                    walk(child, depth + 1)
                context_stack.pop()
                return

            # do-while 循环
            elif node_type == 'do_statement':
                condition = extract_condition(node)
                frame = {
                    'branch_type': 'loop',
                    'condition': f'do-while({condition})' if condition else 'do-while',
                    'line': get_line(node),
                }
                context_stack.append(frame)
                for child in node.children:
                    walk(child, depth + 1)
                context_stack.pop()
                return

            # switch 语句
            elif node_type == 'switch_statement':
                condition = extract_condition(node)
                frame = {
                    'branch_type': 'switch',
                    'condition': f'switch({condition})' if condition else 'switch',
                    'line': get_line(node),
                }
                context_stack.append(frame)
                for child in node.children:
                    walk(child, depth + 1)
                context_stack.pop()
                return

            # case 语句
            elif node_type == 'case_statement':
                case_value = ''
                for child in node.children:
                    if child.type not in (':', 'compound_statement', 'break_statement',
                                          'declaration', 'expression_statement'):
                        t = get_text(child).strip()
                        if t and t != 'case':
                            case_value = t
                            break
                frame = {
                    'branch_type': 'switch_case',
                    'condition': f'case {case_value}' if case_value else 'case',
                    'line': get_line(node),
                }
                context_stack.append(frame)
                for child in node.children:
                    walk(child, depth + 1)
                context_stack.pop()
                return

            # 三元表达式
            elif node_type == 'conditional_expression':
                condition = get_text(node.children[0]).strip() if node.children else ''
                frame = {
                    'branch_type': 'ternary',
                    'condition': condition[:200],
                    'line': get_line(node),
                }
                context_stack.append(frame)
                for child in node.children:
                    walk(child, depth + 1)
                context_stack.pop()
                return

            # 调用表达式 — 记录分支标注
            elif node_type == 'call_expression':
                branch_type, branch_condition = get_branch_info()
                # 提取被调用函数名
                callee = self._extract_callee_name(node, get_text)
                if callee:
                    annotations.append({
                        'target': callee,
                        'source_line': get_line(node),
                        'branch_type': branch_type,
                        'branch_condition': branch_condition,
                    })

            # 继续遍历子节点
            for child in node.children:
                walk(child, depth + 1)

        root = tree.root_node if hasattr(tree, 'root_node') else tree
        walk(root)
        return annotations

    def _extract_callee_name(self, node, get_text) -> str:
        """提取调用表达式的被调用函数名"""
        for child in node.children:
            if child.type == 'identifier':
                return get_text(child)
            elif child.type == 'field_expression':
                for fc in child.children:
                    if fc.type == 'field_identifier':
                        return get_text(fc)
                # fallback: last identifier
                parts = get_text(child).split('.')
                return parts[-1] if parts else ''
            elif child.type == 'qualified_name':
                name = get_text(child)
                if '::' in name:
                    return name.split('::')[-1]
                return name
            elif child.type in ('template_function', 'operator_name'):
                return get_text(child)
        return ''
