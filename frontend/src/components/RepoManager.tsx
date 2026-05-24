import React, { useState, useEffect, useCallback } from 'react';
import { X, Plus, Trash2, Play, Loader, GitBranch } from 'lucide-react';
import { repositoryApi, Repository } from '../api';
import { IgnorePatterns } from './IgnorePatterns';
import styles from './RepoManager.module.css';

interface RepoManagerProps {
  isOpen: boolean;
  onClose: () => void;
  onRepositorySelect: (repo: Repository) => void;
  selectedRepo: Repository | null;
}

const LAYERS = ['SDK', 'LOGIC', 'BUSINESS', 'UI'] as const;
const LAYER_COLORS: Record<string, string> = {
  SDK: 'var(--layer-sdk)',
  LOGIC: 'var(--layer-logic)',
  BUSINESS: 'var(--layer-business)',
  UI: 'var(--layer-ui)',
};

const DEFAULT_IGNORE = ['build', 'bin', 'obj', '.git', '.svn', 'node_modules', 'third_party', 'dependencies', 'extern', '__pycache__', '.vs', 'Debug', 'Release', 'x64', 'ARM64'];

export const RepoManager: React.FC<RepoManagerProps> = ({ isOpen, onClose, onRepositorySelect, selectedRepo }) => {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [parsing, setParsing] = useState<number | null>(null);
  const [parseProgress, setParseProgress] = useState<{percent: number, message: string} | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    name: '', path: '', layer: 'SDK', remote_url: '', branch: 'main',
  });
  const [ignorePatterns, setIgnorePatterns] = useState<string[]>(DEFAULT_IGNORE);

  const loadRepos = useCallback(async () => {
    try {
      const data = await repositoryApi.list();
      setRepos(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load repos');
    }
  }, []);

  // 轮询解析进度
  const pollProgress = useCallback((repoId: number, intervalId: ReturnType<typeof setInterval>) => {
    const poll = async () => {
      try {
        const response = await fetch(`/api/repositories/${repoId}/parse-status`);
        const data = await response.json();
        if (data.status === 'completed' || data.status === 'error') {
          clearInterval(intervalId);
          setParseProgress({ percent: 100, message: data.status === 'completed' ? '解析完成!' : '解析失败' });
          // 刷新仓库列表
          loadRepos();
          setTimeout(() => {
            setParsing(null);
            setParseProgress(null);
          }, 2000);
        } else {
          setParseProgress({ percent: data.percent || 0, message: data.message || '解析中...' });
        }
      } catch (err) {
        // ignore polling errors
      }
    };
    return poll;
  }, [loadRepos]);

  useEffect(() => {
    if (isOpen) loadRepos();
  }, [isOpen, loadRepos]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleCreate = async () => {
    if (!formData.name || !formData.path) { setError('Name and path are required'); return; }
    try {
      await repositoryApi.create({ ...formData, parent_repo_id: null, parent_repo_branch: 'main', sln_path: '' });
      setShowCreate(false);
      setFormData({ name: '', path: '', layer: 'SDK', remote_url: '', branch: 'main' });
      loadRepos();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Create failed');
    }
  };

  const handleDelete = async (repo: Repository) => {
    if (!confirm(`Delete repository ${repo.name}?`)) return;
    try { await repositoryApi.delete(repo.id); loadRepos(); }
    catch (err) { setError(err instanceof Error ? err.message : 'Delete failed'); }
  };

  const handleParse = async (repo: Repository) => {
    setParsing(repo.id);
    setParseProgress({ percent: 0, message: '准备解析...' });
    try {
      const ignoreStr = ignorePatterns.length > 0 ? ignorePatterns.join(',') : undefined;

      // 启动进度轮询
      const intervalId = setInterval(() => {
        pollProgress(repo.id, intervalId)();
      }, 500);

      // 发送解析请求（不等待响应）
      repositoryApi.parse(repo.id, undefined, ignoreStr).catch(err => {
        // 忽略错误，让轮询处理
        console.error('Parse request error:', err);
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Parse failed');
      setParsing(null);
      setParseProgress(null);
    }
  };

  const reposByLayer = LAYERS.reduce((acc, layer) => {
    acc[layer] = repos.filter(r => r.layer === layer);
    return acc;
  }, {} as Record<string, Repository[]>);

  return (
    <div className={styles.overlay} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>
        <div className={styles.modalHeader}>
          <h2>Repository Management</h2>
          <button className={styles.closeBtn} onClick={onClose}><X size={20} /></button>
        </div>

        {error && (
          <div className={styles.errorBanner}>
            <span>{error}</span>
            <button onClick={() => setError(null)}><X size={14} /></button>
          </div>
        )}

        {/* 解析进度条 */}
        {parsing && parseProgress && (
          <div className={styles.progressOverlay}>
            <div className={styles.progressCard}>
              <div className={styles.progressTitle}>
                <Loader size={20} className={styles.spin} />
                正在解析代码...
              </div>
              <div className={styles.progressBar}>
                <div
                  className={styles.progressFill}
                  style={{ width: `${parseProgress.percent}%` }}
                />
              </div>
              <div className={styles.progressMessage}>
                {parseProgress.message}
              </div>
            </div>
          </div>
        )}

        <div className={styles.modalBody}>
          <div className={styles.repoList}>
            {LAYERS.map(layer => reposByLayer[layer]?.length > 0 && (
              <div key={layer} className={styles.layerGroup}>
                <h3 className={styles.layerTitle} style={{ color: LAYER_COLORS[layer] }}>{layer}</h3>
                {reposByLayer[layer].map(repo => (
                  <div key={repo.id} className={`${styles.repoCard} ${selectedRepo?.id === repo.id ? styles.repoCardSelected : ''}`}>
                    <div className={styles.repoInfo} onClick={() => { onRepositorySelect(repo); onClose(); }}>
                      <GitBranch size={16} style={{ color: LAYER_COLORS[repo.layer] }} />
                      <div className={styles.repoDetails}>
                        <span className={styles.repoName}>{repo.name}</span>
                        <span className={styles.repoPath} title={repo.path}>{repo.path}</span>
                      </div>
                    </div>
                    <div className={styles.repoActions}>
                      <button className={styles.parseBtn} onClick={() => handleParse(repo)} disabled={parsing === repo.id}>
                        {parsing === repo.id ? <Loader size={14} className={styles.spin} /> : <Play size={14} />}
                        Parse
                      </button>
                      <button className={styles.deleteBtn} onClick={() => handleDelete(repo)}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ))}
            {repos.length === 0 && <p className={styles.emptyText}>No repositories yet. Add one to get started.</p>}
          </div>

          <div className={styles.sidebar}>
            {!showCreate ? (
              <button className={styles.addBtn} onClick={() => setShowCreate(true)}>
                <Plus size={16} /> Add Repository
              </button>
            ) : (
              <div className={styles.createForm}>
                <h3>Add Repository</h3>
                <div className={styles.formGroup}>
                  <label>Name *</label>
                  <input type="text" value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })} placeholder="e.g. sdk_core" />
                </div>
                <div className={styles.formGroup}>
                  <label>Path *</label>
                  <input type="text" value={formData.path} onChange={e => setFormData({ ...formData, path: e.target.value })} placeholder="/path/to/repo" />
                </div>
                <div className={styles.formGroup}>
                  <label>Layer</label>
                  <select value={formData.layer} onChange={e => setFormData({ ...formData, layer: e.target.value })}>
                    {LAYERS.map(l => <option key={l} value={l}>{l}</option>)}
                  </select>
                </div>
                <div className={styles.formGroup}>
                  <label>Branch</label>
                  <input type="text" value={formData.branch} onChange={e => setFormData({ ...formData, branch: e.target.value })} />
                </div>
                <div className={styles.formActions}>
                  <button className={styles.cancelBtn} onClick={() => setShowCreate(false)}>Cancel</button>
                  <button className={styles.submitBtn} onClick={handleCreate}>Create</button>
                </div>
              </div>
            )}

            <div className={styles.ignoreSection}>
              <h4>Parse Ignore Patterns</h4>
              <p className={styles.ignoreHint}>Directories and patterns to skip during parsing</p>
              <IgnorePatterns patterns={ignorePatterns} onChange={setIgnorePatterns} defaults={DEFAULT_IGNORE} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
