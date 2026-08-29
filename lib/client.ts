/**
 * API Client for backend communication
 */

// Use VITE_API_BASE environment variable for backend API base URL
// Force local backend in development mode
// Remove trailing slash to ensure proper URL concatenation
const getApiBaseUrl = () => {
  let base = import.meta.env.VITE_API_BASE || (import.meta.env.DEV
    ? 'http://127.0.0.1:8000/api'
    : '/api');
  
  // Remove trailing slash
  base = base.endsWith('/') ? base.slice(0, -1) : base;
  
  // If base doesn't end with /api, append it
  if (!base.endsWith('/api')) {
    base = base + '/api';
  }
  
  return base;
};
const API_BASE_URL = getApiBaseUrl();

export interface FileInfo {
  id: string;
  name: string;
  originalName?: string;
  size: string;
  rows: number;
  columns: number;
  headers: string[];
  preview: string[][];
  uploadedAt: string;
}

export interface UploadFileResponse {
  success: boolean;
  message: string;
  file: FileInfo;
}

export interface QueryRequest {
  question: string;
  fileIds: string[];
  project_id?: string;
  model?: string;
  prompt_style?: string; // zero, zero_cot, sub_question (optional, defaults to "zero")
  mode?: 'agent';
  conversationId?: string;
  userMessageId?: string;
}

export interface AgentStep {
  step: number;
  node: string;
  tool: string;
  thought: string;
  args: Record<string, any>;
  status: string;
  observation: string;
  duration_ms?: number;
}

export type VisualizationType = 'bar' | 'line' | 'pie' | 'scatter' | 'histogram' | 'box' | 'heatmap' | 'table';

export interface VisualizationDataset {
  id: string;
  name: string;
  rows: Array<Record<string, unknown>>;
}

export interface VisualizationSpec {
  type: VisualizationType;
  title: string;
  dataset_id: string;
  description?: string;
  x?: string;
  y?: string;
  value?: string;
  series?: string;
  lower?: string;
  q1?: string;
  median?: string;
  q3?: string;
  upper?: string;
}

export interface ResultEvidence {
  plan_metric_key?: string | null;
  kind: 'scalar' | 'dataset';
  value?: string | number | boolean | null;
  value_scale?: 'raw' | 'fraction' | 'percent' | null;
  unit?: string | null;
  dataset_id?: string | null;
  value_field?: string | null;
  dimension_fields: string[];
  coordinates: Record<string, string | number | boolean | null>;
  label?: string | null;
}

export interface AnalysisResult {
  answer_type: 'number' | 'table' | 'text';
  primary_value?: string | number | boolean | null;
  unit?: string | null;
  summary: string;
  rows: Array<Record<string, unknown>>;
  columns_used: string[];
  metric_id?: string | null;
  assumptions: string[];
  insights?: string[];
  datasets?: VisualizationDataset[];
  visualizations?: VisualizationSpec[];
  evidence?: ResultEvidence[];
}

export interface ResponseData {
  content: string;
  code?: string;
  thinking_process?: string;
  status: 'success' | 'error' | 'running';
  output?: {
    type: 'table' | 'chart' | 'number' | 'text';
    data: any;
    analysis_result?: AnalysisResult;
  };
  metadata?: {
    agent_mode?: boolean;
    agent_framework?: string;
    project_id?: string | null;
    agent_steps?: AgentStep[];
    selected_skills?: Array<{
      id?: string;
      name: string;
      guidance: string;
      matched_terms?: string[];
      selection_mode?: "keyword_match" | "default_fallback";
    }>;
    plan?: Record<string, any>;
    retrieved_metrics?: any[];
    validation_report?: any;
    final_answer_validation?: any;
    analysis_result?: AnalysisResult;
    repair_attempts?: number;
    max_repair_attempts?: number;
    execution_attempts?: any[];
    memory?: {
      used: boolean;
      recent_message_count: number;
      verified_finding_count: number;
      source_run_ids: string[];
    };
    [key: string]: any;
  };
}

export interface QueryResponse {
  success: boolean;
  llmResponse: ResponseData;
  sandboxResponse: ResponseData;
}

