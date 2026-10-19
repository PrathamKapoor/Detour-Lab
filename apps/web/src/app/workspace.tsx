import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import type { ApiClient} from '@/api/client';
import { ApiError } from '@/api/client'
import type {
  ManifestResponse,
  NormalisedAnalysisResult,
  PhaseGraphResponse,
  PhaseTimelineEntry,
  Project,
  ProjectGraph,
  RuleSetResponse,
  ScenarioEdit,
  ScenarioList,
  ScenarioSummary,
  ScenarioTimeline,
  StoredRunSummary,
} from '@/api/types'
import { useResource } from '@/lib/useResource'

export type ViewId =
  | 'projects'
  | 'network'
  | 'scenario'
  | 'analysis'
  | 'evidence'
  | 'phases'
  | 'optimization'
  | 'failure-lab'
  | 'branches'
  | 'compare'
  | 'reports'

export interface RunSnapshot {
  run: StoredRunSummary
  result: NormalisedAnalysisResult
}

export interface WorkspaceState {
  api: ApiClient
  /* resources ---------------------------------------------------------- */
  projects: { data: { projects: Project[] } | null; error: ApiError | null; loading: boolean }
  graph: ProjectGraph | null
  graphError: ApiError | null
  graphLoading: boolean
  reloadGraph: () => void
  rulesets: RuleSetResponse | null
  /* selection ---------------------------------------------------------- */
  projectId: string | null
  selectProject: (projectId: string) => void
  scenarioId: string | null
  selectScenario: (scenarioId: string) => void
  scenarios: readonly ScenarioSummary[]
  reloadScenarios: () => void
  scenario: ScenarioList | null
  scenarioError: ApiError | null
  scenarioLoading: boolean
  scenarioSummary: { id: string; name: string; revision: number; edit_count: number } | null
  reloadScenario: () => void
  selectedEdgeId: string | null
  selectedNodeId: string | null
  selectEdge: (edgeId: string | null) => void
  selectNode: (nodeId: string | null) => void
  /* analysis ----------------------------------------------------------- */
  profileId: string
  phaseId: string
  setProfileId: (id: string) => void
  setPhaseId: (id: string) => void
  evaluationInstant: string
  setEvaluationInstant: (value: string) => void
  current: RunSnapshot | null
  baseline: RunSnapshot | null
  running: boolean
  runError: ApiError | null
  runAnalysis: () => Promise<void>
  promoteToBaseline: () => void
  stale: boolean
  /* scenario editing --------------------------------------------------- */
  pendingEdits: ScenarioEdit[]
  isDirty: boolean
  addEdit: (edit: ScenarioEdit) => void
  removeEdit: (index: number) => void
  discardEdits: () => void
  saveEdits: () => Promise<void>
  saveError: ApiError | null
  conflict: { expected: number; actual: number } | null
  resolveConflictByReload: () => void
  saving: boolean
  /* branching ---------------------------------------------------------- */
  createBranch: (input: { phaseId: string; reopenEdgeId: string }) => Promise<void>
  branchError: ApiError | null
  branching: boolean
  /* reporting ---------------------------------------------------------- */
  manifest: ManifestResponse | null
  manifestError: ApiError | null
  loadManifest: (runId: string) => Promise<void>
  /* phase timeline (Gate 4) ---------------------------------------------- */
  timeline: ScenarioTimeline | null
  timelineLoading: boolean
  timelineError: ApiError | null
  reloadTimeline: () => void
  orderedPhases: readonly PhaseTimelineEntry[]
  selectedPhaseId: string | null
  selectPhase: (phaseId: string) => void
  phaseGraph: PhaseGraphResponse | null
  phaseGraphLoading: boolean
  phaseGraphError: ApiError | null
  /** Per-phase analysis results, keyed by phase id. Absent means not evaluated. */
  phaseResults: Readonly<Record<string, NormalisedAnalysisResult>>
  phaseRuns: Readonly<Record<string, StoredRunSummary>>
  evaluateAllPhases: () => Promise<void>
  evaluatingPhases: Readonly<Record<string, 'running' | 'done' | 'failed'>>
  batchError: ApiError | null
  evaluatePhase: (phaseId: string) => Promise<void>
  /** Active closure/temporary set of a phase, for temporal comparison. */
  graphFor: (phaseId: string) => { closed: readonly string[]; temporary: readonly string[] } | null
  /* navigation --------------------------------------------------------- */
  view: ViewId
  setView: (view: ViewId) => void
}

