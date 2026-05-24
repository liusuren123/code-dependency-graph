import React, { useState } from 'react';
import { GitBranch, Network, Activity } from 'lucide-react';
import { CallTreeView } from './CallTreeView';
import { GraphView } from './GraphView';
import { AnalysisView } from './AnalysisView';
import styles from './MainTabs.module.css';

interface MainTabsProps {
  symbolId: number | null;
  repositoryId: number | undefined;
}

export const MainTabs: React.FC<MainTabsProps> = ({ symbolId, repositoryId }) => {
  const [activeTab, setActiveTab] = useState<'calltree' | 'graph' | 'analysis'>('calltree');

  return (
    <div className={styles.mainTabs}>
      <div className={styles.tabBar}>
        <button
          className={`${styles.tab} ${activeTab === 'calltree' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('calltree')}
        >
          <GitBranch size={14} />
          Call Tree
        </button>
        {/* <button
          className={`${styles.tab} ${activeTab === 'graph' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('graph')}
        >
          <Network size={14} />
          Graph
        </button> */}
        <button
          className={`${styles.tab} ${activeTab === 'analysis' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('analysis')}
        >
          <Activity size={14} />
          Analysis
        </button>
      </div>
      <div className={styles.tabContent}>
        {activeTab === 'calltree' && (
          symbolId ? (
            <CallTreeView key={symbolId} symbolId={symbolId} />
          ) : (
            <div className={styles.emptyState}>
              <GitBranch size={48} className={styles.emptyIcon} />
              <h3>Select a Symbol</h3>
              <p>Choose a function from the Explorer panel to view its call tree</p>
            </div>
          )
        )}
        {activeTab === 'graph' && (
          <GraphView repositoryId={repositoryId} />
        )}
        {activeTab === 'analysis' && (
          <AnalysisView symbolId={symbolId} />
        )}
      </div>
    </div>
  );
};