export interface AgentProgressEvent {
  id?: string;
  type?: 'run_started';
  graph_thread_id?: string;
  node?: string;
  status: 'running' | 'completed' | 'error';
  title_zh?: string;
  title_en?: string;
  detail_zh?: string;
  detail_en?: string;
  timestamp: number;
}

export interface PersistedChatMessage {
  id: string;
  type: 'user' | 'ai';
  content: string;
  timestamp: string;
  filesUsed?: string[];
  llmResponse?: ResponseData;
  sandboxResponse?: ResponseData;
}

export interface PersistedConversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
  messages: PersistedChatMessage[];
  activeFileIds: string[];
}

async function parseApiResponse<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: fallback }));
    throw new Error(error.detail || error.error || error.message || fallback);
  }
  return response.json();
}

export async function listConversations(): Promise<PersistedConversation[]> {
  const response = await fetch(`${API_BASE_URL}/conversations`);
  const data = await parseApiResponse<{ conversations: PersistedConversation[] }>(response, 'Failed to load conversations');
  return data.conversations || [];
}

export async function createConversation(title: string, activeFileIds: string[] = []): Promise<PersistedConversation> {
  const response = await fetch(`${API_BASE_URL}/conversations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, activeFileIds }),
  });
  const data = await parseApiResponse<{ conversation: PersistedConversation }>(response, 'Failed to create conversation');
  return data.conversation;
}

export async function updateConversation(
  conversationId: string,
  updates: { title?: string; activeFileIds?: string[] },
): Promise<PersistedConversation> {
  const response = await fetch(`${API_BASE_URL}/conversations/${conversationId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  const data = await parseApiResponse<{ conversation: PersistedConversation }>(response, 'Failed to update conversation');
  return data.conversation;
}

export async function deleteConversation(conversationId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/conversations/${conversationId}`, { method: 'DELETE' });
  await parseApiResponse(response, 'Failed to delete conversation');
}

/**
 * Upload a single CSV file
 */
export async function uploadFile(file: File): Promise<UploadFileResponse> {
  const formData = new FormData();
  formData.append('file', file);

  // API_BASE_URL already includes /api prefix
  // So the final URL will be: /api/files/upload
  const uploadUrl = `${API_BASE_URL}/files/upload`;
  console.log('[uploadFile] Request URL:', uploadUrl);
  console.log('[uploadFile] API_BASE_URL:', API_BASE_URL);
  console.log('[uploadFile] File name:', file.name);

  const response = await fetch(uploadUrl, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    let errorData;
    try {
      errorData = JSON.parse(errorText);
    } catch {
      errorData = { error: errorText || 'Upload failed' };
    }
    
    // Provide helpful error messages
    if (response.status === 404) {
      console.error('[uploadFile] 404 Not Found - Backend endpoint not found');
      console.error('[uploadFile] Requested URL:', uploadUrl);
      console.error('[uploadFile] Expected: /api/files/upload');
      console.error('[uploadFile] Solution: Check VITE_API_BASE environment variable in Vercel');
      throw new Error(`Backend endpoint not found (404). Requested: ${uploadUrl}. Please check VITE_API_BASE environment variable is set correctly (should be: https://your-backend.up.railway.app/api)`);
    }
    
    throw new Error(errorData.error || errorData.message || `Failed to upload file (${response.status})`);
  }

  return response.json();
}

/**
 * Upload multiple CSV files (loops through single file upload)
 */
export async function uploadFiles(files: File[]): Promise<{ success: boolean; files: FileInfo[] }> {
  if (!files || files.length === 0) {
    return { success: false, files: [] };
  }

  const uploadedFiles: FileInfo[] = [];
  const errors: string[] = [];

  // Upload each file individually using single file upload endpoint
  for (const file of files) {
    try {
      console.log(`[uploadFiles] Uploading file: ${file.name}`);
      const response = await uploadFile(file);
      
      if (response.success && response.file) {
        uploadedFiles.push(response.file);
        console.log(`[uploadFiles] Successfully uploaded: ${file.name}`);
      }
    } catch (error: any) {
      console.error(`[uploadFiles] Failed to upload ${file.name}:`, error);
      errors.push(`${file.name}: ${error.message || 'Upload failed'}`);
    }
  }

  if (uploadedFiles.length === 0) {
    throw new Error(errors.length > 0 ? errors.join('; ') : 'All files failed to upload');
  }

  return {
    success: true,
    files: uploadedFiles
  };
}

/**
 * Get file information
 */
export async function getFileInfo(fileId: string): Promise<FileInfo> {
  const response = await fetch(`${API_BASE_URL}/files/${fileId}`);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Failed to get file info' }));
    throw new Error(error.error || error.message || 'Failed to get file info');
  }

  const data = await response.json();
  return data.file;
}

