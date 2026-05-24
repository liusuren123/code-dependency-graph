import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Info, ArrowLeftRight, GitFork, Type, AlertTriangle, Network,
  ChevronRight, ChevronDown, FileCode, Layers, Code2, Zap, FileText
} from 'lucide-react';
import { Symbol, symbolApi, api } from '../api';
import styles from './DetailPanel.module.css';

type TabKey = 'info' | 'source' | 'deps' | 'branches' | 'types' | 'errors' | 'hierarchy';

interface DetailPanelProps {
  symbol: Symbol | null;
  onClose?: () => void;
}

export const DetailPanel: React.FC<DetailPanelProps> = ({ symbol }) => {
  const [activeTab, setActiveTab] = useState<TabKey>('source');
  const [panelWidth, setPanelWidth] = useState(420);
  const [isResizing, setIsResizing] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);

    const startX = e.clientX;
    const startWidth = panelWidth;

    const handleMouseMove = (e: MouseEvent) => {
      const delta = startX - e.clientX;
      const newWidth = Math.min(800, Math.max(280, startWidth + delta));
      setPanelWidth(newWidth);
    };

    const handleMouseUp = () => {
      setIsResizing(false);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, [panelWidth]);

  if (!symbol) {
    return (
      <div className={styles.detailPanel}>
        <div className={styles.emptyState}>
          <Info size={32} className={styles.emptyIcon} />
          <p>Select a symbol to view details</p>
        </div>
      </div>
    );
  }

  const tabs: { key: TabKey; label: string; icon: React.ReactNode }[] = [
    { key: 'source', label: 'Source', icon: <FileText size={13} /> },
    { key: 'info', label: 'Info', icon: <Info size={13} /> },
    { key: 'deps', label: 'Deps', icon: <ArrowLeftRight size={13} /> },
    { key: 'branches', label: 'Branches', icon: <GitFork size={13} /> },
    { key: 'types', label: 'Types', icon: <Type size={13} /> },
    { key: 'errors', label: 'Errors', icon: <AlertTriangle size={13} /> },
    { key: 'hierarchy', label: 'Hierarchy', icon: <Network size={13} /> },
  ];

  return (
    <div
      ref={panelRef}
      className={`${styles.detailPanel} ${isResizing ? styles.resizing : ''}`}
      style={{ width: panelWidth }}
    >
      <div className={styles.resizeHandle} onMouseDown={handleMouseDown} />

      <div className={styles.header}>
        <div className={styles.headerInfo}>
          <span className={styles.kindBadge}>{symbol.kind}</span>
          <span className={styles.symbolName} title={symbol.name}>{symbol.name}</span>
        </div>
        <div className={styles.headerMeta}>
          <FileCode size={12} />
          <span className={styles.filePath} title={symbol.file_path}>
            {symbol.file_path.split(/[\\/]/).slice(-2).join('/')}:{symbol.line_number}
          </span>
        </div>
        {symbol.signature && (
          <code className={styles.signature}>{symbol.signature}</code>
        )}
      </div>

      <div className={styles.tabBar}>
        {tabs.map(tab => (
          <button
            key={tab.key}
            className={`${styles.tab} ${activeTab === tab.key ? styles.tabActive : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      <div className={styles.tabContent}>
        {activeTab === 'source' && <SourceTab symbol={symbol} />}
        {activeTab === 'info' && <InfoTab symbol={symbol} />}
        {activeTab === 'deps' && <DepsTab symbolId={symbol.id} />}
        {activeTab === 'branches' && <BranchesTab symbolId={symbol.id} />}
        {activeTab === 'types' && <TypesTab symbolId={symbol.id} />}
        {activeTab === 'errors' && <ErrorsTab symbolId={symbol.id} />}
        {activeTab === 'hierarchy' && <HierarchyTab symbolId={symbol.id} />}
      </div>
    </div>
  );
};

/* === Source Tab === */
const SourceTab: React.FC<{ symbol: Symbol }> = ({ symbol }) => {
  const [sourceData, setSourceData] = useState<{
    file_path: string;
    relative_path: string;
    target_line: number;
    total_lines: number;
    snippet: Array<{ line_number: number; content: string; is_target: boolean }>;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    symbolApi.getSource(symbol.id, 15)
      .then(data => {
        setSourceData(data);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message || 'Failed to load source');
        setLoading(false);
      });
  }, [symbol.id]);

  if (loading) return <div className={styles.loading}>Loading source...</div>;
  if (error) return <div className={styles.error}>{error}</div>;
  if (!sourceData) return <div className={styles.emptyText}>No source available</div>;

  return (
    <div className={styles.sourceTab}>
      <div className={styles.sourceHeader}>
        <span className={styles.sourceFile} title={sourceData.file_path}>
          {sourceData.relative_path.split(/[\\/]/).slice(-2).join('/')}
        </span>
        <span className={styles.sourceLines}>
          {sourceData.target_line}/{sourceData.total_lines}
        </span>
      </div>
      <pre className={styles.sourcePre}>
        {sourceData.snippet.map((line) => (
          <div
            key={line.line_number}
            className={`${styles.sourceLine} ${line.is_target ? styles.targetLine : ''}`}
          >
            <span className={styles.lineNumber}>{line.line_number}</span>
            <span className={styles.lineContent}>{line.content || ' '}</span>
          </div>
        ))}
      </pre>
    </div>
  );
};

/* === Info Tab === */
const InfoTab: React.FC<{ symbol: Symbol }> = ({ symbol }) => (
  <div className={styles.infoTab}>
    <div className={styles.infoRow}>
      <span className={styles.infoLabel}>Name</span>
      <span className={styles.infoValue}>{symbol.name}</span>
    </div>
    <div className={styles.infoRow}>
      <span className={styles.infoLabel}>Kind</span>
      <span className={styles.infoValue}>{symbol.kind}</span>
    </div>
    {symbol.return_type && (
      <div className={styles.infoRow}>
        <span className={styles.infoLabel}>Return</span>
        <code className={styles.infoCode}>{symbol.return_type}</code>
      </div>
    )}
    {symbol.namespace && (
      <div className={styles.infoRow}>
        <span className={styles.infoLabel}>Namespace</span>
        <span className={styles.infoValue}>{symbol.namespace}</span>
      </div>
    )}
    <div className={styles.infoRow}>
      <span className={styles.infoLabel}>File</span>
      <span className={styles.infoValue} title={symbol.file_path}>{symbol.file_path}</span>
    </div>
    <div className={styles.infoRow}>
      <span className={styles.infoLabel}>Line</span>
      <span className={styles.infoValue}>{symbol.line_number}</span>
    </div>
  </div>
);

/* === Deps Tab === */
const DepsTab: React.FC<{ symbolId: number }> = ({ symbolId }) => {
  const [deps, setDeps] = useState<{ incoming: any[]; outgoing: any[] } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    symbolApi.getDetail(symbolId)
      .then(data => setDeps(data.dependencies))
      .catch(() => setDeps(null))
      .finally(() => setLoading(false));
  }, [symbolId]);

  if (loading) return <div className={styles.loading}>Loading...</div>;
  if (!deps) return <div className={styles.error}>Failed to load dependencies</div>;

  return (
    <div className={styles.depsTab}>
      <div className={styles.section}>
        <h4 className={styles.sectionTitle}><ChevronRight size={14} /> Outgoing ({deps.outgoing.length})</h4>
        {deps.outgoing.length === 0 ? <p className={styles.emptyText}>No outgoing dependencies</p> : (
          deps.outgoing.map((d, i) => (
            <div key={i} className={styles.depItem}>
              <span className={styles.depType}>{d.dependency_type}</span>
              <span className={styles.depName}>{d.target_name || d.target_symbol_id}</span>
            </div>
          ))
        )}
      </div>
      <div className={styles.section}>
        <h4 className={styles.sectionTitle}><ChevronDown size={14} /> Incoming ({deps.incoming.length})</h4>
        {deps.incoming.length === 0 ? <p className={styles.emptyText}>No incoming dependencies</p> : (
          deps.incoming.map((d, i) => (
            <div key={i} className={styles.depItem}>
              <span className={styles.depType}>{d.dependency_type}</span>
              <span className={styles.depName}>{d.source_name || d.source_symbol_id}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

/* === Branches Tab === */
const BranchesTab: React.FC<{ symbolId: number }> = ({ symbolId }) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/symbols/${symbolId}/branch-paths`)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [symbolId]);

  if (loading) return <div className={styles.loading}>Loading...</div>;
  if (!data) return <div className={styles.emptyText}>No branch data</div>;

  return (
    <div className={styles.branchesTab}>
      {data.unconditional_calls?.length > 0 && (
        <div className={styles.section}>
          <h4 className={styles.sectionTitle}><Zap size={14} /> Unconditional ({data.unconditional_calls.length})</h4>
          {data.unconditional_calls.map((c: any, i: number) => (
            <div key={i} className={styles.depItem}>
              <Code2 size={12} className={styles.itemIcon} />
              <span className={styles.depName}>{c.name}</span>
              <span className={styles.itemLine}>:{c.line}</span>
            </div>
          ))}
        </div>
      )}
      {data.branch_groups?.map((bg: any, i: number) => (
        <div key={i} className={styles.section}>
          <h4 className={styles.sectionTitle}>
            <GitFork size={14} />
            <span className={styles.branchType}>{bg.branch_type}</span>
            {bg.branch_condition && (
              <code className={styles.branchCondition}>{bg.branch_condition}</code>
            )}
            <span className={styles.branchCount}>({bg.calls.length})</span>
          </h4>
          {bg.calls.map((c: any, j: number) => (
            <div key={j} className={styles.depItem}>
              <Code2 size={12} className={styles.itemIcon} />
              <span className={styles.depName}>{c.name}</span>
              <span className={styles.itemLine}>:{c.line}</span>
            </div>
          ))}
        </div>
      ))}
      {!data.unconditional_calls?.length && !data.branch_groups?.length && (
        <p className={styles.emptyText}>No branch analysis available</p>
      )}
    </div>
  );
};

/* === Types Tab === */
const TypesTab: React.FC<{ symbolId: number }> = ({ symbolId }) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/symbols/${symbolId}/type-chain`)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [symbolId]);

  if (loading) return <div className={styles.loading}>Loading...</div>;
  if (!data) return <div className={styles.emptyText}>No type data</div>;

  return (
    <div className={styles.typesTab}>
      <div className={styles.section}>
        <h4 className={styles.sectionTitle}><ChevronRight size={14} /> Type Inflow</h4>
        {(data.inflow_types || []).length === 0 ? <p className={styles.emptyText}>No inflow types</p> : (
          (data.inflow_types || []).map((t: any, i: number) => (
            <div key={i} className={styles.typeItem}>
              <code className={styles.typeCode}>{t.type_name}</code>
            </div>
          ))
        )}
      </div>
      <div className={styles.section}>
        <h4 className={styles.sectionTitle}><ChevronDown size={14} /> Type Outflow</h4>
        {(data.outflow_types || []).length === 0 ? <p className={styles.emptyText}>No outflow types</p> : (
          (data.outflow_types || []).map((t: any, i: number) => (
            <div key={i} className={styles.typeItem}>
              <code className={styles.typeCode}>{t.type_name}</code>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

/* === Errors Tab === */
const ErrorsTab: React.FC<{ symbolId: number }> = ({ symbolId }) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/symbols/${symbolId}/error-paths`)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [symbolId]);

  if (loading) return <div className={styles.loading}>Loading...</div>;
  if (!data) return <div className={styles.emptyText}>No error path data</div>;

  return (
    <div className={styles.errorsTab}>
      {data.error_paths?.map((ep: any, i: number) => (
        <div key={i} className={styles.errorPathItem}>
          <div className={styles.errorPathHeader}>
            <span className={`${styles.errorTypeBadge} ${styles[`errorType_${ep.error_type}`]}`}>
              {ep.error_type === 'try_block' ? 'try' : ep.error_type === 'catch_handler' ? 'catch' : 'throw'}
            </span>
            <span className={styles.errorLine}>Line {ep.line_number}</span>
          </div>
          {ep.caught_type && <code className={styles.errorDetail}>catches: {ep.caught_type}</code>}
          {ep.caught_types && ep.caught_types.length > 0 && (
            <div className={styles.errorCaughtTypes}>
              {JSON.parse(typeof ep.caught_types === 'string' ? ep.caught_types : '[]').map((ct: string, j: number) => (
                <code key={j} className={styles.errorCaughtType}>{ct}</code>
              ))}
            </div>
          )}
          {ep.thrown_expression && <code className={styles.errorDetail}>throws: {ep.thrown_expression}</code>}
        </div>
      ))}
      {data.calls_with_error_context?.length > 0 && (
        <div className={styles.section}>
          <h4 className={styles.sectionTitle}>Calls in Error Context</h4>
          {data.calls_with_error_context.map((c: any, i: number) => (
            <div key={i} className={styles.depItem}>
              <span className={`${styles.errorCtxBadge} ${c.error_context === 'try_protected' ? styles.tryBadge : styles.catchBadge}`}>
                {c.error_context}
              </span>
              <span className={styles.depName}>{c.target_name}</span>
              <span className={styles.itemLine}>:{c.source_line}</span>
            </div>
          ))}
        </div>
      )}
      {(!data.error_paths || data.error_paths.length === 0) && (
        <p className={styles.emptyText}>No error handling paths found</p>
      )}
    </div>
  );
};

