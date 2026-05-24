import React, { useState, useEffect, useCallback } from 'react';
import { repositoryApi, Repository, api } from '../api';

interface RepoPanelProps {
  onRepositorySelect?: (repo: Repository) => void;
  onParseComplete?: () => void;
}

const LAYERS = ['SDK', 'LOGIC', 'BUSINESS', 'UI'];
const LAYER_COLORS: Record<string, string> = {
  SDK: '#4CAF50',
  LOGIC: '#2196F3',
  BUSINESS: '#FF9800',
  UI: '#9C27B0',
};

// 获取 Git 信息的 API 调用
const fetchGitInfo = async (path: string) => {
  try {
    // api.get 已经返回 result.data，所以直接返回 response
    const response = await api.get(`/repositories/git-info?path=${encodeURIComponent(path)}`);
    return response || null;
  } catch (err) {
    console.error('获取 Git 信息失败:', err);
    return null;
  }
};

export const RepoPanel: React.FC<RepoPanelProps> = ({
  onRepositorySelect,
  onParseComplete,
}) => {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [layers, setLayers] = useState<string[]>(LAYERS);
  const [loading, setLoading] = useState(true);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [showLayerManager, setShowLayerManager] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    path: '',
    layer: 'SDK',
    remote_url: '',
    branch: 'main',
    parent_repo_id: '',
    parent_repo_branch: 'main',
  });
  const [availableBranches, setAvailableBranches] = useState<string[]>([]);
  const [parsing, setParsing] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingGitInfo, setLoadingGitInfo] = useState(false);

  // 路径变化时自动获取 Git 信息
  useEffect(() => {
    if (!formData.path || !showCreateForm) return;

    const timer = setTimeout(async () => {
      setLoadingGitInfo(true);
      try {
        const gitInfo = await fetchGitInfo(formData.path);
        // gitInfo 现在直接是 data 对象: { current_branch, remote_url, all_branches, success }
        if (gitInfo && (gitInfo.success || gitInfo.current_branch)) {
          setAvailableBranches(gitInfo.all_branches || [gitInfo.current_branch]);

          // 自动填充分支和远程 URL
          setFormData(prev => ({
            ...prev,
            branch: gitInfo.current_branch || prev.branch,
            remote_url: gitInfo.remote_url || prev.remote_url
          }));
        }
      } catch (err) {
        console.error('自动获取 Git 信息失败:', err);
      } finally {
        setLoadingGitInfo(false);
      }
    }, 500); // 防抖 500ms

    return () => clearTimeout(timer);
  }, [formData.path, showCreateForm]);

  const loadRepositories = useCallback(async () => {
    setLoading(true);
    try {
      const data = await repositoryApi.list();
      setRepos(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRepositories();
  }, [loadRepositories]);

  const handleCreate = async () => {
    if (!formData.name || !formData.path) {
      setError('名称和路径不能为空');
      return;
    }

    try {
      await repositoryApi.create({
        ...formData,
        parent_repo_id: formData.parent_repo_id ? Number(formData.parent_repo_id) : null,
      });
      setShowCreateForm(false);
      setFormData({
        name: '',
        path: '',
        layer: 'SDK',
        remote_url: '',
        branch: 'main',
        parent_repo_id: '',
        parent_repo_branch: 'main',
      });
      loadRepositories();
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建失败');
    }
  };

  const handleDelete = async (repo: Repository) => {
    if (!confirm(`确定删除仓库 ${repo.name}:${repo.branch}？`)) return;

    try {
      await repositoryApi.delete(repo.id);
      loadRepositories();
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败');
    }
  };

  const handleParse = async (repo: Repository) => {
    setParsing(repo.id);
    try {
      await repositoryApi.parse(repo.id);
      onParseComplete?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : '解析失败');
    } finally {
      setParsing(null);
    }
  };

  // 按层级分组
  const reposByLayer = layers.reduce((acc, layer) => {
    acc[layer] = repos.filter(r => r.layer === layer);
    return acc;
  }, {} as Record<string, Repository[]>);

  return (
    <div className="repo-panel">
      <div className="panel-header">
        <h3>仓库管理</h3>
        <button className="btn-primary" onClick={() => setShowCreateForm(!showCreateForm)}>
          {showCreateForm ? '取消' : '+ 添加仓库'}
        </button>
      </div>

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      {/* 创建表单 */}
      {showCreateForm && (
        <div className="create-form">
          <div className="form-group">
            <label>仓库名称 *</label>
            <input
              type="text"
              value={formData.name}
              onChange={e => setFormData({ ...formData, name: e.target.value })}
              placeholder="如: sdk_core"
            />
          </div>
          <div className="form-group">
            <label>本地路径 *</label>
            <div className="path-input-group">
              <input
                type="text"
                value={formData.path}
                onChange={e => setFormData({ ...formData, path: e.target.value })}
                placeholder="如: /path/to/repo"
              />
              <label className="file-btn" title="选择目录">
                <input
                  type="file"
                  webkitdirectory
                  onChange={e => {
                    const file = e.target.files?.[0];
                    if (file) {
                      const dir = (file as any).webkitRelativePath?.split('/')[0] || file.name;
                      // 尝试获取完整路径
                      const filePath = (file as any).path || dir;
                      setFormData(prev => ({
                        ...prev,
                        path: filePath,
                        name: prev.name || dir
                      }));
                    }
                  }}
                  style={{ display: 'none' }}
                />
                📁
              </label>
              <label className="file-btn" title="选择 .sln 文件">
                <input
                  type="file"
                  accept=".sln"
                  onChange={e => {
                    const file = e.target.files?.[0];
                    if (file) {
                      const filePath = (file as any).path || file.name;
                      const dir = filePath.replace(/[/\\][^/\\]*$/, '');
                      const fileName = file.name.replace(/\.sln$/, '');

                      setFormData(prev => ({
                        ...prev,
                        path: dir || formData.path,
                        name: prev.name || fileName
                      }));
                    }
                  }}
                  style={{ display: 'none' }}
                />
                📄
              </label>
            </div>
            <small className="hint">点击 📁 选择目录，或 📄 选择 .sln 文件</small>
          </div>
          <div className="form-group">
            <label>层级 *</label>
            <select
              value={formData.layer}
              onChange={e => setFormData({ ...formData, layer: e.target.value })}
            >
              {layers.map(layer => (
                <option key={layer} value={layer}>{layer}</option>
              ))}
            </select>
            <button
              className="btn-text-link"
              onClick={() => setShowLayerManager(true)}
              type="button"
            >
              + 管理层级
            </button>
          </div>
          <div className="form-group">
            <label>
              分支 {loadingGitInfo && <span className="loading-hint">⟳</span>}
            </label>
            {availableBranches.length > 0 ? (
              <select
                value={formData.branch}
                onChange={e => setFormData({ ...formData, branch: e.target.value })}
              >
                {availableBranches.map(branch => (
                  <option key={branch} value={branch}>{branch}</option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                value={formData.branch}
                onChange={e => setFormData({ ...formData, branch: e.target.value })}
                placeholder="main"
              />
            )}
          </div>
          <div className="form-group">
            <label>远程 URL</label>
            <input
              type="text"
              value={formData.remote_url}
              onChange={e => setFormData({ ...formData, remote_url: e.target.value })}
              placeholder="git@github.com:xxx/repo.git"
            />
          </div>
          <div className="form-group">
            <label>依赖的上游仓库</label>
            <select
              value={formData.parent_repo_id}
              onChange={e => setFormData({ ...formData, parent_repo_id: e.target.value })}
            >
              <option value="">无</option>
              {repos.map(repo => (
                <option key={repo.id} value={repo.id}>
                  {repo.name}:{repo.branch}
                </option>
              ))}
            </select>
          </div>
          <div className="form-actions">
            <button className="btn-primary" onClick={handleCreate}>创建</button>
          </div>
        </div>
      )}

      {/* 仓库列表 */}
      <div className="repo-list">
        {loading ? (
          <div className="loading">加载中...</div>
        ) : repos.length === 0 ? (
          <div className="empty">暂无仓库，点击上方按钮添加</div>
        ) : (
          LAYERS.map(layer => (
            reposByLayer[layer].length > 0 && (
              <div key={layer} className="layer-section">
                <div className="layer-header" style={{ borderLeftColor: LAYER_COLORS[layer] }}>
                  <span className="layer-name">{layer}</span>
                  <span className="layer-count">{reposByLayer[layer].length}</span>
                </div>
                <div className="layer-repos">
                  {reposByLayer[layer].map(repo => (
                    <div key={repo.id} className="repo-item">
                      <div
                        className="repo-info"
                        onClick={() => onRepositorySelect?.(repo)}
                      >
                        <div className="repo-name">{repo.name}</div>
                        <div className="repo-meta">
                          <span className="repo-branch">{repo.branch}</span>
                          {repo.parent_repo_id && (
                            <span className="repo-dep">
                              依赖: {repos.find(r => r.id === repo.parent_repo_id)?.name}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="repo-actions">
                        <button
                          className="btn-icon"
                          onClick={() => handleParse(repo)}
                          disabled={parsing === repo.id}
                          title="解析代码"
                        >
                          {parsing === repo.id ? '⟳' : '▶'}
                        </button>
                        <button
                          className="btn-icon"
                          onClick={() => handleDelete(repo)}
                          title="删除"
                        >
                          ×
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )
          ))
        )}
      </div>

      {/* 层级管理器弹窗 */}
      {showLayerManager && (
        <div className="modal-overlay" onClick={() => setShowLayerManager(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>管理层级</h3>
              <button className="btn-close" onClick={() => setShowLayerManager(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="layer-list">
                {layers.map((layer, index) => (
                  <div key={layer} className="layer-item">
                    <span
                      className="layer-color"
                      style={{ backgroundColor: LAYER_COLORS[layer] || '#666' }}
                    />
                    <span className="layer-name">{layer}</span>
                    <button
                      className="btn-icon"
                      onClick={() => {
                        const newLayers = [...layers];
                        newLayers.splice(index, 1);
                        setLayers(newLayers);
                      }}
                      title="删除"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
              <div className="add-layer-form">
                <input
                  type="text"
                  placeholder="新层级名称"
                  id="newLayerInput"
                />
                <button
                  className="btn-primary"
                  onClick={() => {
                    const input = document.getElementById('newLayerInput') as HTMLInputElement;
                    const name = input?.value?.trim();
                    if (name && !layers.includes(name)) {
                      setLayers([...layers, name]);
                      if (input) input.value = '';
                    }
                  }}
                >
                  添加
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
