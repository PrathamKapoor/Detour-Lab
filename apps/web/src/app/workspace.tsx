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
  Project,
  ProjectGraph,
  RuleSetResponse,
  ScenarioEdit,
  ScenarioList,
  ScenarioSummary,
  StoredRunSummary,
} from '@/api/types'
import { useResource } from '@/lib/useResource'

export type ViewId = 'projects' | 'network' | 'scenario' | 'analysis' | 'evidence' | 'compare' | 'reports'

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
  useEffect(() => {
    if (scenarioEntries.length === 0) return
    const known = scenarioEntries.some((entry) => entry.id === scenarioId)
    if (!known) setScenarioId(scenarioEntries[0]!.id)
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
      view,
    ],
  )

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
}