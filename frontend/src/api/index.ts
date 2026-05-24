/**
 * API Client
 */
const API_BASE = '/api';

interface ApiResponse<T = any> {
  success: boolean;
  message: string;
  data?: T;
}

export interface Repository {
  id: number;
  name: string;
  path: string;
  layer: string;
  remote_url: string;
  branch: string;
  parent_repo_id: number | null;
  parent_repo_branch: string;
  sln_path: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface Symbol {
  id: number;
  name: string;
  kind: string;
  file_path: string;
  line_number: number;
  namespace: string;
  return_type: string;
  parameters: string;
  signature: string;
  hash_value: string;
}

export interface GraphNode {
  id: string;
  label: string;
  kind: string;
  layer: string;
  namespace: string;
  file: string;
  line: number;
  signature: string;
  x?: number;
  y?: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  source_file: string;
  source_line: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  layers: string[];
  statistics: {
    total_nodes: number;
    total_edges: number;
    repositories_by_layer: Record<string, number>;
    symbols_by_layer: Record<string, number>;
  };
}

export interface CallTreeNode {
  symbol: {
    id: number;
    name: string;
    kind: string;
    signature: string;
    file: string;
    line: number;
    dep_type?: string;
    dep_file?: string;
  };
  direction: string;
  depth: number;
  is_recursive?: boolean;
  children: CallTreeNode[];
}

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  const result: ApiResponse<T> = await response.json();

  if (!result.success) {
    throw new Error(result.message);
  }

  return result.data as T;
}

export const api = {
  get: (path: string) => fetchApi<any>(path),
  post: (path: string, data: any) =>
    fetchApi<any>(path, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  put: (path: string, data: any) =>
    fetchApi<any>(path, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  delete: (path: string) => fetchApi<any>(path, { method: 'DELETE' }),
};

// Repository API
export const repositoryApi = {
  list: (layer?: string) =>
    fetchApi<{ repositories: Repository[] }>(
      `/repositories${layer ? `?layer=${layer}` : ''}`
    ).then((r) => r.repositories),

  get: (id: number) =>
    fetchApi<{ repository: Repository; statistics: any }>(`/repositories/${id}`),

  create: (repo: Partial<Repository> & { name: string; path: string; layer: string }) =>
    fetchApi<{ repository_id: number }>('/repositories', {
      method: 'POST',
      body: JSON.stringify(repo),
    }),

  update: (id: number, updates: Partial<Repository>) =>
    fetchApi(`/repositories/${id}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    }),

  delete: (id: number) =>
    fetchApi(`/repositories/${id}`, { method: 'DELETE' }),

  parse: (id: number, fileExtensions?: string[], ignorePatterns?: string) => {
    const params = new URLSearchParams();
    if (fileExtensions) params.set('file_extensions', fileExtensions.join(','));
    if (ignorePatterns) params.set('ignore_patterns', ignorePatterns);
    const qs = params.toString();
    return fetchApi<{ symbols_count: number; dependencies_count: number }>(
      `/repositories/${id}/parse${qs ? `?${qs}` : ''}`,
      { method: 'POST' }
    );
  },
};

// Graph API
export const graphApi = {
  getGraphData: (params?: { repository_id?: number; layer?: string; max_nodes?: number }) => {
    const searchParams = new URLSearchParams();
    if (params?.repository_id) searchParams.set('repository_id', String(params.repository_id));
    if (params?.layer) searchParams.set('layer', params.layer);
    if (params?.max_nodes) searchParams.set('max_nodes', String(params.max_nodes));
    const query = searchParams.toString();
    return fetchApi<GraphData>(`/graph${query ? `?${query}` : ''}`);
  },

  getLayerDependencies: () =>
    fetchApi<{ layer_dependencies: Array<{ source_layer: string; target_layer: string; dependency_count: number }> }>(
      '/graph/layers'
    ).then((r) => r.layer_dependencies),
};

// Symbol API
export const symbolApi = {
  search: (params: {
    keyword?: string;
    layer?: string;
    kind?: string;
    repository_id?: number;
    page?: number;
    page_size?: number;
  }) => {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) searchParams.set(k, String(v));
    });
    return fetchApi<{
      total: number;
      page: number;
      page_size: number;
      symbols: Symbol[];
    }>(`/symbols?${searchParams.toString()}`);
  },

  getDetail: (id: number) =>
    fetchApi<{
      symbol: Symbol;
      dependencies: { incoming: any[]; outgoing: any[] };
    }>(`/symbols/${id}`),

  getCallTree: (symbolId: number, direction: 'outgoing' | 'incoming' = 'outgoing', maxDepth: number = 3) => {
    return fetchApi<{
      tree: CallTreeNode;
      tree_text: string;
      statistics: {
        total_nodes: number;
        max_depth: number;
        direction: string;
      };
    }>(`/symbols/${symbolId}/call-tree?direction=${direction}&max_depth=${maxDepth}`);
  },

  getClassMembers: (symbolId: number) => {
    return fetchApi<{ class: Symbol; members: Symbol[]; total: number }>(`/symbols/${symbolId}/members`)
      .then(r => r.members);
  },

  getBranchPaths: (id: number) =>
    fetchApi(`/symbols/${id}/branch-paths`),

  getTypeChain: (id: number) =>
    fetchApi(`/symbols/${id}/type-chain`),

  getErrorPaths: (id: number) =>
    fetchApi(`/symbols/${id}/error-paths`),

  getErrorPropagation: (id: number) =>
    fetchApi(`/error-propagation/${id}`),

  getHierarchy: (id: number) =>
    fetchApi(`/symbols/${id}/hierarchy`),

  getDataFlow: (id: number) =>
    fetchApi(`/symbols/${id}/data-flow`),

  getImpact: (id: number, maxDepth: number = 6) =>
    fetchApi(`/symbols/${id}/impact?max_depth=${maxDepth}`),

  getSource: (id: number, contextLines: number = 5) =>
    fetchApi<{
      file_path: string;
      relative_path: string;
      target_line: number;
      total_lines: number;
      snippet: Array<{ line_number: number; content: string; is_target: boolean }>;
    }>(`/symbols/${id}/source?context_lines=${contextLines}`),
};

// Simulate API
export const simulateApi = {
  trigger: (symbolId: number, inputParams: Record<string, string> = {}, maxDepth: number = 6) =>
    fetchApi('/simulate/trigger', {
      method: 'POST',
      body: JSON.stringify({ symbol_id: symbolId, input_params: inputParams, max_depth: maxDepth }),
    }),

  traceDataFlow: (symbolId: number, maxDepth: number = 6) =>
    fetchApi(`/data-flow/trace?symbol_id=${symbolId}&max_depth=${maxDepth}`),
};

// Type API
export const typeApi = {
  getUsage: (typeName: string) =>
    fetchApi(`/types/${encodeURIComponent(typeName)}/usage`),
};

// Statistics API
export const statisticsApi = {
  get: () =>
    fetchApi<{
      total_repositories: number;
      layers: Record<string, { repositories: string[]; symbols_count: number }>;
      layer_dependencies: any[];
    }>('/statistics'),
};
