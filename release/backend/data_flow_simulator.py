"""
数据流模拟器
模拟从入口函数触发的完整数据流转，追踪调用链、参数传递、日志输出和影响范围
"""
from typing import List, Dict, Set, Optional
import json


class DataFlowSimulator:
    def __init__(self, db):
        self.db = db

    def simulate(self, symbol_id: int, input_params: dict = None, max_depth: int = 8) -> dict:
        """模拟从指定函数入口触发的数据流"""
        symbol = self.db.get_symbol(symbol_id)
        if not symbol:
            return {'error': 'Symbol not found'}

        # Get repo info
        repo = None
        repos = self.db.list_repositories()
        for r in repos:
            if r.id == symbol.repository_id:
                repo = r
                break

        # Build call tree with data flow annotations
        visited = set()
        trace = self._trace(symbol_id, input_params or {}, max_depth, visited, 0)

        # Collect all logs from the trace
        all_logs = []
        self._collect_logs(trace, all_logs)

        # Compute impact set
        impact_visited = set()
        impact = self._compute_impact(symbol_id, impact_visited, max_depth)

        return {
            'entry': {
                'id': symbol.id,
                'name': symbol.name,
                'kind': symbol.kind,
                'namespace': symbol.namespace,
                'file_path': symbol.file_path,
                'signature': symbol.signature,
                'repository': repo.name if repo else '',
                'layer': repo.layer if repo else '',
            },
            'input_params': input_params or {},
            'trace': trace,
            'logs': all_logs,
            'impact': impact,
        }

    def _trace(self, symbol_id: int, params: dict, max_depth: int,
               visited: set, depth: int) -> dict:
        """递归追踪数据流"""
        if depth > max_depth or symbol_id in visited:
            return {'id': symbol_id, 'circular': True}

        visited.add(symbol_id)
        symbol = self.db.get_symbol(symbol_id)
        if not symbol:
            return {'id': symbol_id, 'error': 'Symbol not found'}

        # Get repo info
        repo_name = ''
        repo_layer = ''
        repos = self.db.list_repositories()
        for r in repos:
            if r.id == symbol.repository_id:
                repo_name = r.name
                repo_layer = r.layer
                break

        node = {
            'id': symbol.id,
            'name': symbol.name,
            'kind': symbol.kind,
            'namespace': symbol.namespace,
            'file_path': symbol.file_path,
            'line_number': symbol.line_number,
            'repository': repo_name,
            'layer': repo_layer,
            'params_in': params,
            'calls': [],
            'data_flows': [],
            'logs': [],
        }

        # Get outgoing calls (dependencies where this symbol is the source)
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT target_symbol_id, source_line FROM dependencies WHERE source_symbol_id = ? AND dependency_type = 'calls'",
                (symbol_id,)
            )
            outgoing = cursor.fetchall()

        # Get data flows from this symbol
        flows = self.db.get_data_flows_by_source(symbol_id)

        for flow in flows:
            if flow['flow_type'] == 'log_output':
                detail = json.loads(flow.get('detail', '{}')) if flow.get('detail') else {}
                node['logs'].append({
                    'line': flow['line_number'],
                    'level': detail.get('log_level', 'info'),
                    'message': flow['source_param'][:100],
                    'file': flow['file_path'],
                })
            elif flow['flow_type'] == 'param_pass':
                node['data_flows'].append({
                    'type': 'param_pass',
                    'param': flow['source_param'],
                    'target_param': flow['target_param'],
                    'target_name': flow.get('target_name', ''),
                    'line': flow['line_number'],
                })
            elif flow['flow_type'] == 'return_chain':
                node['data_flows'].append({
                    'type': 'return_chain',
                    'from': flow.get('target_name', ''),
                    'param': flow['source_param'],
                    'line': flow['line_number'],
                })

        # Recursively trace called functions
        for row in outgoing:
            target_id = row['target_symbol_id'] if isinstance(row, dict) else row[0]
            # Find matching data flows for this call
            call_flows = [f for f in flows
                         if f.get('target_symbol_id') == target_id and f['flow_type'] == 'param_pass']
            child_params = {}
            for cf in call_flows:
                child_params[cf['target_param']] = cf['source_param']

            child_trace = self._trace(target_id, child_params, max_depth, set(visited), depth + 1)
            if child_trace:
                child_trace['call_line'] = row['source_line'] if isinstance(row, dict) else row[1]
                node['calls'].append(child_trace)

        return node

    def _collect_logs(self, trace: dict, logs: list):
        """递归收集所有日志点"""
        if not trace:
            return
        for log in trace.get('logs', []):
            log['caller'] = trace.get('name', '')
            logs.append(log)
        for call in trace.get('calls', []):
            self._collect_logs(call, logs)

    def _compute_impact(self, symbol_id: int, visited: set, max_depth: int) -> dict:
        """计算影响范围：哪些下游函数会受到影响"""
        if symbol_id in visited or max_depth <= 0:
            return {'id': symbol_id, 'name': '', 'already_visited': True}
        visited.add(symbol_id)

        symbol = self.db.get_symbol(symbol_id)
        if not symbol:
            return {'id': symbol_id, 'error': 'not found'}

        # Get repo
        repo_name = ''
        repo_layer = ''
        repos = self.db.list_repositories()
        for r in repos:
            if r.id == symbol.repository_id:
                repo_name = r.name
                repo_layer = r.layer

        impact = {
            'id': symbol.id,
            'name': symbol.name,
            'kind': symbol.kind,
            'namespace': symbol.namespace,
            'file_path': symbol.file_path,
            'repository': repo_name,
            'layer': repo_layer,
            'affected_by': [],
        }

        # Find who calls this function (incoming calls)
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT source_symbol_id, source_line FROM dependencies WHERE target_symbol_id = ? AND dependency_type = 'calls'",
                (symbol_id,)
            )
            callers = cursor.fetchall()

        for row in callers:
            caller_id = row['source_symbol_id'] if isinstance(row, dict) else row[0]
            caller_impact = self._compute_impact(caller_id, set(visited), max_depth - 1)
            if caller_impact:
                caller_impact['via_line'] = row['source_line'] if isinstance(row, dict) else row[1]
                impact['affected_by'].append(caller_impact)

        return impact

    def trace_data_flow(self, symbol_id: int, max_depth: int = 6) -> dict:
        """轻量级数据流追踪（不含完整模拟）"""
        symbol = self.db.get_symbol(symbol_id)
        if not symbol:
            return {'error': 'Symbol not found'}

        flows_in = self.db.get_data_flows_by_target(symbol_id)
        flows_out = self.db.get_data_flows_by_source(symbol_id)
        logs = self.db.get_log_outputs(symbol_id)

        return {
            'symbol': {
                'id': symbol.id,
                'name': symbol.name,
                'kind': symbol.kind,
                'file_path': symbol.file_path,
                'line_number': symbol.line_number,
            },
            'flows_in': [{
                'from': f.get('source_name', ''),
                'type': f['flow_type'],
                'param': f['source_param'],
                'line': f['line_number'],
            } for f in flows_in],
            'flows_out': [{
                'to': f.get('target_name', ''),
                'type': f['flow_type'],
                'param': f['source_param'],
                'line': f['line_number'],
            } for f in flows_out],
            'logs': [{
                'level': json.loads(f.get('detail', '{}')).get('log_level', 'info'),
                'message': f['source_param'][:100],
                'line': f['line_number'],
            } for f in logs],
        }
