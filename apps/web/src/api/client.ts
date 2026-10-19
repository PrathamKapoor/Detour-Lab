/**
 * Typed API client.
 *
 * Contract rules honoured here:
 *  - every failure surfaces as `ApiError` carrying the backend's flat envelope
 *    (`code`, `message`, `details`) plus the HTTP status - nothing is swallowed;
 *  - requests accept an `AbortSignal` so navigation cancels stale work;
 *  - responses are validated for shape before use; a malformed payload raises a
 *    clear error instead of crashing a component deep in the tree;
 *  - the base URL comes from configuration (`VITE_API_BASE_URL`, defaulting to a
 *    same-origin `/api` proxy) - no hardcoded production host.
 */

import { normaliseAnalysisResult } from './normalize'
import type {
  ApiErrorBody,
  InterventionCatalog,
  OptimizationSearchList,
  OptimizationSearchRequest,
  PromotionRequest,
  PromotionResult,
  RunSummary,
  SearchOutcome,
  StoredRunSummary,
  EvaluateResponse,
  HealthResponse,
  ManifestResponse,
  Project,
  ProjectGraph,
  RunResponse,
  RuleSetResponse,
  ScenarioEdit,
  ScenarioList,
  ScenarioListResponse,
  PhaseGraphResponse,
  ScenarioRunList,
  ScenarioTimeline,
} from './types'

export const DEFAULT_TIMEOUT_MS = 20_000

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly details: Record<string, unknown>
  readonly requestId: string

  constructor(status: number, body: Partial<ApiErrorBody>, fallback: string) {
    super(body.message ?? fallback)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code ?? `HTTP_${status}`
    this.details = body.details ?? {}
    this.requestId = body.request_id ?? 'n/a'
  }

  /** True when the scenario was changed by someone else (HTTP 409). */
  get isRevisionConflict(): boolean {
    return this.status === 409
  }

  get isNotFound(): boolean {
    return this.status === 404
  }

  get isValidation(): boolean {
    return this.status === 422 || this.status === 400
  }

  /** Concise, user-facing text. Never a stack trace. */
  get userMessage(): string {
    switch (this.code) {
      case 'NETWORK_UNREACHABLE':
        return 'Cannot reach the analysis service. Check that the backend is running, then retry.'
      case 'REQUEST_TIMEOUT':
        return 'The analysis service did not respond in time. Retry or check the backend logs.'
      case 'REQUEST_ABORTED':
        return 'Request cancelled.'
      case 'REVISION_CONFLICT':
        return 'This scenario changed since you loaded it. Reload it, then reapply your edit.'
      case 'NOT_FOUND':
        return 'The requested item no longer exists on the server.'
      default:
        return this.message
    }
  }
}

export interface GraphEditPayload {
  expected_revision: number
  edits: ScenarioEdit[]
  note?: string
}

export interface ApiClientOptions {
  baseUrl?: string
  timeoutMs?: number
  fetchImpl?: typeof fetch
}

function resolveBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL
  if (typeof configured === 'string' && configured.length > 0) return configured.replace(/\/$/, '')
  return '' // same-origin: Vite proxies /api to the local backend
}

export interface RequestOptions {
  method?: string | undefined
  body?: string | undefined
  headers?: Record<string, string> | undefined
  signal?: AbortSignal | null | undefined
}

