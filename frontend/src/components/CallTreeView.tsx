import React, { useState, useEffect, useCallback } from 'react';
import { symbolApi, CallTreeNode, Symbol } from '../api';
import { X, FileCode, ArrowRight, ArrowLeft } from 'lucide-react';

interface CallTreeViewProps {
  symbolId: number;
  onNodeClick?: (node: CallTreeNode) => void;
  onClose?: () => void;
}

// 回调节点类型（从API获取）
interface CallTreeNodeWithCallback extends CallTreeNode {
  is_callback?: boolean;
  callback_type?: 'callback' | 'observer' | 'connection' | 'async' | 'lambda_ref' | 'lambda_val' | 'unknown';
  has_ref_capture?: boolean;
}

// 源代码片段类型
interface SourceSnippet {
  file_path: string;
  relative_path: string;
  target_line: number;
  total_lines: number;
  snippet: Array<{ line_number: number; content: string; is_target: boolean }>;
}

// 检测是否为回调函数
function isCallbackFunction(funcName: string): { isCallback: boolean; callbackType?: string } {
  const funcLower = funcName.toLowerCase();
  const patterns = [
    'callback', 'cb', 'handler', 'on_', 'on', 'setcallback', 'registercallback',
    'addlistener', 'addobserver', 'sethandler', 'connect', 'subscribe',
    'register', 'attach', 'listen', 'observe'
  ];

  for (const pattern of patterns) {
    if (funcLower.includes(pattern)) {
      // 进一步分类
      if (/observer|listener|subscribe|observe|listen/.test(funcLower)) {
        return { isCallback: true, callbackType: 'observer' };
      }
      if (/callback|cb|handler/.test(funcLower)) {
        return { isCallback: true, callbackType: 'callback' };
      }
      if (/connect|attach|bind/.test(funcLower)) {
        return { isCallback: true, callbackType: 'connection' };
      }
      if (/async|promise|future|task/.test(funcLower)) {
        return { isCallback: true, callbackType: 'async' };
      }
      return { isCallback: true, callbackType: 'unknown' };
    }
  }
  return { isCallback: false };
}

// 树节点组件
interface TreeNodeProps {
  node: CallTreeNode;
  depth: number;
  onToggle: (nodeId: number) => void;
  expandedNodes: Set<number>;
  showCallbacksOnly: boolean;
  highlightedCallback?: { isCallback: boolean; callbackType?: string };
  onSelect?: (node: CallTreeNode) => void;
  isSelected?: boolean;
}

