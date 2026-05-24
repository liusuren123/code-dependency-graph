"""
类型流分析器
追踪类型在函数链中的转换，查找类型的使用位置
"""
import json
from typing import Dict, List, Optional


class TypeFlowAnalyzer:
    """分析类型在代码中的流转和使用"""

    def __init__(self, db):
        self.db = db

    def analyze_type_chain(self, symbol_id: int) -> dict:
        """分析函数的类型流入/流出链"""
        symbol = self.db.get_symbol(symbol_id)
        if not symbol:
            return {'error': 'symbol not found'}

        # 解析参数类型
        input_types = []
        if symbol.parameters:
            try:
                params = json.loads(symbol.parameters)
                for p in params:
                    input_types.append({
                        'param': p.get('name', ''),
                        'type': p.get('type', 'void')
                    })
            except (json.JSONDecodeError, TypeError):
                pass

        # 追踪类型通过调用链的流转
        deps = self.db.get_dependencies_by_symbol(symbol_id, 'outgoing')
        calls = [d for d in deps if d.get('dependency_type') == 'calls']

        internal_transforms = []
        for dep in calls:
            target_id = dep.get('target_symbol_id')
            if not target_id:
                continue
            target_sym = self.db.get_symbol(target_id)
            if target_sym:
                internal_transforms.append({
                    'from_type': symbol.return_type,
                    'to_function': target_sym.name,
                    'to_return_type': target_sym.return_type,
                    'line': dep.get('source_line', 0)
                })

        return {
            'symbol': {
                'id': symbol.id,
                'name': symbol.name,
                'kind': symbol.kind,
            },
            'input_types': input_types,
            'output_type': symbol.return_type,
            'internal_transforms': internal_transforms
        }

    def get_type_usage(self, type_name: str) -> dict:
        """查找使用某类型的所有符号"""
        as_param = []
        as_return = []

        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            # 在参数中查找
            cursor.execute("SELECT id, name, kind, file_path, parameters FROM symbols")
            for row in cursor.fetchall():
                r = dict(row)
                params_str = r.get('parameters', '')
                if not params_str:
                    continue
                try:
                    params = json.loads(params_str)
                    for p in params:
                        ptype = p.get('type', '')
                        if type_name in ptype:
                            as_param.append({
                                'symbol_id': r['id'],
                                'name': r['name'],
                                'kind': r['kind'],
                                'file': r['file_path'],
                                'param_name': p.get('name', ''),
                                'param_type': ptype
                            })
                except (json.JSONDecodeError, TypeError):
                    pass

            # 在返回类型中查找
            cursor.execute(
                "SELECT id, name, kind, file_path, return_type FROM symbols WHERE return_type LIKE ?",
                (f'%{type_name}%',)
            )
            for row in cursor.fetchall():
                r = dict(row)
                if type_name in r.get('return_type', ''):
                    as_return.append({
                        'symbol_id': r['id'],
                        'name': r['name'],
                        'kind': r['kind'],
                        'file': r['file_path'],
                        'return_type': r['return_type']
                    })

        return {
            'type_name': type_name,
            'as_parameter': as_param,
            'as_return': as_return,
            'total_usage': len(as_param) + len(as_return)
        }
