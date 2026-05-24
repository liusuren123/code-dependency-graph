import React, { useEffect, useRef, useState, useCallback } from 'react';
import * as d3 from 'd3';
import { GraphNode, GraphEdge, graphApi } from '../api';

interface GraphViewProps {
  repositoryId?: number;
  layer?: string;
  onNodeClick?: (node: GraphNode) => void;
}

const LAYER_COLORS: Record<string, string> = {
  SDK: '#4ade80',
  LOGIC: '#38bdf8',
  BUSINESS: '#fb923c',
  UI: '#f472b6',
};

const KIND_COLORS: Record<string, string> = {
  function: '#4ade80',
  class: '#38bdf8',
  struct: '#a78bfa',
  enum: '#f87171',
  typedef: '#f472b6',
};

export const GraphView: React.FC<GraphViewProps> = ({
  repositoryId,
  layer,
  onNodeClick,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [graphData, setGraphData] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const [stats, setStats] = useState({ nodes: 0, edges: 0, filteredEdges: 0 });

  // Refs for graph state
  const simulationRef = useRef<d3.Simulation<any, any> | null>(null);
  const nodesRef = useRef<any[]>([]);
  const allEdgesRef = useRef<any[]>([]);
  const filteredEdgesRef = useRef<any[]>([]);
  const edgeWeightsRef = useRef<Map<string, number>>(new Map());

  // Refs for interaction state
  const transformRef = useRef({ x: 0, y: 0, k: 1 });
  const isDraggingNode = useRef(false);
  const isDraggingCanvas = useRef(false);
  const draggedNode = useRef<any>(null);
  const dragStartPos = useRef({ x: 0, y: 0 });
  const mousePos = useRef({ x: 0, y: 0 });
  const hoveredNodeRef = useRef<GraphNode | null>(null);
  const isDraggingRef = useRef(false);

  const [maxNodes, setMaxNodes] = useState(500);
  const [edgeTypeFilter, setEdgeTypeFilter] = useState<string>('all');
  const [minEdgeWeight, setMinEdgeWeight] = useState(0);

  // 加载图数据
  const loadGraphData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await graphApi.getGraphData({
        repository_id: repositoryId,
        layer,
        max_nodes: maxNodes,
      });
      setGraphData({ nodes: data.nodes, edges: data.edges });
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [repositoryId, layer, maxNodes]);

  useEffect(() => {
    loadGraphData();
  }, [loadGraphData]);

  // 世界坐标转屏幕坐标
  const worldToScreen = useCallback((wx: number, wy: number) => {
    const t = transformRef.current;
    return {
      x: wx * t.k + t.x,
      y: wy * t.k + t.y,
    };
  }, []);

  // 屏幕坐标转世界坐标
  const screenToWorld = useCallback((sx: number, sy: number) => {
    const t = transformRef.current;
    return {
      x: (sx - t.x) / t.k,
      y: (sy - t.y) / t.k,
    };
  }, []);

  // 渲染函数
  const render = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;

    const { nodes } = { nodes: nodesRef.current };
    const edges = filteredEdgesRef.current;
    const transform = transformRef.current;
    const hovered = hoveredNodeRef.current;
    const dpr = window.devicePixelRatio || 1;

    const width = canvas.width / dpr;
    const height = canvas.height / dpr;

    // 清空画布
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = '#0a0e17';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // 应用变换
    ctx.translate(transform.x * dpr, transform.y * dpr);
    ctx.scale(transform.k, transform.k);

    // 可见区域
    const viewX = -transform.x / transform.k;
    const viewY = -transform.y / transform.k;
    const viewW = width / transform.k;
    const viewH = height / transform.k;

    // 绘制边
    ctx.lineWidth = 1 / transform.k;
    for (const edge of edges) {
      const source = edge.source;
      const target = edge.target;
      if (!source.x || !source.y || !target.x || !target.y) continue;

      // 裁剪
      const margin = 50 / transform.k;
      const minX = Math.min(source.x, target.x) - margin;
      const maxX = Math.max(source.x, target.x) + margin;
      const minY = Math.min(source.y, target.y) - margin;
      const maxY = Math.max(source.y, target.y) + margin;
      if (maxX < viewX || minX > viewX + viewW || maxY < viewY || minY > viewY + viewH) continue;

      // 高亮
      const isHighlighted = hovered && (source.id === hovered.id || target.id === hovered.id);
      const isOther = hovered && !isHighlighted;

      ctx.beginPath();
      ctx.moveTo(source.x, source.y);
      ctx.lineTo(target.x, target.y);
      ctx.strokeStyle = isHighlighted ? '#f59e0b' : '#475569';
      ctx.globalAlpha = isOther ? 0.1 : isHighlighted ? 1 : 0.4;
      ctx.lineWidth = (isHighlighted ? 2 : 1) / transform.k;
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    // 绘制节点
    for (const node of nodes) {
      if (node.x === undefined || node.y === undefined) continue;

      const nodeSize = node.kind === 'function' ? 8 : 12;
      // 裁剪
      if (node.x + nodeSize < viewX - 50 || node.x - nodeSize > viewX + viewW + 50 ||
          node.y + nodeSize < viewY - 50 || node.y - nodeSize > viewY + viewH + 50) continue;

      const isHovered = hovered && node.id === hovered.id;
      const baseColor = KIND_COLORS[node.kind] || '#666';
      const layerColor = LAYER_COLORS[node.layer] || '#999';

      // 光晕
      if (isHovered) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, (nodeSize + 6) / transform.k, 0, Math.PI * 2);
        ctx.strokeStyle = '#f59e0b';
        ctx.lineWidth = 2 / transform.k;
        ctx.stroke();
      }

      // 节点圆形
      ctx.beginPath();
      ctx.arc(node.x, node.y, nodeSize / transform.k, 0, Math.PI * 2);
      ctx.fillStyle = baseColor;
      ctx.fill();
      ctx.strokeStyle = layerColor;
      ctx.lineWidth = 2 / transform.k;
      ctx.stroke();

      // 标签（缩放足够大时显示）
      if (transform.k > 0.4) {
        const fontSize = Math.max(11 / transform.k, 8);
        ctx.font = `${fontSize}px system-ui, sans-serif`;
        ctx.fillStyle = '#e2e8f0';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        const label = node.label?.length > 18 ? node.label.substring(0, 15) + '...' : (node.label || '');
        ctx.fillText(label, node.x + (nodeSize + 6) / transform.k, node.y);
      }
    }
  }, []);

  // 查找节点
  const findNodeAtPos = useCallback((wx: number, wy: number): any => {
    for (const node of nodesRef.current) {
      const nodeSize = (node.kind === 'function' ? 8 : 12) / transformRef.current.k;
      const dx = (node.x || 0) - wx;
      const dy = (node.y || 0) - wy;
      if (dx * dx + dy * dy < nodeSize * nodeSize) {
        return node;
      }
    }
    return null;
  }, []);

  // 设置 Canvas 尺寸
  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const resizeObserver = new ResizeObserver(() => {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = container.clientWidth * dpr;
      canvas.height = container.clientHeight * dpr;
      canvas.style.width = `${container.clientWidth}px`;
      canvas.style.height = `${container.clientHeight}px`;
      render();
    });

    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, [render]);

  // 初始化图
  useEffect(() => {
    if (!graphData || !canvasRef.current) return;

    if (simulationRef.current) {
      simulationRef.current.stop();
    }

    const canvas = canvasRef.current;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = canvas.clientWidth * dpr;
    canvas.height = canvas.clientHeight * dpr;

    // 初始化节点
    nodesRef.current = graphData.nodes.map((n, i) => ({
      ...n,
      x: n.x ?? 400 + (Math.random() - 0.5) * 600,
      y: n.y ?? 300 + (Math.random() - 0.5) * 400,
    }));

    // 创建映射
    const nodeById = new Map(nodesRef.current.map(n => [n.id, n]));

    // 初始化边
    allEdgesRef.current = graphData.edges.map(e => {
      const sourceId = typeof e.source === 'string' ? e.source : (e.source as any).id;
      const targetId = typeof e.target === 'string' ? e.target : (e.target as any).id;
      return {
        ...e,
        source: nodeById.get(sourceId) || e.source,
        target: nodeById.get(targetId) || e.target,
      };
    }).filter(e => e.source && e.target);

    // 计算权重
    const weights = new Map<string, number>();
    for (const edge of allEdgesRef.current) {
      const sid = typeof edge.source === 'object' ? edge.source.id : edge.source;
      const tid = typeof edge.target === 'object' ? edge.target.id : edge.target;
      weights.set(sid, (weights.get(sid) || 0) + 1);
      weights.set(tid, (weights.get(tid) || 0) + 1);
    }
    edgeWeightsRef.current = weights;

    applyEdgeFilters();

    // 力模拟
    const simulation = d3.forceSimulation(nodesRef.current)
      .force('link', d3.forceLink(allEdgesRef.current).id((d: any) => d.id).distance(100).strength(0.2))
      .force('charge', d3.forceManyBody().strength(-200).distanceMax(400))
      .force('center', d3.forceCenter(canvas.width / dpr / 2, canvas.height / dpr / 2))
      .force('collision', d3.forceCollide().radius(25))
      .alphaDecay(0.02)
      .velocityDecay(0.3);

    simulation.on('tick', () => {
      render();
    });

    simulation.on('end', () => {
      render();
    });

    simulationRef.current = simulation;

    return () => {
      simulation.stop();
    };
  }, [graphData, render]);

  // 边过滤
  const applyEdgeFilters = useCallback(() => {
    let filtered = allEdgesRef.current;

    if (edgeTypeFilter !== 'all') {
      filtered = filtered.filter(e => e.type === edgeTypeFilter);
    }

    if (minEdgeWeight > 0) {
      filtered = filtered.filter(e => {
        const sid = typeof e.source === 'object' ? e.source.id : e.source;
        const tid = typeof e.target === 'object' ? e.target.id : e.target;
        return (edgeWeightsRef.current.get(sid) || 0) >= minEdgeWeight ||
               (edgeWeightsRef.current.get(tid) || 0) >= minEdgeWeight;
      });
    }

    filteredEdgesRef.current = filtered;
    setStats({
      nodes: nodesRef.current.length,
      edges: allEdgesRef.current.length,
      filteredEdges: filtered.length,
    });
  }, [edgeTypeFilter, minEdgeWeight]);

  useEffect(() => {
    applyEdgeFilters();
  }, [edgeTypeFilter, minEdgeWeight, applyEdgeFilters]);

  // 鼠标事件
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    let dragMode: 'none' | 'node' | 'canvas' = 'none';
    let lastMouseWorld = { x: 0, y: 0 };

    const getWorldPos = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const sx = (e.clientX - rect.left);
      const sy = (e.clientY - rect.top);
      return {
        x: (sx - transformRef.current.x) / transformRef.current.k,
        y: (sy - transformRef.current.y) / transformRef.current.k,
      };
    };

    const onMouseDown = (e: MouseEvent) => {
      const world = getWorldPos(e);
      lastMouseWorld = world;
      dragStartPos.current = { x: e.clientX, y: e.clientY };

      const node = findNodeAtPos(world.x, world.y);
      if (node) {
        dragMode = 'node';
        isDraggingNode.current = true;
        draggedNode.current = node;
        node.fx = node.x;
        node.fy = node.y;
        simulationRef.current?.alphaTarget(0.2).restart();
      } else {
        dragMode = 'canvas';
        isDraggingRef.current = true;
      }
    };

    const onMouseMove = (e: MouseEvent) => {
      const world = getWorldPos(e);
      mousePos.current = world;

      if (dragMode === 'node' && draggedNode.current) {
        draggedNode.current.fx = world.x;
        draggedNode.current.fy = world.y;
      } else if (dragMode === 'canvas' && isDraggingRef.current) {
        const dx = e.clientX - dragStartPos.current.x;
        const dy = e.clientY - dragStartPos.current.y;
        transformRef.current.x += dx;
        transformRef.current.y += dy;
        dragStartPos.current = { x: e.clientX, y: e.clientY };
        render();
      } else {
        // 悬停检测
        const node = findNodeAtPos(world.x, world.y);
        if (node !== hoveredNodeRef.current) {
          hoveredNodeRef.current = node || null;
          setHoveredNode(node || null);
          canvas.style.cursor = node ? 'pointer' : 'grab';
          render();
        }
      }
    };

    const onMouseUp = (e: MouseEvent) => {
      if (dragMode === 'node' && draggedNode.current) {
        draggedNode.current.fx = null;
        draggedNode.current.fy = null;
        simulationRef.current?.alphaTarget(0);
      }
      dragMode = 'none';
      isDraggingNode.current = false;
      isDraggingRef.current = false;
      draggedNode.current = null;
    };

    const onClick = (e: MouseEvent) => {
      if (dragMode === 'node' || dragMode === 'canvas') return;
      const world = getWorldPos(e);
      const node = findNodeAtPos(world.x, world.y);
      if (node) {
        onNodeClick?.(node);
      }
    };

    const onDoubleClick = () => {
      // 重置视图
      transformRef.current = { x: 0, y: 0, k: 1 };
      simulationRef.current?.alpha(1).restart();
    };

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;

      const zoomFactor = e.deltaY > 0 ? 0.85 : 1.15;
      const newK = Math.max(0.1, Math.min(5, transformRef.current.k * zoomFactor));

      transformRef.current.x = mx - (mx - transformRef.current.x) * (newK / transformRef.current.k);
      transformRef.current.y = my - (my - transformRef.current.y) * (newK / transformRef.current.k);
      transformRef.current.k = newK;
      render();
    };

    canvas.addEventListener('mousedown', onMouseDown);
    canvas.addEventListener('mousemove', onMouseMove);
    canvas.addEventListener('mouseup', onMouseUp);
    canvas.addEventListener('click', onClick);
    canvas.addEventListener('dblclick', onDoubleClick);
    canvas.addEventListener('wheel', onWheel, { passive: false });

    return () => {
      canvas.removeEventListener('mousedown', onMouseDown);
      canvas.removeEventListener('mousemove', onMouseMove);
      canvas.removeEventListener('mouseup', onMouseUp);
      canvas.removeEventListener('click', onClick);
      canvas.removeEventListener('dblclick', onDoubleClick);
      canvas.removeEventListener('wheel', onWheel);
    };
  }, [findNodeAtPos, onNodeClick, render]);

  return (
    <div ref={containerRef} className="graph-container" style={{ width: '100%', height: '100%', position: 'relative' }}>
      {loading && (
        <div className="loading-overlay">
          <div className="loading-spinner" />
          <span>加载中...</span>
        </div>
      )}

      {error && (
        <div className="error-overlay">
          <span>错误: {error}</span>
          <button onClick={loadGraphData}>重试</button>
        </div>
      )}

      <canvas ref={canvasRef} style={{ display: 'block', cursor: 'grab' }} />

      {/* Tooltip */}
      {hoveredNode && (
        <div
          style={{
            position: 'fixed',
            left: mousePos.current.x + 20,
            top: mousePos.current.y + 20,
            background: 'rgba(15,23,42,0.95)',
            border: '1px solid #1e293b',
            borderRadius: '6px',
            padding: '10px 14px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
            maxWidth: '320px',
            zIndex: 1000,
            pointerEvents: 'none',
          }}
        >
          <div style={{ fontWeight: 'bold', marginBottom: '6px', color: '#e2e8f0', fontSize: '13px' }}>
            {hoveredNode.label}
          </div>
          <div style={{ fontSize: '11px', color: '#94a3b8', display: 'flex', flexDirection: 'column', gap: '3px' }}>
            <div><span style={{ color: '#64748b' }}>类型:</span> {hoveredNode.kind} <span style={{ color: '#475569' }}>|</span> <span style={{ color: KIND_COLORS[hoveredNode.kind] }}>{hoveredNode.kind}</span></div>
            <div><span style={{ color: '#64748b' }}>层级:</span> <span style={{ color: LAYER_COLORS[hoveredNode.layer] }}>{hoveredNode.layer}</span></div>
            {hoveredNode.namespace && <div><span style={{ color: '#64748b' }}>命名空间:</span> {hoveredNode.namespace}</div>}
            <div style={{ marginTop: '4px', color: '#64748b', wordBreak: 'break-all', fontSize: '10px' }}>
              {hoveredNode.file}:{hoveredNode.line}
            </div>
          </div>
        </div>
      )}

      {/* 控制面板 */}
      <div style={{
        position: 'absolute',
        top: '16px',
        right: '16px',
        background: 'rgba(15,23,42,0.92)',
        border: '1px solid #1e293b',
        borderRadius: '8px',
        padding: '14px',
        fontSize: '12px',
        color: '#e2e8f0',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
        minWidth: '170px',
      }}>
        <div style={{ fontWeight: 'bold', fontSize: '13px', marginBottom: '4px' }}>统计</div>
        <div>节点: <span style={{ color: '#38bdf8' }}>{stats.nodes}</span></div>
        <div>边: <span style={{ color: '#38bdf8' }}>{stats.filteredEdges}</span> <span style={{ color: '#475569', fontSize: '10px' }}>/ {stats.edges}</span></div>

        <div style={{ borderTop: '1px solid #1e293b', paddingTop: '10px' }}>
          <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>节点上限</label>
          <select
            value={maxNodes}
            onChange={e => setMaxNodes(Number(e.target.value))}
            onBlur={loadGraphData}
            style={{ width: '100%', background: '#1e293b', color: '#e2e8f0', border: '1px solid #334155', borderRadius: '4px', padding: '4px', fontSize: '12px' }}
          >
            {[100, 200, 500, 1000, 2000].map(v => <option key={v} value={v}>{v}</option>)}
          </select>
        </div>

        <div>
          <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>边类型</label>
          <select
            value={edgeTypeFilter}
            onChange={e => setEdgeTypeFilter(e.target.value)}
            style={{ width: '100%', background: '#1e293b', color: '#e2e8f0', border: '1px solid #334155', borderRadius: '4px', padding: '4px', fontSize: '12px' }}
          >
            <option value="all">全部</option>
            <option value="calls">函数调用</option>
            <option value="include">include</option>
            <option value="inheritance">继承</option>
            <option value="composition">组合</option>
          </select>
        </div>

        <div>
          <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>最小连接度</label>
          <select
            value={minEdgeWeight}
            onChange={e => setMinEdgeWeight(Number(e.target.value))}
            style={{ width: '100%', background: '#1e293b', color: '#e2e8f0', border: '1px solid #334155', borderRadius: '4px', padding: '4px', fontSize: '12px' }}
          >
            {[0, 2, 5, 10, 20].map(v => <option key={v} value={v}>{v === 0 ? '全部' : `${v}+`}</option>)}
          </select>
        </div>

        <div style={{ fontSize: '10px', color: '#475569', borderTop: '1px solid #1e293b', paddingTop: '8px' }}>
          拖拽空白区域移动视图 | 滚轮缩放 | 双击重置
        </div>
      </div>

      {/* 图例 */}
      <div style={{
        position: 'absolute',
        bottom: '16px',
        left: '16px',
        background: 'rgba(15,23,42,0.92)',
        border: '1px solid #1e293b',
        borderRadius: '8px',
        padding: '12px',
        fontSize: '11px',
        color: '#e2e8f0',
      }}>
        <div style={{ fontWeight: 'bold', marginBottom: '8px', fontSize: '12px' }}>图例</div>
        <div style={{ marginBottom: '6px' }}>
          <strong style={{ color: '#64748b' }}>层级:</strong>
          {Object.entries(LAYER_COLORS).map(([l, c]) => (
            <span key={l} style={{ marginLeft: '10px' }}>
              <span style={{ display: 'inline-block', width: '9px', height: '9px', background: c, borderRadius: '50%', marginRight: '3px' }} />
              {l}
            </span>
          ))}
        </div>
        <div>
          <strong style={{ color: '#64748b' }}>类型:</strong>
          {Object.entries(KIND_COLORS).map(([k, c]) => (
            <span key={k} style={{ marginLeft: '10px' }}>
              <span style={{ display: 'inline-block', width: '8px', height: '8px', background: c, borderRadius: k === 'function' ? '50%' : '2px' }} />
              {k}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
};
