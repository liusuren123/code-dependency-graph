import React, { useState, useCallback, useEffect } from 'react';
import { Activity, Zap, GitMerge, ArrowRight, ChevronRight, ChevronDown, ArrowDown, LogIn, LogOut, FileText } from 'lucide-react';
import { symbolApi, simulateApi } from '../api';

interface AnalysisViewProps {
  symbolId: number | null;
}

interface ImpactNode {
  id: number;
  name: string;
  kind: string;
  namespace?: string;
  file_path?: string;
  repository?: string;
  layer?: string;
  via_line?: number;
  affected_by?: ImpactNode[];
}

export const AnalysisView: React.FC<AnalysisViewProps> = ({ symbolId }) => {
  const [mode, setMode] = useState<'impact' | 'dataflow'>('impact');
  const [impactData, setImpactData] = useState<ImpactNode | null>(null);
  const [dataFlowData, setDataFlowData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [expandedNodes, setExpandedNodes] = useState<Set<number>>(new Set());

  const loadImpact = useCallback(async () => {
    if (!symbolId) return;
    setLoading(true);
    try {
      const data = await symbolApi.getImpact(symbolId, 8);
      setImpactData(data as ImpactNode);
      // 展开所有节点
      const allIds = new Set<number>();
      const collectIds = (node: ImpactNode) => {
        if (node.affected_by && node.affected_by.length > 0) {
          allIds.add(node.id);
          node.affected_by.forEach(collectIds);
        }
      };
      collectIds(data as ImpactNode);
      setExpandedNodes(allIds);
    } catch (err) {
      console.error('Impact analysis error:', err);
    } finally {
      setLoading(false);
    }
  }, [symbolId]);

  const loadDataFlow = useCallback(async () => {
    if (!symbolId) return;
    setLoading(true);
    try {
      const data = await simulateApi.traceDataFlow(symbolId, 6);
      setDataFlowData(data);
    } catch (err) {
      console.error('Data flow trace error:', err);
    } finally {
      setLoading(false);
    }
  }, [symbolId]);

  // 自动触发分析
  useEffect(() => {
    if (symbolId) {
      if (mode === 'impact') loadImpact();
      else loadDataFlow();
    } else {
      setImpactData(null);
      setDataFlowData(null);
    }
  }, [symbolId, mode, loadImpact, loadDataFlow]);

  const runAnalysis = () => {
    if (mode === 'impact') loadImpact();
    else loadDataFlow();
  };

  const toggleNode = (id: number) => {
    setExpandedNodes(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const countDescendants = (node: ImpactNode): number => {
    if (!node.affected_by) return 0;
    return node.affected_by.reduce((sum, c) => sum + 1 + countDescendants(c), 0);
  };

  if (!symbolId) {
    return (
      <div className="av-empty">
        <Activity size={48} className="av-empty-icon" />
        <h3>Analysis View</h3>
        <p>Select a symbol to analyze data flow, impact, and trace paths</p>
      </div>
    );
  }

  return (
    <div className="av-root">
      {/* Toolbar */}
      <div className="av-toolbar">
        <div className="av-mode-toggle">
          <button
            className={`av-mode-btn ${mode === 'impact' ? 'av-mode-active' : ''}`}
            onClick={() => setMode('impact')}
          >
            <Zap size={13} />
            Impact
          </button>
          <button
            className={`av-mode-btn ${mode === 'dataflow' ? 'av-mode-active' : ''}`}
            onClick={() => setMode('dataflow')}
          >
            <GitMerge size={13} />
            Data Flow
          </button>
        </div>
        <button className="av-run-btn" onClick={runAnalysis} disabled={loading}>
          {loading ? 'Analyzing...' : 'Run Analysis'}
        </button>
      </div>

      {/* Content */}
      <div className="av-content">
        {loading && (
          <div className="av-loading">
            <div className="av-spinner" />
            <span>Analyzing...</span>
          </div>
        )}

        {!loading && !impactData && !dataFlowData && (
          <div className="av-placeholder">
            <p>Choose a mode and click <strong>Run Analysis</strong></p>
            <div className="av-mode-desc">
              <div className="av-mode-card">
                <Zap size={16} />
                <strong>Impact Analysis</strong>
                <span>Who would be affected if you modify this function?</span>
              </div>
              <div className="av-mode-card">
                <GitMerge size={16} />
                <strong>Data Flow Trace</strong>
                <span>Trace how data flows through function parameters and return values</span>
              </div>
            </div>
          </div>
        )}

        {/* Impact tree */}
        {!loading && mode === 'impact' && impactData && (
          <div className="av-impact">
            <div className="av-impact-header">
              <span className="av-impact-label">Modification impact</span>
              <span className="av-impact-count">{countDescendants(impactData)} affected symbols</span>
            </div>
            <ImpactTree
              node={impactData}
              expandedNodes={expandedNodes}
              onToggle={toggleNode}
              isRoot
            />
          </div>
        )}

        {/* Data flow */}
        {!loading && mode === 'dataflow' && dataFlowData && (
          <div className="av-dataflow">
            {/* Center symbol */}
            <div className="df-center">
              <div className="df-center-node">
                <span className="df-center-icon">ƒ</span>
                <span className="df-center-name">{dataFlowData.symbol?.name}</span>
                <span className="df-center-file">
                  {dataFlowData.symbol?.file_path?.split(/[\\/]/).pop()}:{dataFlowData.symbol?.line_number}
                </span>
              </div>
            </div>

            <div className="df-columns">
              {/* Flows In */}
              <div className="df-col df-in">
                <div className="df-col-header">
                  <LogIn size={14} />
                  <span>Data In</span>
                  <span className="df-col-count">{dataFlowData.flows_in?.length || 0}</span>
                </div>
                {(!dataFlowData.flows_in || dataFlowData.flows_in.length === 0) ? (
                  <div className="df-empty">No incoming data flows</div>
                ) : (
                  dataFlowData.flows_in.map((flow: any, i: number) => (
                    <div key={i} className="df-flow-card df-flow-in">
                      <div className="df-flow-arrow">
                        <ArrowRight size={14} />
                      </div>
                      <div className="df-flow-body">
                        <span className="df-flow-name">{flow.from || 'external'}</span>
                        <span className="df-flow-type">{flow.type?.replace(/_/g, ' ')}</span>
                        {flow.param && <span className="df-flow-param">param: {flow.param}</span>}
                      </div>
                      <span className="df-flow-line">L{flow.line}</span>
                    </div>
                  ))
                )}
              </div>

              {/* Flows Out */}
              <div className="df-col df-out">
                <div className="df-col-header">
                  <LogOut size={14} />
                  <span>Data Out</span>
                  <span className="df-col-count">{dataFlowData.flows_out?.length || 0}</span>
                </div>
                {(!dataFlowData.flows_out || dataFlowData.flows_out.length === 0) ? (
                  <div className="df-empty">No outgoing data flows</div>
                ) : (
                  dataFlowData.flows_out.map((flow: any, i: number) => (
                    <div key={i} className="df-flow-card df-flow-out">
                      <div className="df-flow-arrow">
                        <ArrowRight size={14} />
                      </div>
                      <div className="df-flow-body">
                        <span className="df-flow-name">{flow.to || 'external'}</span>
                        <span className="df-flow-type">{flow.type?.replace(/_/g, ' ')}</span>
                        {flow.param && <span className="df-flow-param">param: {flow.param}</span>}
                      </div>
                      <span className="df-flow-line">L{flow.line}</span>
                    </div>
                  ))
                )}
              </div>

              {/* Logs */}
              {dataFlowData.logs && dataFlowData.logs.length > 0 && (
                <div className="df-col df-logs">
                  <div className="df-col-header">
                    <FileText size={14} />
                    <span>Log Messages</span>
                    <span className="df-col-count">{dataFlowData.logs.length}</span>
                  </div>
                  {dataFlowData.logs.map((log: any, i: number) => (
                    <div key={i} className={`df-log-card df-log-${log.level}`}>
                      <span className="df-log-level">{log.level}</span>
                      <span className="df-log-msg">{log.message}</span>
                      <span className="df-flow-line">L{log.line}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const ImpactTree: React.FC<{
  node: ImpactNode;
  expandedNodes: Set<number>;
  onToggle: (id: number) => void;
  isRoot?: boolean;
  depth?: number;
}> = ({ node, expandedNodes, onToggle, isRoot, depth = 0 }) => {
  const hasChildren = node.affected_by && node.affected_by.length > 0;
  const isExpanded = expandedNodes.has(node.id);

  return (
    <div className="av-tree-node">
      <div
        className={`av-tree-row ${isRoot ? 'av-tree-root' : ''}`}
        style={{ paddingLeft: depth * 20 + 8 }}
        onClick={() => hasChildren && onToggle(node.id)}
      >
        {hasChildren ? (
          <span className="av-tree-arrow">
            {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          </span>
        ) : (
          <span className="av-tree-leaf" />
        )}
        <span className={`av-tree-kind kind-${node.kind}`}>
          {node.kind === 'function' ? 'ƒ' : node.kind === 'class' ? 'C' : 'T'}
        </span>
        <span className="av-tree-name">{node.name}</span>
        {node.via_line && (
          <span className="av-tree-via">line {node.via_line}</span>
        )}
        {node.repository && (
          <span className="av-tree-repo">{node.repository}</span>
        )}
        {node.file_path && (
          <span className="av-tree-file">{node.file_path.split(/[\\/]/).pop()}:{node.via_line || ''}</span>
        )}
      </div>
      {hasChildren && isExpanded && (
        <div className="av-tree-children">
          {node.affected_by!.map(child => (
            <ImpactTree
              key={child.id}
              node={child}
              expandedNodes={expandedNodes}
              onToggle={onToggle}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
};