const TreeNode: React.FC<TreeNodeProps> = ({ node, depth, onToggle, expandedNodes, showCallbacksOnly, highlightedCallback, onSelect, isSelected }) => {
  const hasChildren = node.children && node.children.length > 0;
  const isExpanded = expandedNodes.has(node.symbol.id);

  // 检测回调
  const callbackInfo = isCallbackFunction(node.symbol.name);
  const isCallback = node.symbol.kind === 'function' && (callbackInfo.isCallback || (node as any).is_callback);
  const callbackType = (node as any).callback_type || callbackInfo.callbackType;

  // 如果启用回调过滤，且不是回调节点，则不显示
  if (showCallbacksOnly && !isCallback) {
    return null;
  }

  const handleClick = () => {
    if (hasChildren) {
      onToggle(node.symbol.id);
    }
  };

  const handleNodeClick = (e: React.MouseEvent) => {
    e.stopPropagation();
  };

  // 获取回调类型标签
  const getCallbackBadge = (type?: string) => {
    if (!type) return null;
    switch (type) {
      case 'observer': return <span className="callback-badge observer">观察者</span>;
      case 'connection': return <span className="callback-badge connection">连接</span>;
      case 'async': return <span className="callback-badge async">异步</span>;
      case 'lambda_ref': return <span className="callback-badge lambda-ref">Lambda↩</span>;
      case 'lambda_val': return <span className="callback-badge lambda-val">Lambda</span>;
      default: return <span className="callback-badge">回调</span>;
    }
  };

  return (
    <div className={`tree-node ${isCallback ? 'callback-node' : ''}`}>
      <div
        className={`tree-node-content ${hasChildren ? 'has-children' : ''} ${isCallback ? 'callback' : ''}`}
        style={{ paddingLeft: depth * 20 + 4 }}
        onClick={handleClick}
      >
        {hasChildren && (
          <span className="tree-toggle" onClick={(e) => { e.stopPropagation(); onToggle(node.symbol.id); }}>
            {isExpanded ? '▼' : '▶'}
          </span>
        )}
        {!hasChildren && <span className="tree-leaf">•</span>}
        <span
          className={`tree-node-label ${isSelected ? 'selected' : ''}`}
          onClick={(e) => { e.stopPropagation(); onSelect?.(node); handleNodeClick(node); }}
          title={`${node.symbol.name}\n${node.symbol.file}:${node.symbol.line}`}
        >
          <span className={`node-kind kind-${node.symbol.kind}`}>
            {node.symbol.kind === 'function' ? 'ƒ' : node.symbol.kind === 'class' ? 'C' : 'T'}
          </span>
          <span className="node-name">{node.symbol.name}</span>
          {node.depth > 0 && (
            <span className="node-location" title={node.symbol.dep_file || node.symbol.file}>
              {node.symbol.dep_file ? `(${node.symbol.dep_file.split('/').pop()}:${node.symbol.line})` : ''}
            </span>
          )}
          {isCallback && getCallbackBadge(callbackType)}
        </span>
      </div>
      {hasChildren && isExpanded && (
        <div className="tree-children">
          {node.children.map((child) => (
            <TreeNode
              key={child.symbol.id}
              node={child}
              depth={depth + 1}
              onToggle={onToggle}
              expandedNodes={expandedNodes}
              showCallbacksOnly={showCallbacksOnly}
              highlightedCallback={highlightedCallback}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export const CallTreeView: React.FC<CallTreeViewProps> = ({
  symbolId,
  onNodeClick,
  onClose,
}) => {
  const [callTree, setCallTree] = useState<CallTreeNode | null>(null);
  const [treeText, setTreeText] = useState<string>('');
  const [direction, setDirection] = useState<'outgoing' | 'incoming'>('outgoing');
  const [maxDepth, setMaxDepth] = useState(10);
  const [loading, setLoading] = useState(true);
  const [expandedNodes, setExpandedNodes] = useState<Set<number>>(new Set());
  const [statistics, setStatistics] = useState<{ total_nodes: number; max_depth: number } | null>(null);
  const [showCallbacksOnly, setShowCallbacksOnly] = useState(false);
  const [selectedNode, setSelectedNode] = useState<CallTreeNode | null>(null);
  const [sourceSnippet, setSourceSnippet] = useState<SourceSnippet | null>(null);
  const [loadingSource, setLoadingSource] = useState(false);
  const [showDetail, setShowDetail] = useState(true);

  const loadCallTree = useCallback(async () => {
    setLoading(true);
    try {
      const data = await symbolApi.getCallTree(symbolId, direction, maxDepth);
      setCallTree(data.tree);
      setTreeText(data.tree_text);
      setStatistics(data.statistics);

      // 自动展开所有节点
      const allIds = new Set<number>();
      const collectIds = (node: any) => {
        if (node.children && node.children.length > 0) {
          allIds.add(node.symbol.id);
          node.children.forEach(collectIds);
        }
      };
      collectIds(data.tree);
      setExpandedNodes(allIds);
    } catch (err) {
      console.error('Load call tree error:', err);
    } finally {
      setLoading(false);
    }
  }, [symbolId, direction, maxDepth]);

  useEffect(() => {
    loadCallTree();
  }, [loadCallTree]);

  const handleToggle = (nodeId: number) => {
    setExpandedNodes(prev => {
      const next = new Set(prev);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  };

  const handleDirectionChange = (newDirection: 'outgoing' | 'incoming') => {
    setDirection(newDirection);
  };

  const handleDepthChange = (newDepth: number) => {
    setMaxDepth(newDepth);
  };

  const handleNodeClick = (node: CallTreeNode) => {
    onNodeClick?.(node);
  };

  const handleNodeSelect = async (node: CallTreeNode) => {
    setSelectedNode(node);
    setLoadingSource(true);
    setSourceSnippet(null);
    try {
      const source = await symbolApi.getSource(node.symbol.id, 8);
      setSourceSnippet(source);
    } catch (err) {
      console.error('Failed to load source:', err);
    } finally {
      setLoadingSource(false);
    }
  };

  const handleCloseDetail = () => {
    setSelectedNode(null);
    setSourceSnippet(null);
  };

  if (loading) {
    return (
      <div className="call-tree-view loading">
        <div className="loading-spinner" />
        <span>加载调用树...</span>
      </div>
    );
  }

  if (!callTree) {
    return (
      <div className="call-tree-view empty">
        <div className="empty-message">
          <p>暂无调用关系数据</p>
          <p className="hint">该符号可能没有函数调用关系，或调用的是外部库函数</p>
        </div>
      </div>
    );
  }

  return (
    <div className="call-tree-view">
      {/* 头部控制栏 */}
      <div className="tree-header">
        <div className="tree-title">
          <h4>
            {direction === 'outgoing' ? '📤 调用谁' : '📥 被谁调用'}
          </h4>
          <span className="root-symbol">{callTree.symbol.name}</span>
        </div>
        <div className="tree-controls">
          <div className="direction-toggle">
            <button
              className={direction === 'outgoing' ? 'active' : ''}
              onClick={() => handleDirectionChange('outgoing')}
              title="查看该函数调用的其他函数"
            >
              调用谁
            </button>
            <button
              className={direction === 'incoming' ? 'active' : ''}
              onClick={() => handleDirectionChange('incoming')}
              title="查看调用该函数的其他函数"
            >
              被谁调用
            </button>
          </div>
          <div className="depth-control">
            <label>深度:</label>
            <select value={maxDepth} onChange={(e) => handleDepthChange(Number(e.target.value))}>
              <option value={5}>5</option>
              <option value={10}>10</option>
              <option value={20}>20</option>
              <option value={30}>30</option>
              <option value={50}>50</option>
            </select>
          </div>
          <button className="btn-refresh" onClick={loadCallTree} title="刷新">
            ↻
          </button>
          <button
            className={`btn-callback-filter ${showCallbacksOnly ? 'active' : ''}`}
            onClick={() => setShowCallbacksOnly(!showCallbacksOnly)}
            title="只显示回调函数"
          >
            ↩ 回调
          </button>
        </div>
      </div>

      {/* 统计信息 */}
      {statistics && (
        <div className="tree-stats">
          <span>节点: {statistics.total_nodes}</span>
          <span>最大深度: {statistics.max_depth}</span>
          {showCallbacksOnly && <span className="callback-hint">回调过滤已启用</span>}
        </div>
      )}

      {/* 树形内容 + 详情面板 */}
      <div className="tree-main-content">
        {/* 树形内容 */}
        <div className="tree-content">
          {callTree.children.length === 0 ? (
            <div className="empty-tree">
              <p>没有找到{direction === 'outgoing' ? '调用的函数' : '调用该函数的函数'}</p>
              <p className="hint">该函数可能只调用了外部库函数（如 STL、Windows API 等）</p>
            </div>
          ) : (
            <>
              {/* 根节点 */}
              <div className="tree-node root-node" onClick={() => handleNodeSelect(callTree)}>
                <span className={`node-kind kind-${callTree.symbol.kind}`}>
                  {callTree.symbol.kind === 'function' ? 'ƒ' : callTree.symbol.kind === 'class' ? 'C' : 'T'}
                </span>
                <span className="node-name root-name">{callTree.symbol.name}</span>
                <span className="node-location">{callTree.symbol.file.split('/').pop()}:{callTree.symbol.line}</span>
              </div>
              {/* 子节点 */}
              {callTree.children.map((child) => (
                <TreeNode
                  key={child.symbol.id}
                  node={child}
                  depth={1}
                  onToggle={handleToggle}
                  expandedNodes={expandedNodes}
                  showCallbacksOnly={showCallbacksOnly}
                  onSelect={handleNodeSelect}
                  isSelected={selectedNode?.symbol.id === child.symbol.id}
                />
              ))}
            </>
          )}
        </div>

        {/* 右侧详情面板 */}
        {selectedNode && (
          <div className="detail-panel">
            <div className="detail-header">
              <div className="detail-title">
                <FileCode size={16} />
                <span>代码详情</span>
              </div>
              <button className="detail-close" onClick={handleCloseDetail} title="关闭">
                <X size={16} />
              </button>
            </div>

            <div className="detail-info">
              <div className="detail-symbol">
                <span className={`detail-kind kind-${selectedNode.symbol.kind}`}>
                  {selectedNode.symbol.kind === 'function' ? 'ƒ' : selectedNode.symbol.kind === 'class' ? 'C' : 'T'}
                </span>
                <span className="detail-name">{selectedNode.symbol.name}</span>
              </div>
              <div className="detail-meta">
                <span className="detail-file" title={selectedNode.symbol.file}>
                  {selectedNode.symbol.file.split('/').pop()}:{selectedNode.symbol.line}
                </span>
                {selectedNode.symbol.dep_file && (
                  <span className="detail-call-info">
                    {direction === 'outgoing' ? <ArrowRight size={12} /> : <ArrowLeft size={12} />}
                    调用位置: {selectedNode.symbol.dep_file.split('/').pop()}:{selectedNode.symbol.line}
                  </span>
                )}
              </div>
              {selectedNode.symbol.signature && (
                <div className="detail-signature">{selectedNode.symbol.signature}</div>
              )}
            </div>

            <div className="detail-source">
              {loadingSource ? (
                <div className="source-loading">
                  <div className="loading-spinner small" />
                  <span>加载代码...</span>
                </div>
              ) : sourceSnippet ? (
                <div className="source-code">
                  <div className="source-header">
                    <span className="source-file" title={sourceSnippet.file_path}>
                      {sourceSnippet.relative_path}
                    </span>
                    <span className="source-lines">
                      {sourceSnippet.target_line}/{sourceSnippet.total_lines}
                    </span>
                  </div>
                  <pre className="source-pre">
                    {sourceSnippet.snippet.map((line) => (
                      <div
                        key={line.line_number}
                        className={`source-line ${line.is_target ? 'target' : ''}`}
                      >
                        <span className="line-number">{line.line_number}</span>
                        <span className="line-content">{line.content || ' '}</span>
                      </div>
                    ))}
                  </pre>
                </div>
              ) : (
                <div className="source-error">无法加载源代码</div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* 文本格式的树（可复制） */}
      <details className="tree-text-section">
        <summary>树形文本（点击展开）</summary>
        <pre className="tree-text">{treeText}</pre>
      </details>
    </div>
  );
};
