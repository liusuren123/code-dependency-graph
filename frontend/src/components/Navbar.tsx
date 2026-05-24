import React, { useState, useCallback, useRef, useEffect } from 'react';
import { GitBranch, Plus, Moon, Sun, Search, X, Database } from 'lucide-react';
import { Repository, Symbol, symbolApi } from '../api';
import styles from './Navbar.module.css';

interface NavbarProps {
  theme: 'dark' | 'light';
  onToggleTheme: () => void;
  selectedRepo: Repository | null;
  onOpenRepoManager: () => void;
  onSymbolSelect: (symbol: Symbol) => void;
  onToggleSidebar: () => void;
  onToggleDetail: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  theme, onToggleTheme, selectedRepo, onOpenRepoManager,
  onSymbolSelect, onToggleSidebar, onToggleDetail,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Symbol[]>([]);
  const [showSearch, setShowSearch] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === '/' && !e.ctrlKey && !e.metaKey && document.activeElement?.tagName !== 'INPUT') {
        e.preventDefault();
        inputRef.current?.focus();
        setShowSearch(true);
      }
      if (e.key === 'Escape') setShowSearch(false);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  useEffect(() => {
    if (!searchQuery.trim()) { setSearchResults([]); return; }
    const timer = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const result = await symbolApi.search({ keyword: searchQuery, page_size: 8 });
        setSearchResults(result.symbols);
      } catch { setSearchResults([]); }
      finally { setSearchLoading(false); }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowSearch(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleSelect = useCallback((sym: Symbol) => {
    onSymbolSelect(sym);
    setShowSearch(false);
    setSearchQuery('');
  }, [onSymbolSelect]);

  return (
    <div className={styles.navbar}>
      <div className={styles.navLeft}>
        <div className={styles.logo}>
          <Database size={20} className={styles.logoIcon} />
          <span className={styles.logoText}>CodeGraph</span>
        </div>
        {selectedRepo && (
          <div className={styles.repoIndicator}>
            <GitBranch size={14} />
            <span>{selectedRepo.name}</span>
            <span className={styles.repoLayer} style={{ color: `var(--layer-${selectedRepo.layer.toLowerCase()})` }}>
              {selectedRepo.layer}
            </span>
          </div>
        )}
      </div>

      <div className={styles.navCenter} ref={searchRef}>
        <div className={`${styles.searchBox} ${showSearch ? styles.searchBoxActive : ''}`}>
          <Search size={16} className={styles.searchIcon} />
          <input
            ref={inputRef}
            type="text"
            placeholder="搜索符号... ( / )"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onFocus={() => setShowSearch(true)}
            className={styles.searchInput}
          />
          {searchQuery && (
            <button className={styles.searchClear} onClick={() => { setSearchQuery(''); setSearchResults([]); }}>
              <X size={14} />
            </button>
          )}
        </div>
        {showSearch && (searchQuery || searchResults.length > 0) && (
          <div className={styles.searchDropdown}>
            {searchLoading && <div className={styles.searchLoading}>搜索中...</div>}
            {!searchLoading && searchResults.length === 0 && searchQuery && (
              <div className={styles.searchEmpty}>未找到匹配符号</div>
            )}
            {searchResults.map(sym => (
              <button key={sym.id} className={styles.searchResult} onClick={() => handleSelect(sym)}>
                <span className={styles.resultKind}>{sym.kind}</span>
                <span className={styles.resultName}>{sym.name}</span>
                <span className={styles.resultFile}>{sym.file_path.split(/[\\/]/).pop()}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className={styles.navRight}>
        <button className={styles.navBtn} onClick={onToggleSidebar} title="切换侧边栏 (Ctrl+B)">
          侧栏
        </button>
        <button className={styles.navBtn} onClick={onToggleDetail} title="切换详情面板">
          详情
        </button>
        <button className={styles.navBtnPrimary} onClick={onOpenRepoManager}>
          <Plus size={16} />
          仓库管理
        </button>
        <button className={styles.navBtn} onClick={onToggleTheme} title="切换主题">
          {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
        </button>
      </div>
    </div>
  );
};