export class ApiClient {
  /** Resolved API base URL; empty means "same origin", which Vite proxies. */
  readonly baseUrl: string
  private readonly timeoutMs: number
  private readonly fetchImpl: typeof fetch

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? resolveBaseUrl()
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis)
  }

  private async request<T>(path: string, init: RequestOptions = {}): Promise<T> {
    const controller = new AbortController()
    const externalSignal = init.signal ?? undefined
    const timeout = setTimeout(() => controller.abort(new DOMException('timeout', 'TimeoutError')), this.timeoutMs)
    const onExternalAbort = () => controller.abort(externalSignal?.reason)
    if (externalSignal) {
      if (externalSignal.aborted) controller.abort(externalSignal.reason)
      else externalSignal.addEventListener('abort', onExternalAbort, { once: true })
    }

    let response: Response
    try {
      const fetchInit: RequestInit = {
        signal: controller.signal,
        headers: {
          Accept: 'application/json',
          ...(init.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
          ...(init.headers ?? {}),
        },
        ...(init.method !== undefined ? { method: init.method } : {}),
        ...(init.body !== undefined ? { body: init.body } : {}),
      }
      response = await this.fetchImpl(`${this.baseUrl}${path}`, fetchInit)
    } catch {
      if (externalSignal?.aborted) throw new ApiError(0, { code: 'REQUEST_ABORTED' }, 'Request cancelled')
      if (controller.signal.aborted) throw new ApiError(0, { code: 'REQUEST_TIMEOUT' }, 'Request timed out')
      throw new ApiError(0, { code: 'NETWORK_UNREACHABLE' }, 'Network request failed', )
    } finally {
      clearTimeout(timeout)
      if (externalSignal) externalSignal.removeEventListener('abort', onExternalAbort)
    }

    const text = await response.text()
    const payload = text.length > 0 ? safeParse(text) : null

    if (!response.ok) {
      const body = (payload ?? {}) as Partial<ApiErrorBody>
      throw new ApiError(response.status, body, `Request to ${path} failed with ${response.status}`)
    }
    if (payload === null) {
      throw new ApiError(response.status, { code: 'EMPTY_RESPONSE' }, 'The server returned an empty body')
    }
    return payload as T
  }

  // ------------------------------------------------------------------ routes
  health(signal?: AbortSignal): Promise<HealthResponse> {
    return this.request<HealthResponse>('/api/v1/health', { signal })
  }

  listProjects(signal?: AbortSignal): Promise<{ projects: Project[] }> {
    return this.request<{ projects: Project[] }>('/api/v1/projects', { signal })
  }

  createProject(payload: Record<string, unknown>, signal?: AbortSignal): Promise<Project> {
    return this.request<Project>('/api/v1/projects', {
      method: 'POST',
      body: JSON.stringify(payload),
      signal,
    })
  }

  getGraph(projectId: string, signal?: AbortSignal): Promise<ProjectGraph> {
    return this.request<ProjectGraph>(`/api/v1/projects/${encodeURIComponent(projectId)}/graph`, { signal })
  }

  listScenarios(projectId: string, signal?: AbortSignal): Promise<ScenarioListResponse> {
    return this.request<ScenarioListResponse>(
      `/api/v1/projects/${encodeURIComponent(projectId)}/scenarios`,
      { signal },
    )
  }

  getScenario(scenarioId: string, signal?: AbortSignal): Promise<ScenarioList> {
    return this.request<ScenarioList>(`/api/v1/scenarios/${encodeURIComponent(scenarioId)}`, { signal })
  }

  /** Creates a new scenario (used for immutable branches). */
  createScenario(projectId: string, payload: Record<string, unknown>, signal?: AbortSignal): Promise<ScenarioList> {
    return this.request<ScenarioList>(`/api/v1/projects/${encodeURIComponent(projectId)}/scenarios`, {
      method: 'POST',
      body: JSON.stringify(payload),
      signal,
    })
  }

  listScenarioRuns(scenarioId: string, signal?: AbortSignal): Promise<ScenarioRunList> {
    return this.request<ScenarioRunList>(`/api/v1/scenarios/${encodeURIComponent(scenarioId)}/runs`, { signal })
  }

  patchScenario(scenarioId: string, payload: GraphEditPayload, signal?: AbortSignal): Promise<ScenarioList> {
    return this.request<ScenarioList>(`/api/v1/scenarios/${encodeURIComponent(scenarioId)}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
      signal,
    })
  }

  evaluate(
    scenarioId: string,
    payload: { profile_id: string; phase_id: string; evaluation_instant?: string },
    signal?: AbortSignal,
  ): Promise<EvaluateResponse> {
    return this.request<{ run: RunSummary; result: unknown }>(
      `/api/v1/scenarios/${encodeURIComponent(scenarioId)}/evaluate`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
        signal,
      },
    ).then((response) => ({
      run: response.run,
      result: withNormalisedResult(response.result),
    }))
  }

  /** Ordered construction timeline; ordering comes from `Phase.order`. */
  getTimeline(scenarioId: string, signal?: AbortSignal): Promise<ScenarioTimeline> {
    return this.request<ScenarioTimeline>(
      `/api/v1/scenarios/${encodeURIComponent(scenarioId)}/timeline`,
      { signal },
    )
  }

  /** The authoritative materialised graph of one phase. */
  getPhaseGraph(scenarioId: string, phaseId: string, signal?: AbortSignal): Promise<PhaseGraphResponse> {
    return this.request<PhaseGraphResponse>(
      `/api/v1/scenarios/${encodeURIComponent(scenarioId)}/phases/${encodeURIComponent(phaseId)}/graph`,
      { signal },
    )
  }

  /**
 * Creates an independent branch of an existing scenario.
 *
 * The source is read, never written: its phases, origins/destinations and
 * temporary edges are copied into a new scenario identity, so the branch has its
 * own revision history and content hash. Edits are intentionally **not**
 * copied - a branch starts from the declared construction plan.
 */
async createBranchFrom(
    projectId: string,
    sourceScenarioId: string,
    newScenarioId: string,
    name: string,
    signal?: AbortSignal,
  ): Promise<ScenarioList> {
    const source = await this.getScenario(sourceScenarioId, signal)
    return this.createScenario(
      projectId,
      {
        id: newScenarioId,
        name,
        parent_scenario_id: source.id,
        base_graph_version_id: source.base_graph_version_id,
        phases: source.phases,
        origins_destinations: source.origins_destinations,
        temporary_edges: source.temporary_edges,
        note: `Branch of ${source.id} at revision ${source.revision}.`,
      },
      signal,
    )
  }

  getRun(runId: string, signal?: AbortSignal): Promise<RunResponse> {
    return this.request<{ run: StoredRunSummary; result: unknown }>(
      `/api/v1/runs/${encodeURIComponent(runId)}`,
      { signal },
    ).then((response) => ({
      run: response.run,
      result: withNormalisedResult(response.result),
    }))
  }

  getManifest(runId: string, signal?: AbortSignal): Promise<ManifestResponse> {
    return this.request<ManifestResponse>(`/api/v1/runs/${encodeURIComponent(runId)}/manifest`, { signal })
  }

  rulesets(signal?: AbortSignal): Promise<RuleSetResponse> {
    return this.request<RuleSetResponse>('/api/v1/rulesets', { signal })
  }

  // ------------------------------------------------------------ Fix This Plan
  /** The bundled intervention library as applicable to one phase. */
  listInterventions(
    scenarioId: string,
    phaseId: string,
    signal?: AbortSignal,
  ): Promise<InterventionCatalog> {
    const query = `?phase_id=${encodeURIComponent(phaseId)}`
    return this.request<InterventionCatalog>(
      `/api/v1/scenarios/${encodeURIComponent(scenarioId)}/optimization/interventions${query}`,
      { signal },
    )
  }

  /** Runs one bounded search; the response is the stored payload. */
  startOptimizationSearch(
    scenarioId: string,
    payload: OptimizationSearchRequest,
    signal?: AbortSignal,
  ): Promise<SearchOutcome> {
    return this.request<SearchOutcome>(
      `/api/v1/scenarios/${encodeURIComponent(scenarioId)}/optimization/search`,
      { method: 'POST', body: JSON.stringify(payload), signal },
    )
  }

  listOptimizationSearches(scenarioId: string, signal?: AbortSignal): Promise<OptimizationSearchList> {
    return this.request<OptimizationSearchList>(
      `/api/v1/scenarios/${encodeURIComponent(scenarioId)}/optimization/searches`,
      { signal },
    )
  }

  /** One stored search payload, for deterministic replay. */
  getOptimizationSearch(searchId: string, signal?: AbortSignal): Promise<SearchOutcome> {
    return this.request<SearchOutcome>(
      `/api/v1/optimization/searches/${encodeURIComponent(searchId)}`,
      { signal },
    )
  }

  /** Applies one candidate to a new scenario branch; the server re-verifies it. */
  promoteProposal(payload: PromotionRequest, signal?: AbortSignal): Promise<PromotionResult> {
    return this.request<PromotionResult>('/api/v1/optimization/promote', {
      method: 'POST',
      body: JSON.stringify(payload),
      signal,
    })
  }
}

function safeParse(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

/**
 * Shape validation at the boundary: a payload that is not a recognisable analysis
 * result is surfaced as an explicit error, not as an empty dashboard.
 */
function withNormalisedResult(raw: unknown) {
  try {
    return normaliseAnalysisResult(raw)
  } catch (error) {
    throw new ApiError(
      200,
      { code: 'MALFORMED_RESPONSE', message: error instanceof Error ? error.message : 'Malformed response' },
      'The analysis service returned a payload this client cannot read',
    )
  }
}

export const api = new ApiClient()