/**
 * List all files
 */
export async function listFiles(): Promise<FileInfo[]> {
  const response = await fetch(`${API_BASE_URL}/files`);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Failed to list files' }));
    throw new Error(error.error || error.message || 'Failed to list files');
  }

  const data = await response.json();
  return data.files || [];
}

/**
 * Delete a file
 */
export async function deleteFile(fileId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/files/${fileId}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Failed to delete file' }));
    throw new Error(error.error || error.message || 'Failed to delete file');
  }
}

/**
 * Send query and get both LLM and sandbox responses
 */
export async function sendQuery(request: QueryRequest): Promise<QueryResponse> {
  // Set timeout to 300 seconds for agentic LLM + sandbox workflows.
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 300000);

  // Try without trailing slash first, then with trailing slash if 405 error
  const tryRequest = async (url: string): Promise<Response> => {
    const requestBody = JSON.stringify(request);
    console.log(`[sendQuery] Sending POST request to: ${url}`, {
      method: 'POST',
      url: url,
      body: request,
      hasBody: !!requestBody
    });
    
    // Create request with explicit POST method
    const fetchOptions: RequestInit = {
      method: 'POST', // CRITICAL: Must be POST, not GET
      headers: {
        'Content-Type': 'application/json',
      },
      body: requestBody,
      signal: controller.signal,
    };
    
    // Double-check method is POST
    if (fetchOptions.method !== 'POST') {
      throw new Error('FATAL: Request method is not POST!');
    }
    
    console.log('[sendQuery] Fetch options:', {
      method: fetchOptions.method,
      hasBody: !!fetchOptions.body,
      url: url
    });
    
    return fetch(url, fetchOptions);
  };

  try {
    // Try without trailing slash first (backend route is @router.post(""))
    let response = await tryRequest(`${API_BASE_URL}/query`);

    // If 404 or 405, try with trailing slash (fallback for old backend)
    if (response.status === 404 || response.status === 405) {
      console.warn(`Received ${response.status} for /query, retrying with trailing slash`);
      response = await tryRequest(`${API_BASE_URL}/query/`);
    }

    clearTimeout(timeoutId);

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Query failed' }));
      throw new Error(error.error || error.message || `Failed to process query (status: ${response.status})`);
    }

    return response.json();
  } catch (error: any) {
    clearTimeout(timeoutId);
    if (error.name === 'AbortError') {
      throw new Error('Request timeout: The query took more than 5 minutes. Please try a faster model, a simpler question, or a smaller dataset.');
    }
    throw error;
  }
}

/**
 * Send a query through the SSE endpoint and surface real LangGraph node events.
 */