/* === Hierarchy Tab === */
const HierarchyTab: React.FC<{ symbolId: number }> = ({ symbolId }) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/symbols/${symbolId}/hierarchy`)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [symbolId]);

  if (loading) return <div className={styles.loading}>Loading...</div>;
  if (!data) return <div className={styles.emptyText}>No hierarchy data</div>;

  return (
    <div className={styles.hierarchyTab}>
      <div className={styles.section}>
        <h4 className={styles.sectionTitle}><Layers size={14} /> Base Classes</h4>
        {(!data.base_classes || data.base_classes.length === 0) ? (
          <p className={styles.emptyText}>No base classes</p>
        ) : (
          data.base_classes.map((c: any, i: number) => (
            <div key={i} className={styles.depItem}>
              <Network size={12} className={styles.itemIcon} />
              <span className={styles.depName}>{c.name || c.target_name}</span>
            </div>
          ))
        )}
      </div>
      <div className={styles.section}>
        <h4 className={styles.sectionTitle}><Layers size={14} /> Derived Classes</h4>
        {(!data.derived_classes || data.derived_classes.length === 0) ? (
          <p className={styles.emptyText}>No derived classes</p>
        ) : (
          data.derived_classes.map((c: any, i: number) => (
            <div key={i} className={styles.depItem}>
              <Network size={12} className={styles.itemIcon} />
              <span className={styles.depName}>{c.name || c.source_name}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