const WorkspaceContext = createContext<WorkspaceState | null>(null)

export function useWorkspace(): WorkspaceState {
  const value = useContext(WorkspaceContext)
  if (!value) throw new Error('useWorkspace must be used inside <WorkspaceProvider>')
  return value
}

const DEMO_EVALUATION_INSTANT = '2026-03-01T00:00:00Z'

export function WorkspaceProvider({ children, api }: { children: ReactNode; api: ApiClient }) {
  const [projectId, setProjectId] = useState<string | null>(null)
  const [scenarioId, setScenarioId] = useState<string | null>(null)
  const [scenarioSummary, setScenarioSummary] = useState<WorkspaceState['scenarioSummary']>(null)
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [profileId, setProfileId] = useState('DEMO_PROFILE_MANUAL_WHEELCHAIR')
  const [phaseId, setPhaseId] = useState('phase-1')
  const [evaluationInstant, setEvaluationInstant] = useState(DEMO_EVALUATION_INSTANT)
  const [current, setCurrent] = useState<RunSnapshot | null>(null)
  const [baseline, setBaseline] = useState<RunSnapshot | null>(null)
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState<ApiError | null>(null)
  const [pendingEdits, setPendingEdits] = useState<ScenarioEdit[]>([])
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<ApiError | null>(null)
  const [conflict, setConflict] = useState<{ expected: number; actual: number } | null>(null)
  const [manifest, setManifest] = useState<ManifestResponse | null>(null)
  const [manifestError, setManifestError] = useState<ApiError | null>(null)
  const [branchError, setBranchError] = useState<ApiError | null>(null)
  const [branching, setBranching] = useState(false)
  const [view, setView] = useState<ViewId>('projects')
  const [selectedPhaseId, setSelectedPhaseId] = useState<string | null>(null)
  const [phaseResults, setPhaseResults] = useState<Record<string, NormalisedAnalysisResult>>({})
  const [phaseRuns, setPhaseRuns] = useState<Record<string, StoredRunSummary>>({})
  const [evaluatingPhases, setEvaluatingPhases] = useState<Record<string, 'running' | 'done' | 'failed'>>(
    {},
  )
  const [batchError, setBatchError] = useState<ApiError | null>(null)

  const projects = useResource((signal) => api.listProjects(signal), [api])
  const rulesets = useResource((signal) => api.rulesets(signal), [api])

  // Seed the workspace from the backend's own project list.
  const projectList = useMemo(() => projects.data?.projects ?? [], [projects.data])
  useEffect(() => {
    if (!projectId && projectList.length > 0) {
      setProjectId(projectList[0]!.id)
    }
  }, [projectId, projectList])

  const graph = useResource(
    (signal) => api.getGraph(projectId as string, signal),
    [api, projectId],
    { enabled: Boolean(projectId) },
  )

  const scenarioList = useResource(
    (signal) => api.listScenarios(projectId as string, signal),
    [api, projectId],
    { enabled: Boolean(projectId) },
  )
  const scenarioEntries = useMemo(() => scenarioList.data?.scenarios ?? [], [scenarioList.data])
  // Adopt a default scenario only when nothing is selected yet. An explicit
  // selection must never be overridden by a list that has not refreshed yet.
  useEffect(() => {
    if (scenarioEntries.length === 0 || scenarioId !== null) return
    setScenarioId(scenarioEntries[0]!.id)
  }, [scenarioEntries, scenarioId])

  const scenario = useResource(
    (signal) => api.getScenario(scenarioId as string, signal),
    [api, scenarioId],
    { enabled: Boolean(scenarioId) },
  )

  const loadedScenario = scenario.data
  useEffect(() => {
    if (!loadedScenario) return
    setScenarioSummary({
      id: loadedScenario.id,
      name: loadedScenario.name,
      revision: loadedScenario.revision,
      edit_count: loadedScenario.edits.length,
    })
  }, [loadedScenario])

  const stale = useMemo(() => {
    if (!current || !loadedScenario) return false
    return current.run.scenario_revision !== loadedScenario.revision || pendingEdits.length > 0
  }, [current, loadedScenario, pendingEdits])

  const runAnalysis = useCallback(async () => {
    if (!scenarioId) return
    setRunning(true)
    setRunError(null)
    try {
      const response = await api.evaluate(scenarioId, {
        profile_id: profileId,
        phase_id: phaseId,
        evaluation_instant: evaluationInstant,
      })
      setCurrent({
        run: response.run,
        result: response.result,
      })
    } catch (error) {
      setRunError(error instanceof ApiError ? error : new ApiError(0, { code: 'UNEXPECTED' }, String(error)))
    } finally {
      setRunning(false)
    }
  }, [api, scenarioId, profileId, phaseId, evaluationInstant])

  const promoteToBaseline = useCallback(() => {
    setBaseline((previous) => current ?? previous)
  }, [current])

  const addEdit = useCallback((edit: ScenarioEdit) => {
    setPendingEdits((previous) => [...previous, edit])
    setSaveError(null)
    setConflict(null)
  }, [])

  const removeEdit = useCallback((index: number) => {
    setPendingEdits((previous) => previous.filter((_, position) => position !== index))
  }, [])

  const discardEdits = useCallback(() => {
    setPendingEdits([])
    setSaveError(null)
    setConflict(null)
  }, [])

  const saveEdits = useCallback(async () => {
    if (!scenarioId || !loadedScenario || pendingEdits.length === 0) return
    setSaving(true)
    setSaveError(null)
    setConflict(null)
    try {
      const updated = await api.patchScenario(scenarioId, {
        expected_revision: loadedScenario.revision,
        edits: pendingEdits,
        note: 'Edited in the DETOUR LAB planning studio',
      })
      setPendingEdits([])
      scenario.setData(updated)
      scenarioList.reload()
      // Any previous result describes a revision that no longer exists.
      setCurrent(null)
    } catch (error) {
      const apiError = error instanceof ApiError ? error : new ApiError(0, { code: 'UNEXPECTED' }, String(error))
      setSaveError(apiError)
      if (apiError.isRevisionConflict) {
        const details = apiError.details as { actual_revision?: number }
        setConflict({
          expected: loadedScenario.revision,
          actual: typeof details.actual_revision === 'number' ? details.actual_revision : -1,
        })
      }
    } finally {
      setSaving(false)
    }
  }, [api, scenarioId, loadedScenario, pendingEdits, scenario, scenarioList])

  const resolveConflictByReload = useCallback(() => {
    setConflict(null)
    setPendingEdits([])
    scenario.reload()
  }, [scenario])

  /**
   * Reopening a closure cannot be an edit: the R0 API appends edits but never
   * rewrites a phase declaration, and the baseline is immutable. Reopening is
   * therefore expressed as an immutable branch scenario whose phase omits that
   * closure - the same discipline as applying an optimiser proposal (INV-07).
   */
  const createBranch = useCallback(
    async (input: { phaseId: string; reopenEdgeId: string }) => {
      if (!projectId || !loadedScenario) return
      setBranching(true)
      setBranchError(null)
      try {
        const phases = loadedScenario.phases.map((phase) =>
          phase.id === input.phaseId
            ? { ...phase, closed_edge_ids: (phase.closed_edge_ids ?? []).filter((id) => id !== input.reopenEdgeId) }
            : phase,
        )
        const created = await api.createScenario(
          projectId,
          {
            id: `${loadedScenario.id}--reopen-${input.reopenEdgeId.toLowerCase()}`,
            name: `Reopen ${input.reopenEdgeId} in ${input.phaseId}`,
            parent_scenario_id: loadedScenario.id,
            base_graph_version_id: loadedScenario.base_graph_version_id,
            phases,
            origins_destinations: loadedScenario.origins_destinations,
            temporary_edges: loadedScenario.temporary_edges,
            note: `Branch of ${loadedScenario.id} reopening ${input.reopenEdgeId} in ${input.phaseId}.`,
          },
        )
        scenarioList.reload()
        setScenarioId(created.id ?? '')
        setPendingEdits([])
        setCurrent(null)
        setBaseline(null)
      } catch (error) {
        setBranchError(
          error instanceof ApiError ? error : new ApiError(0, { code: 'UNEXPECTED' }, String(error)),
        )
      } finally {
        setBranching(false)
      }
    },
    [api, projectId, loadedScenario, scenarioList],
  )

  /**
 * Phase timeline and phase graph (Gate 4).
 *
 * Both are reads of authoritative backend state: the browser never derives which
 * edges are closed in a phase by toggling the base graph itself.
 */
const timeline = useResource(
  (signal) => api.getTimeline(scenarioId as string, signal),
  [api, scenarioId],
  { enabled: Boolean(scenarioId) },
)

const orderedPhases = useMemo(
  () => (timeline.data ? [...timeline.data.phases].sort((a, b) => a.order - b.order) : []),
  [timeline.data],
)

// Adopt the first scenario only while nothing is selected. An explicit choice is
// never overridden just because the refreshed list has not caught up yet - that
// would silently redirect an edit at a different scenario.
useEffect(() => {
  if (orderedPhases.length === 0) return
  if (selectedPhaseId === null) setSelectedPhaseId(orderedPhases[0]!.phase_id)
}, [orderedPhases, selectedPhaseId])

// A different scenario invalidates every per-phase result: they belong to the
// scenario revision they were produced from.
useEffect(() => {
  setPhaseResults({})
  setPhaseRuns({})
  setEvaluatingPhases({})
}, [scenarioId])

const phaseGraph = useResource(
  (signal) => api.getPhaseGraph(scenarioId as string, selectedPhaseId as string, signal),
  [api, scenarioId, selectedPhaseId],
  { enabled: Boolean(scenarioId && selectedPhaseId) },
)

const graphFor = useCallback(
  (phaseId: string) => {
    const entry = orderedPhases.find((phase) => phase.phase_id === phaseId)
    if (!entry) return null
    return { closed: entry.closed_edge_ids, temporary: entry.temporary_edge_ids }
  },
  [orderedPhases],
)

const evaluatePhase = useCallback(
  async (phaseId: string) => {
    if (!scenarioId) return
    setEvaluatingPhases((previous) => ({ ...previous, [phaseId]: 'running' }))
    try {
      const response = await api.evaluate(scenarioId, {
        profile_id: profileId,
        phase_id: phaseId,
        evaluation_instant: evaluationInstant,
      })
      setPhaseResults((previous) => ({ ...previous, [phaseId]: response.result }))
      setPhaseRuns((previous) => ({ ...previous, [phaseId]: response.run }))
      setEvaluatingPhases((previous) => ({ ...previous, [phaseId]: 'done' }))
    } catch (error) {
      setEvaluatingPhases((previous) => ({ ...previous, [phaseId]: 'failed' }))
      setBatchError(error instanceof ApiError ? error : new ApiError(0, { code: 'UNEXPECTED' }, String(error)))
    }
  },
  [api, scenarioId, profileId, evaluationInstant],
)

/**
 * Evaluate every ordered phase for the current profile.
 *
 * Phases are identified by their own id, never by request position, so a slow
 * response cannot be filed under the wrong phase. A partial failure is reported
 * per phase; the batch is never marked globally successful.
 */
const evaluateAllPhases = useCallback(async () => {
  if (!scenarioId) return
  setBatchError(null)
  setEvaluatingPhases(Object.fromEntries(orderedPhases.map((phase) => [phase.phase_id, 'running'])))
  const outcomes = await Promise.allSettled(
    orderedPhases.map((phase) =>
      api
        .evaluate(scenarioId, {
          profile_id: profileId,
          phase_id: phase.phase_id,
          evaluation_instant: evaluationInstant,
        })
        .then((response) => ({ phaseId: phase.phase_id, response })),
    ),
  )

  const results: Record<string, NormalisedAnalysisResult> = {}
  const runs: Record<string, StoredRunSummary> = {}
  const statuses: Record<string, 'running' | 'done' | 'failed'> = {}
  const failures: ApiError[] = []

  for (const outcome of outcomes) {
    if (outcome.status === 'fulfilled') {
      results[outcome.value.phaseId] = outcome.value.response.result
      runs[outcome.value.phaseId] = outcome.value.response.run
      statuses[outcome.value.phaseId] = 'done'
    } else {
      const error =
        outcome.reason instanceof ApiError
          ? outcome.reason
          : new ApiError(0, { code: 'UNEXPECTED' }, String(outcome.reason))
      failures.push(error)
    }
  }

  setPhaseResults((previous) => ({ ...previous, ...results }))
  setPhaseRuns((previous) => ({ ...previous, ...runs }))
  setEvaluatingPhases((previous) => ({
    ...previous,
    ...statuses,
    ...Object.fromEntries(failures.length > 0 ? orderedPhases.map((p) => [p.phase_id, 'failed' as const]) : []),
  }))
  if (failures.length > 0) setBatchError(failures[0]!)
}, [api, scenarioId, orderedPhases, profileId, evaluationInstant])

const loadManifest = useCallback(
    async (runId: string) => {
      setManifestError(null)
      try {
        setManifest(await api.getManifest(runId))
      } catch (error) {
        setManifest(null)
        setManifestError(
          error instanceof ApiError ? error : new ApiError(0, { code: 'UNEXPECTED' }, String(error)),
        )
      }
    },
    [api],
  )

  const value = useMemo<WorkspaceState>(
    () => ({
      api,
      projects: { data: projects.data, error: projects.error, loading: projects.loading },
      graph: graph.data,
      graphError: graph.error,
      graphLoading: graph.loading,
      reloadGraph: graph.reload,
      rulesets: rulesets.data,
      projectId,
      selectProject: (id) => {
        setProjectId(id)
        setScenarioId(null)
        setCurrent(null)
        setBaseline(null)
        setSelectedEdgeId(null)
        setSelectedNodeId(null)
      },
      scenarioId,
      selectScenario: (id) => {
        setScenarioId(id)
        setCurrent(null)
        setPendingEdits([])
      },
      scenarios: scenarioEntries,
      reloadScenarios: scenarioList.reload,
      scenario: scenario.data,
      scenarioError: scenario.error,
      scenarioLoading: scenario.loading,
      scenarioSummary,
      reloadScenario: scenario.reload,
      selectedEdgeId,
      selectedNodeId,
      selectEdge: setSelectedEdgeId,
      selectNode: setSelectedNodeId,
      profileId,
      phaseId,
      setProfileId,
      setPhaseId,
      evaluationInstant,
      setEvaluationInstant,
      current,
      baseline,
      running,
      runError,
      runAnalysis,
      promoteToBaseline,
      stale,
      pendingEdits,
      isDirty: pendingEdits.length > 0,
      addEdit,
      removeEdit,
      discardEdits,
      saveEdits,
      saveError,
      conflict,
      resolveConflictByReload,
      saving,
      createBranch,
      branchError,
      branching,
      manifest,
      manifestError,
      loadManifest,
      timeline: timeline.data,
      timelineLoading: timeline.loading,
      timelineError: timeline.error,
      reloadTimeline: timeline.reload,
      orderedPhases,
      selectedPhaseId,
      selectPhase: setSelectedPhaseId,
      phaseGraph: phaseGraph.data,
      phaseGraphLoading: phaseGraph.loading,
      phaseGraphError: phaseGraph.error,
      phaseResults,
      phaseRuns,
      evaluateAllPhases,
      evaluatePhase,
      graphFor,
      evaluatingPhases,
      batchError,
      view,
      setView,
    }),
    [
      api,
      projects.data,
      projects.error,
      projects.loading,
      graph.data,
      graph.error,
      graph.loading,
      graph.reload,
      rulesets.data,
      projectId,
      scenarioId,
      scenarioEntries,
      scenarioList.reload,
      scenario.data,
      scenario.error,
      scenario.loading,
      scenarioSummary,
      scenario.reload,
      selectedEdgeId,
      selectedNodeId,
      profileId,
      phaseId,
      evaluationInstant,
      setEvaluationInstant,
      current,
      baseline,
      running,
      runError,
      runAnalysis,
      promoteToBaseline,
      stale,
      pendingEdits,
      addEdit,
      removeEdit,
      discardEdits,
      saveEdits,
      saveError,
      conflict,
      resolveConflictByReload,
      saving,
      createBranch,
      branchError,
      branching,
      manifest,
      manifestError,
      loadManifest,
      timeline.data,
      timeline.loading,
      timeline.error,
      timeline.reload,
      orderedPhases,
      selectedPhaseId,
      phaseGraph.data,
      phaseGraph.loading,
      phaseGraph.error,
      phaseResults,
      phaseRuns,
      evaluateAllPhases,
      evaluatePhase,
      graphFor,
      evaluatingPhases,
      batchError,
      view,
    ],
  )

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
}