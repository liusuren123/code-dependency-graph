import React, { useState, useEffect, useCallback } from 'react';
import { Search, ChevronRight, Layers, Braces, Cpu, CircleDot, Hash, Type, Variable } from 'lucide-react';
import { symbolApi, Symbol } from '../api';

interface ClassTreePanelProps {
  repositoryId?: number;
  onSymbolSelect: (symbol: Symbol) => void;
}

interface ClassNode {
  symbol: Symbol;
  children: Symbol[];
  childrenLoaded: boolean;
}

const KIND_COLORS: Record<string, string> = {
  class: '#38bdf8',
  struct: '#a78bfa',
  function: '#4ade80',
  method: '#4ade80',
  enum: '#fb923c',
  typedef: '#94a3b8',
  variable: '#f472b6',
};

const KIND_ICONS: Record<string, React.FC<{ size?: number; style?: React.CSSProperties }>> = {
  class: Braces,
  struct: Cpu,
  function: CircleDot,
  method: CircleDot,
  enum: Hash,
  typedef: Type,
  variable: Variable,
};

export const ClassTreePanel: React.FC<ClassTreePanelProps> = ({
  repositoryId,
  onSymbolSelect,
}) => {
  const [classes, setClasses] = useState<ClassNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterKind, setFilterKind] = useState<'all' | 'class' | 'struct'>('all');
  const [expandedNodes, setExpandedNodes] = useState<Set<number>>(new Set());

  const loadClasses = useCallback(async () => {
    setLoading(true);
    try {
      const result = await symbolApi.search({
        kind: 'class,struct',
        repository_id: repositoryId,
        page_size: 100,
      });

      const classNodes: ClassNode[] = result.symbols
        .filter((s: Symbol) => filterKind === 'all' || s.kind === filterKind)
        .map((symbol: Symbol) => ({
          symbol,
          children: [],
          childrenLoaded: false,
        }));

      setClasses(classNodes);
    } catch (err) {
      console.error('Load classes error:', err);
    } finally {
      setLoading(false);
    }
  }, [repositoryId, filterKind]);

  useEffect(() => {
    loadClasses();
  }, [loadClasses]);

  const loadClassMembers = useCallback(async (classId: number) => {
    try {
      return await symbolApi.getClassMembers(classId);
    } catch (err) {
      console.error('Load members error:', err);
      return [];
    }
  }, []);

  const handleToggle = async (classId: number) => {
    const isExpanded = expandedNodes.has(classId);

    if (!isExpanded) {
      const classNode = classes.find(c => c.symbol.id === classId);
      if (classNode && !classNode.childrenLoaded) {
        const members = await loadClassMembers(classId);
        setClasses(prev => prev.map(c => {
          if (c.symbol.id === classId) {
            return { ...c, children: members, childrenLoaded: true };
          }
          return c;
        }));
      }
    }

    setExpandedNodes(prev => {
      const next = new Set(prev);
      if (next.has(classId)) {
        next.delete(classId);
      } else {
        next.add(classId);
      }
      return next;
    });
  };

  const filteredClasses = classes.filter(node => {
    if (!searchTerm) return true;
    const q = searchTerm.toLowerCase();
    return node.symbol.name.toLowerCase().includes(q) ||
           node.symbol.namespace.toLowerCase().includes(q);
  });

  const getSortedMembers = (members: Symbol[]) => {
    return [...members].sort((a, b) => {
      const kindOrder: Record<string, number> = { function: 0, method: 0, class: 1, struct: 1, enum: 2, typedef: 3, variable: 4 };
      const kindDiff = (kindOrder[a.kind] || 5) - (kindOrder[b.kind] || 5);
      if (kindDiff !== 0) return kindDiff;
      return a.name.localeCompare(b.name);
    });
  };

  if (loading) {
    return (
      <div className="ct-loading">
        <div className="ct-spinner" />
        <span>Loading...</span>
      </div>
    );
  }

  return (
    <div className="ct-root">
      {/* Section header */}
      <div className="ct-section-header">
        <Layers size={13} />
        <span>CLASSES</span>
        <span className="ct-badge">{filteredClasses.length}</span>
      </div>

      {/* Search */}
      <div className="ct-toolbar">
        <div className="ct-search">
          <Search size={13} className="ct-search-icon" />
          <input
            type="text"
            placeholder="Filter..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="ct-search-input"
          />
        </div>
        <div className="ct-segmented">
          {(['all', 'class', 'struct'] as const).map(k => (
            <button
              key={k}
              className={`ct-seg-btn ${filterKind === k ? 'ct-seg-active' : ''}`}
              onClick={() => setFilterKind(k)}
            >
              {k === 'all' ? 'All' : k === 'class' ? 'Class' : 'Struct'}
            </button>
          ))}
        </div>
      </div>

      {/* Tree */}
      <div className="ct-list">
        {filteredClasses.length === 0 ? (
          <div className="ct-empty">
            <p>No classes found</p>
            <p className="ct-empty-hint">Select a repository and parse code first</p>
          </div>
        ) : (
          filteredClasses.map((node) => {
            const isExpanded = expandedNodes.has(node.symbol.id);
            const iconColor = KIND_COLORS[node.symbol.kind] || '#94a3b8';
            const IconComp = KIND_ICONS[node.symbol.kind] || CircleDot;

            return (
              <div key={node.symbol.id} className="ct-item">
                <div
                  className={`ct-item-row ${isExpanded ? 'ct-expanded' : ''}`}
                  onClick={() => handleToggle(node.symbol.id)}
                  title={`${node.symbol.name}\n${node.symbol.file_path}:${node.symbol.line_number}`}
                >
                  <span className="ct-arrow">
                    <ChevronRight size={14} />
                  </span>
                  <span className={`ct-icon kind-${node.symbol.kind}`}>
                    <IconComp size={14} style={{ color: iconColor }} />
                  </span>
                  <span className="ct-label">{node.symbol.name}</span>
                  {node.symbol.namespace && (
                    <span className="ct-sub">{node.symbol.namespace}</span>
                  )}
                </div>

                {isExpanded && (
                  <div className="ct-children">
                    {node.childrenLoaded ? (
                      node.children.length > 0 ? (
                        getSortedMembers(node.children).map((member) => {
                          const mColor = KIND_COLORS[member.kind] || '#94a3b8';
                          const MIconComp = KIND_ICONS[member.kind] || CircleDot;
                          return (
                            <div
                              key={member.id}
                              className="ct-child-row"
                              onClick={() => onSymbolSelect(member)}
                              title={`${member.name}\n${member.file_path}:${member.line_number}`}
                            >
                              <span className="ct-guide" />
                              <span className={`ct-icon sm kind-${member.kind}`}>
                                <MIconComp size={13} style={{ color: mColor }} />
                              </span>
                              <span className="ct-child-name">{member.name}</span>
                              {member.return_type && (
                                <span className="ct-child-type">{member.return_type}</span>
                              )}
                            </div>
                          );
                        })
                      ) : (
                        <div className="ct-no-children">
                          <span className="ct-guide" />
                          No members
                        </div>
                      )
                    ) : (
                      <div className="ct-loading-members">
                        <div className="ct-spinner sm" />
                        Loading...
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
