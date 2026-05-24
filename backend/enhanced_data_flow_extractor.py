"""
数据流提取器
从 AST 中提取函数间数据流：参数传递、返回值链路、日志输出
"""
from typing import List, Dict, Optional, Set, Tuple
import re

# 常见日志函数名
LOG_FUNCTIONS = {
    'info', 'debug', 'warning', 'error', 'critical', 'trace', 'warn',
    'log', 'LOG', 'Log',
    'printf', 'fprintf', 'sprintf',
    'cout', 'cerr', 'clog',
}


class DataFlowExtractor:
    def __init__(self):
        self.current_function = None
        self.param_names = []

    def extract_flows(self, tree, content: bytes, file_path: str) -> List[Dict]:
        flows = []
        self.current_function = None
        self.param_names = []

        def get_text(node) -> str:
            return node.text.decode('utf-8', errors='ignore')

        def get_line(node) -> int:
            return node.start_point[0] + 1

        def walk(node, depth=0):
            if depth > 60:
                return
            node_type = node.type

            if node_type == 'function_definition':
                self._handle_function(node, get_text, get_line)
                for child in node.children:
                    if child.type in ('compound_statement', 'block'):
                        self._analyze_block(child, get_text, get_line, file_path, flows)
                self.current_function = None
                self.param_names = []
                return

            for child in node.children:
                if child.type not in ('comment', 'block_comment', 'line_comment'):
                    walk(child, depth + 1)

        root = tree.root_node if hasattr(tree, 'root_node') else tree
        walk(root)
        return flows

    def _handle_function(self, node, get_text, get_line):
        """Extract function name and parameter names."""
        func_name = None
        params = []

        def find_identifier(n):
            if n.type == 'identifier':
                return get_text(n)
            for child in n.children:
                result = find_identifier(child)
                if result:
                    return result
            return None

        for child in node.children:
            if child.type == 'identifier' and not func_name:
                func_name = get_text(child)
            elif child.type == 'function_declarator':
                # Handle qualified names like ClassName::methodName
                for dc in child.children:
                    if dc.type == 'qualified_identifier':
                        # Get the last identifier (the method name)
                        parts = []
                        for qc in dc.children:
                            if qc.type == 'identifier':
                                parts.append(get_text(qc))
                        if parts:
                            func_name = parts[-1]
                    elif dc.type == 'identifier' and not func_name:
                        func_name = get_text(dc)
                    elif dc.type == 'field_identifier' and not func_name:
                        func_name = get_text(dc)

                if not func_name:
                    ident = find_identifier(child)
                    if ident:
                        func_name = ident

                for fc in child.children:
                    if fc.type == 'parameter_list':
                        params = self._extract_param_names(fc, get_text)

        self.current_function = func_name
        self.param_names = params

    def _extract_param_names(self, param_list, get_text) -> List[str]:
        """Extract parameter names from parameter_list node."""
        names = []
        for child in param_list.children:
            if child.type == 'parameter_declaration':
                for pc in child.children:
                    if pc.type == 'identifier':
                        names.append(get_text(pc))
                        break
        return names

    def _analyze_block(self, block, get_text, get_line, file_path, flows):
        """Analyze a function block for data flows."""
        if not self.current_function:
            return

        def walk_stmt(node, depth=0):
            if depth > 40:
                return
            node_type = node.type

            # Variable declarations with initializer: auto x = func()
            if node_type == 'declaration':
                self._check_declaration(node, get_text, get_line, file_path, flows)

            # Return statements
            elif node_type == 'return_statement':
                self._check_return(node, get_text, get_line, file_path, flows)

            # Call expressions (standalone or in expressions)
            elif node_type == 'call_expression':
                self._check_call(node, get_text, get_line, file_path, flows)

            for child in node.children:
                if child.type not in ('comment', 'block_comment', 'line_comment'):
                    walk_stmt(child, depth + 1)

        walk_stmt(block)

    def _check_declaration(self, node, get_text, get_line, file_path, flows):
        """Check variable declaration for data flow: auto x = someFunc(...)"""
        var_name = None
        init_call = None
        init_line = get_line(node)

        for child in node.children:
            if child.type == 'identifier' and not var_name:
                var_name = get_text(child)
            elif child.type == 'call_expression':
                init_call = child
            elif child.type == 'assignment_expression':
                for ac in child.children:
                    if ac.type == 'call_expression':
                        init_call = ac

        if init_call and var_name:
            callee = self._get_callee_name(init_call, get_text)
            if callee:
                arg_names = self._get_call_args(init_call, get_text)
                for i, arg in enumerate(arg_names):
                    if arg in self.param_names:
                        flows.append({
                            'flow_type': 'param_pass',
                            'source_symbol': self.current_function,
                            'target_symbol': callee,
                            'source_param': arg,
                            'target_param': f'arg{i}',
                            'source_line': get_line(init_call),
                            'file_path': file_path,
                        })

    def _check_return(self, node, get_text, get_line, file_path, flows):
        """Check return statement for return value chain."""
        for child in node.children:
            if child.type == 'call_expression':
                callee = self._get_callee_name(child, get_text)
                if callee:
                    arg_names = self._get_call_args(child, get_text)
                    for i, arg in enumerate(arg_names):
                        if arg in self.param_names:
                            flows.append({
                                'flow_type': 'param_pass',
                                'source_symbol': self.current_function,
                                'target_symbol': callee,
                                'source_param': arg,
                                'target_param': f'arg{i}',
                                'source_line': get_line(child),
                                'file_path': file_path,
                            })
                    flows.append({
                        'flow_type': 'return_chain',
                        'source_symbol': callee,
                        'target_symbol': self.current_function,
                        'source_param': '',
                        'target_param': 'return',
                        'source_line': get_line(child),
                        'file_path': file_path,
                    })
            elif child.type == 'identifier':
                var_name = get_text(child)
                if var_name in self.param_names:
                    flows.append({
                        'flow_type': 'return_chain',
                        'source_symbol': self.current_function,
                        'target_symbol': self.current_function,
                        'source_param': var_name,
                        'target_param': 'return',
                        'source_line': get_line(node),
                        'file_path': file_path,
                    })

    def _check_call(self, node, get_text, get_line, file_path, flows):
        """Check call expression for parameter passing and log output."""
        callee = self._get_callee_name(node, get_text)
        if not callee:
            return

        call_line = get_line(node)
        arg_names = self._get_call_args(node, get_text)

        # Check if this is a log call
        if callee in LOG_FUNCTIONS:
            # Build the log message expression
            msg_expr = ', '.join(arg_names) if arg_names else ''
            flows.append({
                'flow_type': 'log_output',
                'source_symbol': self.current_function,
                'target_symbol': callee,
                'source_param': msg_expr,
                'target_param': '',
                'source_line': call_line,
                'file_path': file_path,
                'log_level': self._classify_log_level(callee),
            })
            return

        # Check for field_expression logger.info / logger.debug etc.
        for child in node.children:
            if child.type == 'field_expression':
                parts = []
                for fc in child.children:
                    if fc.type in ('identifier', 'field_identifier'):
                        parts.append(get_text(fc))
                if len(parts) >= 2 and parts[-1] in LOG_FUNCTIONS:
                    msg_expr = ', '.join(arg_names) if arg_names else ''
                    flows.append({
                        'flow_type': 'log_output',
                        'source_symbol': self.current_function,
                        'target_symbol': f'{parts[-2]}.{parts[-1]}',
                        'source_param': msg_expr,
                        'target_param': '',
                        'source_line': call_line,
                        'file_path': file_path,
                        'log_level': self._classify_log_level(parts[-1]),
                    })
                    return

        # Parameter passing
        for i, arg in enumerate(arg_names):
            if arg in self.param_names:
                flows.append({
                    'flow_type': 'param_pass',
                    'source_symbol': self.current_function,
                    'target_symbol': callee,
                    'source_param': arg,
                    'target_param': f'arg{i}',
                    'source_line': call_line,
                    'file_path': file_path,
                })

        # String concatenation argument containing params
        for child in node.children:
            if child.type == 'argument_list':
                self._check_concat_args(child, get_text, callee, call_line, file_path, flows)

    def _check_concat_args(self, arg_list, get_text, callee, line, file_path, flows):
        """Check for string concatenation in arguments that contain params."""
        for child in arg_list.children:
            if child.type == 'binary_expression':
                text = get_text(child)
                if '+' in text:
                    for param in self.param_names:
                        if param in text:
                            flows.append({
                                'flow_type': 'param_pass',
                                'source_symbol': self.current_function,
                                'target_symbol': callee,
                                'source_param': param,
                                'target_param': 'concat_expr',
                                'source_line': line,
                                'file_path': file_path,
                            })

    def _get_callee_name(self, call_node, get_text) -> Optional[str]:
        """Extract the callee function name from a call_expression."""
        for child in call_node.children:
            if child.type == 'identifier':
                return get_text(child)
            elif child.type == 'field_expression':
                for fc in child.children:
                    if fc.type == 'field_identifier':
                        return get_text(fc)
                # Fallback: use last identifier
                parts = []
                for fc in child.children:
                    if fc.type in ('identifier', 'field_identifier'):
                        parts.append(get_text(fc))
                return parts[-1] if parts else None
            elif child.type == 'qualified_name':
                name = get_text(child)
                return name.split('::')[-1] if '::' in name else name
        return None

    def _get_call_args(self, call_node, get_text) -> List[str]:
        """Extract argument expressions from call_expression."""
        args = []
        for child in call_node.children:
            if child.type == 'argument_list':
                for arg in child.children:
                    if arg.type == 'identifier':
                        args.append(get_text(arg))
                    elif arg.type == 'string_literal':
                        # Get string content (first 60 chars)
                        text = get_text(arg)
                        # Strip quotes
                        inner = text.strip('"').strip("'")
                        if len(inner) > 60:
                            inner = inner[:60] + '...'
                        args.append(inner)
                    elif arg.type == 'number_literal':
                        args.append(get_text(arg))
                    elif arg.type == 'field_expression':
                        args.append(get_text(arg))
                    elif arg.type == 'binary_expression':
                        # String concatenation like "prefix" + var
                        args.append(get_text(arg)[:80])
                    elif arg.type == 'call_expression':
                        args.append(get_text(arg)[:60])
        return args

    def _classify_log_level(self, func_name: str) -> str:
        """Classify log level from function name."""
        name_lower = func_name.lower()
        if 'error' in name_lower or 'critical' in name_lower:
            return 'error'
        elif 'warn' in name_lower:
            return 'warning'
        elif 'info' in name_lower:
            return 'info'
        elif 'debug' in name_lower or 'trace' in name_lower:
            return 'debug'
        elif func_name in ('printf', 'fprintf', 'sprintf'):
            return 'info'
        elif func_name in ('cout', 'clog'):
            return 'info'
        elif func_name == 'cerr':
            return 'error'
        return 'info'
