import React, { useState, useCallback } from 'react';
import { Search, ChevronLeft, ChevronRight as ChevronRightIcon, Hash, Braces, Cpu, Type, Variable, CircleDot } from 'lucide-react';
import { symbolApi as api, Symbol } from '../api';

interface SearchPanelProps {
  onSymbolSelect?: (symbol: Symbol) => void;
  repositoryId?: number;
}

const KINDS = ['function', 'class', 'struct', 'enum', 'typedef'];
const LAYERS = ['SDK', 'LOGIC', 'BUSINESS', 'UI'];

const KIND_ICON: Record<string, React.ReactNode> = {
  function: <CircleDot size={12} />,
  method: <CircleDot size={12} />,
  class: <Braces size={12} />,
  struct: <Cpu size={12} />,
  enum: <Hash size={12} />,
  typedef: <Type size={12} />,
  variable: <Variable size={12} />,
};

export const SearchPanel: React.FC<SearchPanelProps> = ({
  onSymbolSelect,
  repositoryId,
}) => {
  const [keyword, setKeyword] = useState('');
  const [layer, setLayer] = useState<string>('');
  const [kind, setKind] = useState<string>('');
  const [results, setResults] = useState<Symbol[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const handleSearch = useCallback(async (p = 1) => {
    if (!keyword && !layer && !kind) {
      setResults([]);
      setTotal(0);
      return;
    }

    setLoading(true);
    setSearched(true);
    try {
      const data = await api.search({
        keyword: keyword || undefined,
        layer: layer || undefined,
        kind: kind || undefined,
        repository_id: repositoryId,
        page: p,
        page_size: pageSize,
      });
      setResults(data.symbols);
      setTotal(data.total);
      setPage(p);
    } catch (err) {
      console.error('Search error:', err);
    } finally {
      setLoading(false);
    }
  }, [keyword, layer, kind, repositoryId, pageSize]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch(1);
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="sp-root">
      {/* Search input */}
      <div className="sp-search-row">
        <Search size={14} className="sp-search-icon" />
        <input
          type="text"
          value={keyword}
          onChange={e => setKeyword(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Search symbols..."
          className="sp-search-input"
        />
        <button onClick={() => handleSearch(1)} className="sp-search-btn">
          <Search size={13} />
        </button>
      </div>

      {/* Filters */}
      <div className="sp-filters">
        <select value={layer} onChange={e => setLayer(e.target.value)} className="sp-select">
          <option value="">All layers</option>
          {LAYERS.map(l => (
            <option key={l} value={l}>{l}</option>
          ))}
        </select>

        <select value={kind} onChange={e => setKind(e.target.value)} className="sp-select">
          <option value="">All kinds</option>
          {KINDS.map(k => (
            <option key={k} value={k}>{k}</option>
          ))}
        </select>
      </div>

      {/* Results */}
      <div className="sp-results">
        {loading && (
          <div className="sp-loading">
            <div className="sp-spinner" />
            Searching...
          </div>
        )}

        {!loading && searched && results.length === 0 && (
          <div className="sp-empty">No matching symbols found</div>
        )}

        {!searched && (
          <div className="sp-empty">Type a keyword and press Enter</div>
        )}

        {results.length > 0 && (
          <>
            <div className="sp-results-header">
              <span>{total} results</span>
              <span>Page {page}/{totalPages}</span>
            </div>

            {results.map(symbol => {
              const icon = KIND_ICON[symbol.kind] || <CircleDot size={12} />;
              return (
                <div
                  key={symbol.id}
                  className="sp-result"
                  onClick={() => onSymbolSelect?.(symbol)}
                >
                  <div className="sp-result-top">
                    <span className={`sp-kind-icon kind-${symbol.kind}`}>
                      {icon}
                    </span>
                    <span className="sp-result-name">{symbol.name}</span>
                  </div>
                  {symbol.signature && (
                    <div className="sp-result-sig">{symbol.signature}</div>
                  )}
                  <div className="sp-result-meta">
                    <span>{symbol.namespace || '—'}</span>
                    <span>{symbol.file_path.split('/').pop()}:{symbol.line_number}</span>
                  </div>
                </div>
              );
            })}

            {totalPages > 1 && (
              <div className="sp-pagination">
                <button
                  disabled={page <= 1}
                  onClick={() => handleSearch(page - 1)}
                  className="sp-page-btn"
                >
                  <ChevronLeft size={14} />
                </button>
                <span className="sp-page-info">{page} / {totalPages}</span>
                <button
                  disabled={page >= totalPages}
                  onClick={() => handleSearch(page + 1)}
                  className="sp-page-btn"
                >
                  <ChevronRightIcon size={14} />
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};
