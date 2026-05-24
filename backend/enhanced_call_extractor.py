"""
增强的函数调用提取器
支持更多复杂的 C++ 调用模式
包含回调链路检测
"""
from typing import List, Dict, Set, Optional, Tuple
import re

class EnhancedCallExtractor:
    """增强的函数调用提取器"""

    def __init__(self):
        self.current_function = None
        self.function_stack = []  # 支持嵌套函数

        # 命名空间追踪
        self.namespace_stack = []
        self.current_class = None

        # 已知类型信息
        self.type_definitions = {}  # type_name -> methods

        # 函数注册表
        self.function_table = {}  # func_name -> [locations]

        # 回调模式配置
        self.callback_patterns = {
            # 回调注册函数名模式
            'callback_registrars': [
                'callback', 'cb', 'handler', 'on_', 'on', 'setCallback', 'registerCallback',
                'addListener', 'addObserver', 'setHandler', 'connect', 'subscribe',
                'register', 'attach', 'listen', 'observe'
            ],
            # 回调参数类型模式
            'callback_types': [
                'Callback', 'Handler', 'Listener', 'Observer', 'Func', 'Function',
                'std::function', 'function', 'CallbackFunction', 'EventHandler',
                'std::callback', 'using Callback', 'using Handler'
            ],
            # 异步函数模式
            'async_patterns': [
                'async', 'Async', 'Await', 'await', 'then', 'promise', 'Promise',
                'future', 'Future', 'Task'
            ]
        }

    def extract_calls(self, tree, content: bytes, file_path: str) -> List[Dict]:
        """从 AST 提取所有函数调用"""
        calls = []

        def get_text(node) -> str:
            return node.text.decode('utf-8', errors='ignore')

        def get_line(node) -> int:
            return node.start_point[0] + 1

        def qualify_name(name: str) -> str:
            """生成完全限定名"""
            parts = []
            if self.current_class:
                parts.append(self.current_class)
            parts.extend(self.namespace_stack)
            if name:
                parts.append(name)
            return '::'.join(parts)

        def walk(node, depth=0):
            if depth > 50:  # 防止无限递归
                return

            node_type = node.type

            # 函数定义 - 进入新上下文
            if node_type == 'function_definition':
                self._handle_function_entry(node, get_text, get_line)
                for child in node.children:
                    if child.type not in ('comment', 'block_comment', 'line_comment'):
                        walk(child, depth + 1)
                self._handle_function_exit()
                return

            # 类/结构体定义
            elif node_type in ('class_specifier', 'struct_specifier'):
                old_class = self.current_class
                for child in node.children:
                    if child.type in ('type_identifier', 'identifier'):
                        if child.prev_sibling is None or child.type == 'type_identifier':
                            self.current_class = get_text(child)
                            break
                for child in node.children:
                    if child.type not in ('comment', 'block_comment', 'line_comment'):
                        walk(child, depth + 1)
                self.current_class = old_class
                return

            # 命名空间
            elif node_type in ('namespace_alias', 'namespace_specifier'):
                for child in node.children:
                    if child.type == 'identifier':
                        ns = get_text(child)
                        if ns not in self.namespace_stack:
                            self.namespace_stack.append(ns)
                        break

            # 函数调用表达式
            elif node_type == 'call_expression':
                call_info = self._extract_call_expression(node, get_text, get_line, file_path, qualify_name)
                if call_info:
                    calls.append(call_info)

            # emit 信号调用: emit signalX(args)
            elif node_type == 'emit_statement':
                caller = self.function_stack[-1] if self.function_stack else None
                if caller:
                    for child in node.children:
                        if child.type == 'call_expression':
                            emit_call = self._extract_call_expression(child, get_text, get_line, file_path, qualify_name)
                            if emit_call:
                                calls.append(emit_call)
                                break
                        elif child.type == 'identifier':
                            calls.append({
                                'type': 'calls',
                                'source': caller['name'],
                                'source_line': caller['line'],
                                'source_file': file_path,
                                'target': get_text(child),
                                'target_line': get_line(node),
                                'line': get_line(node),
                                'call_type': 'emit'
                            })
                            break

            # new 表达式: new ClassName(args)
            elif node_type == 'new_expression':
                caller = self.function_stack[-1] if self.function_stack else None
                if caller:
                    for child in node.children:
                        if child.type in ('type_identifier', 'identifier', 'qualified_name', 'template_type'):
                            class_name = get_text(child)
                            # 去掉模板参数
                            if '<' in class_name:
                                class_name = class_name[:class_name.index('<')]
                            calls.append({
                                'type': 'calls',
                                'source': caller['name'],
                                'source_line': caller['line'],
                                'source_file': file_path,
                                'target': class_name,
                                'target_line': get_line(node),
                                'line': get_line(node),
                                'call_type': 'constructor'
                            })
                            break

            # Lambda 表达式 - 检测回调
            elif node_type == 'lambda_expression':
                lambda_info = self._extract_lambda_info(node, get_text, get_line, file_path)
                if lambda_info:
                    calls.append(lambda_info)

            # 构造函数调用
            elif node_type == 'declaration' and self._is_constructor(node, get_text):
                calls.append(self._handle_constructor_init(node, get_text, get_line, file_path))

            # 模板实例化（隐含函数调用）
            elif node_type == 'template_declaration':
                self._handle_template(node, get_text)

            # 继续遍历
            for child in node.children:
                if child.type not in ('comment', 'block_comment', 'line_comment'):
                    walk(child, depth + 1)

        walk(tree.root_node if hasattr(tree, 'root_node') else tree)
        return calls

    def _handle_function_entry(self, node, get_text, get_line):
        """处理函数入口"""
        func_name = None
        return_type = None
        params = []

        # 递归查找 identifier（因为它可能在 function_declarator 内部）
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
            elif child.type == 'function_declarator' and not func_name:
                # 在 function_declarator 中查找 identifier
                func_name = find_identifier(child)
            elif child.type == 'primitive_type':
                return_type = get_text(child)
            elif child.type == 'parameter_list':
                params = self._parse_params(child, get_text)

        # 完全限定名
        qualified_name = func_name
        if self.current_class:
            qualified_name = f"{self.current_class}::{func_name}"
        if self.namespace_stack:
            qualified_name = '::'.join(self.namespace_stack) + '::' + qualified_name

        self.function_stack.append({
            'name': func_name,
            'qualified_name': qualified_name,
            'line': get_line(node),
            'return_type': return_type,
            'params': params
        })

    def _handle_function_exit(self):
        """处理函数退出"""
        if self.function_stack:
            self.function_stack.pop()

    def _extract_call_expression(self, node, get_text, get_line, file_path, qualify_func) -> Optional[Dict]:
        """提取 call_expression 的详细信息"""
        called_func = None
        called_qualified = None
        caller = self.function_stack[-1] if self.function_stack else None
        call_pattern = None   # 'simple', 'field', 'qualified'
        receiver = None       # field_expression 的调用对象
        qualifier = None      # qualified_name 的类名前缀

        for child in node.children:
            # 简单函数调用: func()
            if child.type == 'identifier':
                call_pattern = 'simple'
                called_func = get_text(child)
                called_qualified = qualify_func(called_func)

            # 成员函数调用: obj.method() 或 obj->method()
            elif child.type == 'field_expression':
                call_pattern = 'field'
                called_func, receiver = self._extract_field_call(child, get_text)
                called_qualified = called_func

            # 限定名称调用: ns::func() 或 Class::method()
            elif child.type == 'qualified_name':
                call_pattern = 'qualified'
                full_name = get_text(child)
                parts = full_name.split('::')
                called_func = parts[-1]
                qualifier = '::'.join(parts[:-1])
                called_qualified = called_func

            # 模板函数调用: make_shared<T>()
            elif child.type == 'template_function':
                call_pattern = 'simple'
                called_func = get_text(child)
                called_qualified = called_func

            # 运算符调用: operator+(a, b)
            elif child.type == 'operator_name':
                call_pattern = 'simple'
                called_func = get_text(child)
                called_qualified = f"operator{called_func}"

        if called_func and caller:
            call_type = self._classify_call(node, called_func)
            if self._is_recursive_call(called_func, caller, call_pattern, receiver, qualifier):
                call_type = 'recursive'
            return {
                'type': 'calls',
                'source': caller['name'],
                'source_line': caller['line'],
                'source_file': file_path,
                'target': called_qualified,
                'target_line': get_line(node),
                'line': get_line(node),
                'call_type': call_type
            }

        return None

    def _is_recursive_call(self, called_func: str, caller: dict,
                           call_pattern: str, receiver: str = None,
                           qualifier: str = None) -> bool:
        """判断是否为真正的递归调用（同一函数调用自身）

        区分三种调用模式：
        - simple: validate() 在类方法内等价于 this->validate()，同名即为递归
        - field: obj.validate() 仅当 obj 是 this 时为递归
        - qualified: Class::validate() 仅当 Class 与 caller 所在类相同时为递归
        """
        if called_func != caller['name']:
            return False

        if call_pattern == 'field':
            return receiver == 'this'
        elif call_pattern == 'qualified':
            return qualifier == self.current_class
        else:
            # simple: 裸函数调用，在类方法内隐含 this->
            return True

    def _extract_field_call(self, node, get_text) -> Tuple[str, Optional[str]]:
        """提取成员函数调用"""
        receiver = None
        method_name = None

        for child in node.children:
            if child.type == 'identifier':
                if not receiver:
                    receiver = get_text(child)
                else:
                    method_name = get_text(child)
            elif child.type == 'field_identifier':
                method_name = get_text(child)
            elif child.type == 'pointer_expression':
                # 处理 ptr->method()
                for grandchild in child.children:
                    if grandchild.type == 'identifier':
                        receiver = f"{get_text(grandchild)}->"
                        break

        return method_name, receiver

    def _is_constructor(self, node, get_text) -> bool:
        """检查是否是构造函数初始化"""
        # 检查子节点是否有 init_list (构造函数初始化列表)
        for child in node.children:
            if child.type == 'field_initializer_list':
                return True
        return False

    def _handle_constructor_init(self, node, get_text, get_line, file_path) -> Dict:
        """处理构造函数初始化"""
        for child in node.children:
            if child.type == 'field_initializer_list':
                for init in child.children:
                    if init.type == 'field_initializer':
                        for init_child in init.children:
                            if init_child.type == 'identifier':
                                return {
                                    'type': 'calls',
                                    'source': 'constructor',
                                    'source_line': get_line(node),
                                    'source_file': file_path,
                                    'target': get_text(init_child),
                                    'target_line': get_line(init),
                                    'line': get_line(init),
                                    'call_type': 'initializer'
                                }
        return None

    def _handle_template(self, node, get_text):
        """处理模板声明"""
        # 记录模板信息用于后续解析
        pass

    def _parse_params(self, param_node, get_text) -> List[str]:
        """解析参数列表"""
        params = []
        for child in param_node.children:
            if child.type == 'parameter_declaration':
                for pchild in child.children:
                    if pchild.type in ('type_identifier', 'primitive_type'):
                        params.append(get_text(pchild))
        return params

    def _classify_call(self, node, func_name: str) -> str:
        """分类函数调用类型"""
        # 常见库函数分类
        if func_name.startswith('std::') or func_name in [
            'make_shared', 'make_unique', 'allocate_shared',
            'string', 'vector', 'map', 'set', 'unique_ptr', 'shared_ptr'
        ]:
            return 'stl_call'
        elif func_name.startswith('winrt::') or func_name.startswith('Windows::'):
            return 'winrt_call'
        elif func_name.endswith('_t') or func_name.endswith('_v'):
            return 'type_trait'
        elif func_name.startswith('operator'):
            return 'operator'
        else:
            return 'user_call'

    def _extract_lambda_info(self, node, get_text, get_line, file_path) -> Optional[Dict]:
        """提取Lambda表达式信息，检测可能的回调"""
        caller = self.function_stack[-1] if self.function_stack else None
        if not caller:
            return None

        # 查找Lambda体内部的函数调用
        lambda_calls = []
        captures = []

        for child in node.children:
            # 捕获列表
            if child.type == 'lambda_capture_specifier':
                captures_text = get_text(child)
                # 提取捕获的变量
                for cp in child.children:
                    if cp.type in ('identifier', 'this'):
                        captures.append(get_text(cp))

            # Lambda体内的调用
            elif child.type == 'block':
                for block_child in child.children:
                    if block_child.type == 'call_expression':
                        call = self._extract_call_expression(block_child, get_text, get_line, file_path, lambda n: n)
                        if call:
                            lambda_calls.append(call)

        if not lambda_calls:
            return None

        # 检测是否捕获引用（可能造成数据回传）
        has_ref_capture = any('&' in str(c) for c in captures)

        return {
            'type': 'lambda_callback',
            'source': caller['qualified_name'],
            'source_line': caller['line'],
            'source_file': file_path,
            'target': '<lambda>',
            'target_line': get_line(node),
            'line': get_line(node),
            'call_type': 'lambda',
            'is_callback': True,
            'has_ref_capture': has_ref_capture,
            'captures': captures,
            'inner_calls': [
                {
                    'func': c.get('target', ''),
                    'line': c.get('line', 0)
                }
                for c in lambda_calls[:5]  # 最多5个内部调用
            ],
            'callback_type': 'lambda_ref' if has_ref_capture else 'lambda_val'
        }

    def _is_callback_registration(self, func_name: str) -> bool:
        """检测是否是回调注册函数"""
        func_lower = func_name.lower()
        for pattern in self.callback_patterns['callback_registrars']:
            if pattern.lower() in func_lower:
                return True
        return False

    def _classify_callback_type(self, node, func_name: str) -> str:
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

    def detect_callback_patterns(self, calls: List[Dict]) -> List[Dict]:
        """检测并标记可能的回调注册"""
        callback_calls = []

        for call in calls:
            func_name = call.get('target', '')
            if self._is_callback_registration(func_name):
                call['is_callback'] = True
                call['callback_type'] = self._classify_callback_type(call, func_name)
                callback_calls.append(call)

        return callback_calls