export async function sendQueryStream(
  request: QueryRequest,
  onProgress: (event: AgentProgressEvent) => void,
): Promise<QueryResponse> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 300000);

  try {
    const response = await fetch(`${API_BASE_URL}/query/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify(request),
      signal: controller.signal,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Failed to start analysis stream' }));
      throw new Error(error.detail || error.error || error.message || `Failed to start analysis (${response.status})`);
    }
    if (!response.body) {
      throw new Error('The browser did not expose the analysis response stream.');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalResponse: QueryResponse | null = null;

    const processBlock = (block: string) => {
      let eventName = 'message';
      const dataLines: string[] = [];
      for (const line of block.split(/\r?\n/)) {
        if (line.startsWith('event:')) eventName = line.slice(6).trim();
        if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
      }
      if (dataLines.length === 0) return;
      const payload = JSON.parse(dataLines.join('\n'));
      if (eventName === 'progress') {
        onProgress(payload as AgentProgressEvent);
      } else if (eventName === 'result') {
        finalResponse = payload as QueryResponse;
      } else if (eventName === 'error') {
        throw new Error(payload.message || 'The analysis workflow failed.');
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const blocks = buffer.split(/\r?\n\r?\n/);
      buffer = blocks.pop() || '';
      for (const block of blocks) {
        if (block.trim()) processBlock(block);
      }
      if (done) break;
    }
    if (buffer.trim()) processBlock(buffer);
    if (!finalResponse) {
      throw new Error('The analysis stream ended before returning a verified result.');
    }
    return finalResponse;
  } catch (error: any) {
    if (error.name === 'AbortError') {
      throw new Error('分析超过 5 分钟，已停止等待。请尝试更快的模型、更简单的问题或更小的数据集。');
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

// New: User interface request and response
export interface AskUserRequest {
  question: string;
  csv_id: string;
  model: string;
  prompt_style: string; // zero, zero_cot, sub_question
}

export interface AskUserResponse {
  success: boolean;
  final_answer: string;
  model: string;
  prompt: string;
  code?: string;
  thinking_process?: string;  // Add thinking process field
  execution_result?: {
    stdout: string;
    error: string;
    exec_time?: number;
  };
}

// New: Developer evaluation interface request and response
export interface DevEvalRequest {
  question: string;
  csv_id: string;
  models: string[];
  prompts: string[];
}

export interface DevEvalResult {
  model: string;
  prompt_style: string;
  prompt: string;
  code: string;
  stdout: string;
  error: string;
  exec_time: number;
  status: string;
  output?: any;
  score: number;
}

export interface DevEvalResponse {
  success: boolean;
  results: DevEvalResult[];
  leaderboard: DevEvalResult[];
  heatmap: Record<string, Record<string, number>>;
  best: DevEvalResult | null;
  summary: {
    total_combinations: number;
    successful: number;
    failed: number;
    average_score: number;
  };
}

/**
 * User interface: Send query and get results
 * Note: Backend only supports /api/query endpoint with question and fileIds
 */
export async function askUser(request: AskUserRequest): Promise<AskUserResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 120000);

  // Convert to backend format: backend supports question, fileIds, and prompt_style
  const backendRequest = {
    question: request.question,
    fileIds: [request.csv_id], // Convert csv_id to fileIds array
    model: request.model,
    prompt_style: request.prompt_style || "zero",  // Pass prompt_style to backend
    mode: "agent" as const,
  };

  const requestUrl = `${API_BASE_URL}/query`;
  console.log('[askUser] Request URL:', requestUrl);
  console.log('[askUser] API_BASE_URL:', API_BASE_URL);
  console.log('[askUser] Request with prompt_style:', backendRequest);

  try {
    const response = await fetch(requestUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(backendRequest),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Request failed' }));
      throw new Error(error.error || error.message || `Failed to process query (status: ${response.status})`);
    }

    // Convert backend response to AskUserResponse format
    const backendResponse = await response.json();
    
    // Debug: Print full backend response
    console.log('[askUser] Full backend response:', backendResponse);
    console.log('[askUser] sandboxResponse:', backendResponse.sandboxResponse);
    console.log('[askUser] thinking_process:', backendResponse.sandboxResponse?.thinking_process);
    
    return {
      success: backendResponse.success,
      final_answer: backendResponse.llmResponse?.content || '',
      model: request.model, // Return requested model (not from backend)
      prompt: '', // Backend doesn't return prompt
      code: backendResponse.sandboxResponse?.code,
      thinking_process: backendResponse.sandboxResponse?.thinking_process || '',  // Add thinking process
      execution_result: {
        stdout: backendResponse.sandboxResponse?.content || '',
        error: backendResponse.sandboxResponse?.status === 'error' ? backendResponse.sandboxResponse?.content || '' : '',
        exec_time: undefined,
      },
    };
  } catch (error: any) {
    clearTimeout(timeoutId);
    if (error.name === 'AbortError') {
      throw new Error('Request timeout: The query took too long to process.');
    }
    throw error;
  }
}

/**
 * Developer evaluation interface: Batch execute all combinations
 * This function will execute all model × prompt combinations sequentially
 */
export async function devEval(request: DevEvalRequest): Promise<DevEvalResponse> {
  const timeoutId = setTimeout(() => {
    throw new Error('Request timeout: The evaluation took too long to process.');
  }, 600000); // 10 minute timeout

  const requestUrl = `${API_BASE_URL}/query`;
  console.log('[devEval] Starting batch evaluation for', request.models.length, 'models ×', request.prompts.length, 'prompts');
  console.log('[devEval] Total combinations:', request.models.length * request.prompts.length);

  const results: DevEvalResult[] = [];

  try {
    // Execute all combinations sequentially
    for (const model of request.models) {
      for (const promptStyle of request.prompts) {
        const combinationStartTime = Date.now();
        console.log(`[devEval] Executing: ${model} + ${promptStyle}`);

        try {
          const backendRequest = {
            question: request.question,
            fileIds: [request.csv_id],
            model,
            prompt_style: promptStyle,
            mode: "agent" as const,
          };

          const response = await fetch(requestUrl, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify(backendRequest),
          });

          if (!response.ok) {
            const error = await response.json().catch(() => ({ error: 'Request failed' }));
            throw new Error(error.error || error.message || `Failed to process query (status: ${response.status})`);
          }

          const backendResponse = await response.json();
          const execTime = (Date.now() - combinationStartTime) / 1000;

          const result: DevEvalResult = {
            model: model,
            prompt_style: promptStyle,
            prompt: '', // Backend doesn't return prompt
            code: backendResponse.sandboxResponse?.code || '',
            stdout: backendResponse.sandboxResponse?.content || '',
            error: backendResponse.sandboxResponse?.status === 'error' ? backendResponse.sandboxResponse?.content || '' : '',
            exec_time: execTime,
            status: backendResponse.sandboxResponse?.status || 'success',
            output: backendResponse.sandboxResponse?.output,
            // Calculate score: 100 for success, 0 for error
            score: backendResponse.sandboxResponse?.status === 'success' ? 100 : 0,
          };

          results.push(result);
          console.log(`[devEval] Completed: ${model} + ${promptStyle} (${execTime.toFixed(2)}s, score: ${result.score})`);
        } catch (error: any) {
          const execTime = (Date.now() - combinationStartTime) / 1000;
          console.error(`[devEval] Failed: ${model} + ${promptStyle}`, error);
          
          const failedResult: DevEvalResult = {
            model: model,
            prompt_style: promptStyle,
            prompt: '',
            code: '',
            stdout: '',
            error: error.message || 'Execution failed',
            exec_time: execTime,
            status: 'error',
            output: undefined,
            score: 0,
          };
          results.push(failedResult);
        }
      }
    }

    clearTimeout(timeoutId);

    // Build heatmap
    const heatmap: Record<string, Record<string, number>> = {};
    for (const model of request.models) {
      heatmap[model] = {};
      for (const promptStyle of request.prompts) {
        const result = results.find(r => r.model === model && r.prompt_style === promptStyle);
        heatmap[model][promptStyle] = result?.score || 0;
      }
    }

    // Sort leaderboard by score (descending), then by execution time (ascending) if scores are equal
    const leaderboard = [...results].sort((a, b) => {
      // First sort by score (descending - higher score first)
      if (b.score !== a.score) {
        return b.score - a.score;
      }
      // If scores are equal, sort by execution time (ascending - shorter time first)
      return a.exec_time - b.exec_time;
    });

    // Find best result
    const best = leaderboard.length > 0 ? leaderboard[0] : null;

    // Calculate summary
    const successful = results.filter(r => r.status === 'success').length;
    const failed = results.filter(r => r.status === 'error').length;
    const averageScore = results.length > 0 
      ? results.reduce((sum, r) => sum + r.score, 0) / results.length 
      : 0;

    console.log('[devEval] Batch evaluation completed:', {
      total: results.length,
      successful,
      failed,
      averageScore: averageScore.toFixed(2),
    });

    return {
      success: true,
      results: results,
      leaderboard: leaderboard,
      heatmap: heatmap,
      best: best,
      summary: {
        total_combinations: results.length,
        successful: successful,
        failed: failed,
        average_score: averageScore,
      },
    };
  } catch (error: any) {
    clearTimeout(timeoutId);
    if (error.name === 'AbortError' || error.message?.includes('timeout')) {
      throw new Error('Request timeout: The evaluation took too long to process.');
    }
    throw error;
  }
}
