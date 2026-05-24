import { useState, useCallback, useEffect } from 'react';
import { Navbar } from './components/Navbar';
import { Sidebar } from './components/Sidebar';
import { MainTabs } from './components/MainTabs';
import { DetailPanel } from './components/DetailPanel';
import { RepoManager } from './components/RepoManager';
import { Repository, Symbol } from './api';
import { useTheme } from './hooks/useTheme';
import layoutStyles from './App.module.css';
import './theme.css';

function App() {
  const { theme, toggle: toggleTheme } = useTheme();
  const [selectedRepo, setSelectedRepo] = useState<Repository | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState<Symbol | null>(null);
  const [showSidebar, setShowSidebar] = useState(true);
  const [showDetail, setShowDetail] = useState(true);
  const [showRepoManager, setShowRepoManager] = useState(false);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === 'b') {
        e.preventDefault();
        setShowSidebar(s => !s);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const handleSymbolSelect = useCallback((symbol: Symbol) => {
    setSelectedSymbol(symbol);
    setShowDetail(true);
  }, []);

  const handleRepoSelect = useCallback((repo: Repository) => {
    setSelectedRepo(repo);
    setSelectedSymbol(null);
  }, []);

  const layoutClass = [
    layoutStyles.appLayout,
    !showSidebar && !showDetail ? layoutStyles.appLayoutBothClosed :
    !showSidebar ? layoutStyles.appLayoutSidebarClosed :
    !showDetail ? layoutStyles.appLayoutDetailClosed : '',
  ].filter(Boolean).join(' ');

  return (
    <div className={layoutClass}>
      <div className={layoutStyles.navbarArea}>
        <Navbar
          theme={theme}
          onToggleTheme={toggleTheme}
          selectedRepo={selectedRepo}
          onOpenRepoManager={() => setShowRepoManager(true)}
          onSymbolSelect={handleSymbolSelect}
          onToggleSidebar={() => setShowSidebar(s => !s)}
          onToggleDetail={() => setShowDetail(s => !s)}
        />
      </div>

      {showSidebar && (
        <div className={layoutStyles.sidebarArea}>
          <Sidebar
            repositoryId={selectedRepo?.id}
            onSymbolSelect={handleSymbolSelect}
          />
        </div>
      )}

      <div className={layoutStyles.mainArea}>
        <MainTabs
          symbolId={selectedSymbol?.id ?? null}
          repositoryId={selectedRepo?.id}
        />
      </div>

      {showDetail && (
        <div className={layoutStyles.detailArea}>
          <DetailPanel
            symbol={selectedSymbol}
            onClose={() => setShowDetail(false)}
          />
        </div>
      )}

      <RepoManager
        isOpen={showRepoManager}
        onClose={() => setShowRepoManager(false)}
        onRepositorySelect={repo => { handleRepoSelect(repo); setShowRepoManager(false); }}
        selectedRepo={selectedRepo}
      />
    </div>
  );
}

export default App;
