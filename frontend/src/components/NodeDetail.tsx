import React, { useState, useEffect } from 'react';
import { GraphNode, symbolApi, Symbol } from '../api';
import { CallTreeView } from './CallTreeView';

interface NodeDetailProps {
  node: GraphNode | null;
  onClose?: () => void;
}

const KIND_COLORS: Record<string, string> = {
  function: '#4CAF50',
  class: '#2196F3',
  struct: '#03A9F4',
  enum: '#FF5722',
  typedef: '#9C27B0',
};

const LAYER_COLORS: Record<string, string> = {
  SDK: '#4CAF50',
  LOGIC: '#2196F3',
  BUSINESS: '#FF9800',
  UI: '#9C27B0',
};

export const NodeDetail: React.FC<NodeDetailProps> = ({ node, onClose }) => {
  const [symbol, setSymbol] = useState<Symbol | null>(null);
  const [dependencies, setDependencies] = useState<{
    incoming: any[];
    outgoing: any[];
  }>({ incoming: [], outgoing: [] });
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'info' | 'deps' | 'calltree'>('info');

  useEffect(() => {
    if (node) {
      // 从节点信息直接显示基本信息
      setSymbol({
        id: 0,
        name: node.label,
        kind: node.kind,
        file_path: node.file,
        line_number: node.line,
        namespace: node.namespace,
        return_type: '',
        parameters: '',
        signature: node.signature,
        hash_value: '',
      });
    }
  }, [node]);

  const loadDependencies = async () => {
    if (!symbol || !symbol.id) return;

    setLoading(true);
    try {
      const data = await symbolApi.getDetail(symbol.id);
      setDependencies(data.dependencies);
    } catch (err) {
      console.error('Load dependencies error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleTabChange = (tab: 'info' | 'deps' | 'calltree') => {
    setActiveTab(tab);
    if (tab === 'deps' && symbol?.id) {
      loadDependencies();
    }
  };

  if (!node) return null;

  return (
    <div className="node-detail">
      <div className="detail-header">
        <div className="detail-title">
          <span
            className="kind-badge"
            style={{ background: KIND_COLORS[node.kind] || '#666' }}
          >
            {node.kind}
          </span>
          <h3>{node.label}</h3>
        </div>
        <button className="btn-close" onClick={onClose}>×</button>
      </div>

      <div className="detail-tabs">
        <button
          className={activeTab === 'info' ? 'active' : ''}
          onClick={() => handleTabChange('info')}
        >
          信息
        </button>
        <button
          className={activeTab === 'deps' ? 'active' : ''}
          onClick={() => handleTabChange('deps')}
        >
          依赖
        </button>
        <button
          className={activeTab === 'calltree' ? 'active' : ''}
          onClick={() => handleTabChange('calltree')}
        >
          调用树
        </button>
      </div>

      <div className="detail-content">
        {activeTab === 'info' && (
          <div className="info-section">
            <div className="info-row">
              <label>名称:</label>
              <span>{node.label}</span>
            </div>
            <div className="info-row">
              <label>类型:</label>
              <span style={{ color: KIND_COLORS[node.kind] }}>{node.kind}</span>
            </div>
            <div className="info-row">
              <label>层级:</label>
              <span style={{ color: LAYER_COLORS[node.layer] }}>{node.layer}</span>
            </div>
            <div className="info-row">
              <label>命名空间:</label>
              <span>{node.namespace || '-'}</span>
            </div>
            <div className="info-row">
              <label>位置:</label>
              <span className="location">{node.file}:{node.line}</span>
            </div>
            {node.signature && (
              <div className="info-row signature">
                <label>签名:</label>
                <code>{node.signature}</code>
              </div>
            )}
          </div>
        )}

        {activeTab === 'deps' && (
          <div className="deps-section">
            {loading && <div className="loading">加载中...</div>}

            {!loading && (
              <>
                <div className="deps-group">
                  <h4>被依赖 (Incoming)</h4>
                  {dependencies.incoming.length === 0 ? (
                    <div className="empty">无</div>
                  ) : (
                    <ul className="deps-list">
                      {dependencies.incoming.map((dep, i) => (
                        <li key={i} className="dep-item">
                          <span className="dep-type">{dep.dependency_type}</span>
                          <span className="dep-name">{dep.source_name}</span>
                          <span className="dep-location">
                            {dep.source_file?.split('/').pop()}:{dep.source_line}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div className="deps-group">
                  <h4>依赖 (Outgoing)</h4>
                  {dependencies.outgoing.length === 0 ? (
                    <div className="empty">无</div>
                  ) : (
                    <ul className="deps-list">
                      {dependencies.outgoing.map((dep, i) => (
                        <li key={i} className="dep-item">
                          <span className="dep-type">{dep.dependency_type}</span>
                          <span className="dep-name">{dep.target_name}</span>
                          <span className="dep-location">
                            {dep.target_file?.split('/').pop()}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </>
            )}
          </div>
        )}

        {activeTab === 'calltree' && symbol && symbol.id > 0 && (
          <CallTreeView
            symbolId={symbol.id}
          />
        )}

        {activeTab === 'calltree' && (!symbol || symbol.id === 0) && (
          <div className="calltree-hint">
            <p>调用树功能需要先点击图中的节点查看详情</p>
            <p className="hint">请从左侧搜索面板选择一个符号，然后点击图中的对应节点</p>
          </div>
        )}
      </div>
    </div>
  );
};
