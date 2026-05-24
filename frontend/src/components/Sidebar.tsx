import React, { useState } from 'react';
import { FolderTree, Search } from 'lucide-react';
import { ClassTreePanel } from './ClassTreePanel';
import { SearchPanel } from './SearchPanel';
import styles from './Sidebar.module.css';

interface SidebarProps {
  repositoryId: number | undefined;
  onSymbolSelect: (symbol: any) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ repositoryId, onSymbolSelect }) => {
  const [activeTab, setActiveTab] = useState<'explorer' | 'search'>('explorer');

  return (
    <div className={styles.sidebar}>
      <div className={styles.tabBar}>
        <button
          className={`${styles.tab} ${activeTab === 'explorer' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('explorer')}
        >
          <FolderTree size={14} />
          Explorer
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'search' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('search')}
        >
          <Search size={14} />
          Search
        </button>
      </div>
      <div className={styles.tabContent}>
        {activeTab === 'explorer' && (
          <ClassTreePanel repositoryId={repositoryId} onSymbolSelect={onSymbolSelect} />
        )}
        {activeTab === 'search' && (
          <SearchPanel onSymbolSelect={onSymbolSelect} />
        )}
      </div>
    </div>
  );
};
