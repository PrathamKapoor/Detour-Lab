// GENERATED FILE - do not edit by hand.
// Produced by detour_lab.reporting.contracts from the Pydantic domain models,
// which are the same contracts the API validates every request with.
//
// Regenerate with:  powershell -NoProfile -File scripts/generate-contracts.ps1

export interface AnalysisResult {
  scenario_id: string;
  scenario_hash: string;
  phase_id: string;
  profile_id: string;
  rulepack_id: string;
  rulepack_version: string;
  rulepack_hash: string;
  base_graph_version_id: string;
  base_graph_hash: string;
  phase_graph_id: string;
  phase_graph_hash: string;
  edge_evaluations: EdgeEvaluation[];
  verdicts: RuleVerdict[];
  od_results: ODPairResult[];
  counts: Record<string, number>;
  warnings?: string[];
}

export interface AttributeSpec {
  quantity: "length_m" | "width_mm" | "slope_percent" | "text";
  accepted_units?: string[];
  freshness?: FreshnessPolicy | null;
  description?: string;
}

export interface BaseGraphVersion {
  id: string;
  schema_version?: string;
  basis: CoordinateBasis;
  nodes: Node[];
  edges: Edge[];
  inactive_edge_ids?: string[];
  evidence?: EvidenceRecord[];
  source: DataSource;
  created_at?: string | null;
  content_hash?: string;
}

export interface BaselineOD {
  origin_id: string;
  destination_id: string;
  confirmed_reachable: boolean;
  possibly_reachable: boolean;
  confirmed_distance_m?: number | null;
  possible_distance_m?: number | null;
}

export interface BaselineProfile {
  profile_id: string;
  semantic_hash: string;
  phase_graph_id: string;
  phase_graph_hash: string;
  od_results: BaselineOD[];
}

export interface BudgetCheck {
  status: "not_requested" | "within" | "exceeds" | "cannot_certify_unknown_cost";
  budget_amount?: number | null;
  budget_currency?: string | null;
  basis?: string | null;
  detail?: string;
}

export interface CandidateAssumption {
  intervention_id: string;
  element_id: string;
  field: string;
  value_display: string;
  unit?: string | null;
  provenance_class: string;
  verification_status: string;
  note: string;
  requires_field_verification?: boolean;
}

export interface CandidateCostLine {
  intervention_id: string;
  cost_id: string;
  label: string;
  provenance: CostProvenance;
  currency: string;
  quantity: number;
  unit: string;
  total_nominal?: number | null;
  total_max?: number | null;
  note?: string;
}

export interface CandidateCostSummary {
  currency?: string | null;
  nominal?: number | null;
  maximum?: number | null;
  unknown?: boolean;
  mixed_currency?: boolean;
  provenance_notes?: string[];
  lines?: CandidateCostLine[];
}

export interface CandidateEvaluation {
  proposal: CandidateProposal;
  classification: "certified" | "requires_verification" | "no_improvement" | "rejected";
  intervention_ids: string[];
  intervention_count: number;
  restored_all_profiles?: string[];
  restored_any_profile?: string[];
  regressed_pairs?: string[];
  verifications: CandidateVerification[];
  assumptions?: CandidateAssumption[];
  applied_phase_changes?: Record<string, unknown>[];
  introduced_fail_verdict_count?: number;
  introduced_unknown_verdict_count?: number;
  cost: CandidateCostSummary;
  budget: BudgetCheck;
  preview_scenario_hash: string;
  preview_phase_graph_hash: string;
  rank?: number | null;
  pareto_optimal?: boolean;
  tie_group?: number | null;
  evaluation_failure?: Record<string, unknown> | null;
}

export interface CandidateProposal {
  proposal_id: string;
  intervention_ids: string[];
  eligible: boolean;
  rejection_reasons?: string[];
  restored_required_od?: boolean | null;
  requires_verification?: boolean;
  passed_profiles?: string[];
  failed_profiles?: string[];
  cost_nominal?: number | null;
  cost_max?: number | null;
  cost_unknown?: boolean;
  added_distance_m?: number | null;
  solver_status?: SolverStatus;
}

export interface CandidateVerification {
  profile_id: string;
  source_semantic_hash: string;
  candidate_semantic_hash: string;
  candidate_phase_graph_id: string;
  candidate_phase_graph_hash: string;
  od_transitions: ODTransition[];
  restored_pairs: string[];
  gained_possible_pairs: string[];
  regressed_pairs: string[];
  new_fail_verdicts: Record<string, string>[];
  new_unknown_verdicts: Record<string, string>[];
  added_distance_m?: number | null;
  comparable_route_count?: number;
}

export interface CoordinateBasis {
  kind: "local_planar_meters" | "wgs84_degrees";
  unit: "m" | "degree";
  local_origin_label?: string | null;
  crs_note?: string;
  projected_crs?: string | null;
}

export type CostProvenance = "demo_only" | "user_entered" | "sourced" | "unknown";

export interface DataSource {
  name: string;
  description?: string;
  license?: string;
  attribution?: string;
  url?: string | null;
  provenance_class: ProvenanceClass;
  version?: string | null;
  retrieved_at?: string | null;
}

export interface DomainSummary {
  eligible_intervention_ids: string[];
  excluded_interventions: ExcludedIntervention[];
  domain_combination_count: number;
  evaluated_count?: number;
  truncated_by?: ("candidate_limit" | "duration_limit")[];
  exhausted?: boolean;
  dependency_blocked?: Record<string, unknown>[];
  mutually_exclusive_blocked?: Record<string, unknown>[];
  precondition_rejected?: Record<string, unknown>[];
}

export interface Edge {
  id: string;
  u: string;
  v: string;
  geometry: Record<string, unknown>[][];
  length_m: number;
  edge_type?: EdgeType;
  name?: string;
  provenance_class?: ProvenanceClass;
  evidence_ids?: string[];
}

export interface EdgeEvaluation {
  edge_id: string;
  state: VerdictState;
  relevant_check_count: number;
  confirmed_eligible: boolean;
  possibly_eligible: boolean;
  unknown_only?: boolean;
  reason_codes?: ReasonCode[];
  verdict_ids?: string[];
  findings?: Finding[];
}

export type EdgeType = "sidewalk" | "crossing" | "temporary_path" | "shared_use_path" | "ramp";

export interface ElementStateChange {
  change: "element_added" | "element_removed" | "state_changed" | "evidence_added" | "evidence_masked";
  element_id: string;
  element_kind: "edge" | "node" | "evidence";
  phase_id: string;
  before_state?: VerdictState | null;
  after_state?: VerdictState | null;
  before_reason_codes?: ReasonCode[];
  after_reason_codes?: ReasonCode[];
  detail?: string;
}

export type EngineeringObservation = "confirmed_connectivity_preserved" | "confirmed_connectivity_gained" | "confirmed_connectivity_lost" | "confirmed_route_became_possible_only" | "possible_only_route_became_disconnected" | "new_known_rule_violation" | "new_unresolved_evidence_condition" | "no_relevant_modelled_change" | "analysis_unavailable";

export interface EvidenceConflictReport {
  element_id: string;
  attribute: string;
  resolution_status: ReasonCode;
  resolved: boolean;
  canonical_value?: number | string | boolean | null;
  canonical_unit?: string | null;
  explanation: string;
  observations?: ObservationComparison[];
  distinct_values?: string[];
  resolution_requirement: string;
  can_be_resolved_without_field_work: boolean;
  selected_value_note?: string;
}

export type EvidenceCriticality = "decision_blocking" | "decision_relevant" | "supporting";

export interface EvidenceIssue {
  issue_id: string;
  scope: string;
  resolution_status: ReasonCode;
  status_label: string;
  element_id: string;
  element_kind: "edge" | "node";
  element_name: string;
  attribute: string;
  edge_u?: string | null;
  edge_v?: string | null;
  edge_length_m?: number | null;
  edge_type?: string | null;
  node_x?: number | null;
  node_y?: number | null;
  node_type?: string | null;
  rule_ids?: string[];
  affected_profile_ids?: string[];
  affected_phase_ids?: string[];
  observations?: ObservationComparison[];
  evidence_record_ids?: string[];
  recorded_measurement?: string | null;
  missing_or_conflicting: string;
  investigation_target: string;
  od_pairs?: EvidenceIssuePair[];
  od_pair_count?: number;
  criticality: EvidenceCriticality;
  criticality_rationale?: string[];
  element_has_known_failure?: boolean;
  queue_state?: QueueState;
  dataset_notice?: string;
}

export interface EvidenceIssuePair {
  pair_id: string;
  origin_id: string;
  destination_id: string;
  profile_id: string;
  role: "blocking" | "relevant" | "on_confirmed_route" | "on_possible_route";
  confirmed_reachable: boolean;
  possibly_reachable: boolean;
  confirmed_distance_m?: number | null;
  phase_id: string;
}

export interface EvidenceQueue {
  schema_version?: string;
  engine_version: string;
  scope: EvidenceQueueScope;
  issues?: EvidenceIssue[];
  counts_by_status?: Record<string, number>;
  counts_by_criticality?: Record<string, number>;
  total_unresolved_attributes_scanned?: number;
  ordering_rule: string;
  prioritization_method: string;
  limitations?: string[];
}

export interface EvidenceQueueScope {
  scenario_id: string;
  scenario_revision: number;
  scenario_content_hash: string;
  project_id: string;
  phase_ids: string[];
  profile_ids: string[];
  rulepack_id: string;
  rulepack_version: string;
  rulepack_hash: string;
  evaluation_instant: string;
  additional_phases_inspected?: string[];
  scope_note?: string;
}

export interface EvidenceRecord {
  id: string;
  element_id: string;
  field: string;
  value?: number | string | boolean | null;
  unit?: string | null;
  method: string;
  source: string;
  source_url?: string | null;
  observed_at?: string | null;
  verification_status?: VerificationStatus;
  quality?: "high" | "medium" | "low";
  reviewer?: string | null;
  invalidated?: boolean;
  provenance_class: ProvenanceClass;
  synthetic?: boolean;
  note?: string;
}

export interface ExcludedIntervention {
  intervention_id: string;
  reasons: string[];
}

export interface ExecutionError {
  stage: "validation" | "materialisation" | "baseline_analysis" | "faulted_analysis" | "comparison" | "persistence";
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface ExperimentLimits {
  max_faults_per_request?: number;
  max_faults_per_suite?: number;
  max_target_ids_per_fault?: number;
  max_synthetic_observations_per_fault?: number;
  max_suite_duration_ms?: number;
  max_graph_elements?: number;
  max_experiments_per_suite?: number;
  note?: string;
}

export interface ExperimentOutcome {
  schema_version?: string;
  engine_version: string;
  experiment_id: string;
  created_at: string;
  duration_ms?: number;
  limits: ExperimentLimits;
  status: ExperimentStatus;
  source: ExperimentSource;
  faults: FaultDefinition[];
  isolated_scenario_hash?: string;
  isolated_graph_hash?: string;
  isolated_graph_version_id?: string;
  faulted_evaluation_instant?: string;
  baseline?: PhaseProfileOutcome[];
  faulted?: PhaseProfileOutcome[];
  transitions?: PairTransition[];
  element_changes?: ElementStateChange[];
  observations?: EngineeringObservation[];
  evidence_change_log?: Record<string, unknown>[];
  error?: ExecutionError | null;
  input_hash?: string;
  semantic_hash?: string;
  limitations?: string[];
  suite_id?: string | null;
}

export interface ExperimentRollup {
  experiment_id: string;
  status: ExperimentStatus;
  fault_kinds: FaultKind[];
  fault_labels: string[];
  transitions_compared: number;
  confirmed_preserved: number;
  confirmed_gained: number;
  confirmed_lost: number;
  became_possible_only: number;
  became_disconnected: number;
  new_known_violations: number;
  new_unknown_conditions: number;
  comparable_routes: number;
  total_distance_delta_m?: number | null;
  observations: EngineeringObservation[];
  error_code?: string | null;
}

export interface ExperimentSource {
  project_id: string;
  scenario_id: string;
  scenario_revision: number;
  scenario_content_hash: string;
  base_graph_version_id: string;
  base_graph_hash: string;
  rulepack_id: string;
  rulepack_version: string;
  rulepack_hash: string;
  phase_ids: string[];
  profile_ids: string[];
  evaluation_instant: string;
  verified_baseline_run_ids?: string[];
  baseline_link_note?: string;
}

export type ExperimentStatus = "completed" | "partially_completed" | "invalid_experiment" | "execution_failed" | "cancelled";

export interface ExperimentSummary {
  experiment_id: string;
  scenario_id: string;
  scenario_revision: number;
  phase_ids: string[];
  profile_ids: string[];
  fault_kinds: FaultKind[];
  fault_labels: string[];
  status: ExperimentStatus;
  observations: EngineeringObservation[];
  input_hash: string;
  semantic_hash: string;
  created_at: string;
  suite_id?: string | null;
  error_code?: string | null;
}

export interface FaultDefinition {
  fault_id?: string;
  kind: FaultKind;
  label?: string;
  target_ids?: string[];
  phase_ids?: string[];
  observation?: FaultObservation | null;
  evaluation_instant?: string | null;
  note?: string;
  semantic_hash?: string;
}

export type FaultKind = "edge_closure" | "temporary_connection_loss" | "evidence_removal" | "conflicting_observation" | "evidence_expiration" | "unsupported_unit_observation" | "path_obstruction";

export interface FaultObservation {
  field: string;
  value?: number | string | boolean | null;
  unit?: string | null;
  method?: string;
  source?: string;
  verification_status?: "unverified" | "verified" | "disputed";
  quality?: "high" | "medium" | "low";
  provenance_class?: "assumed" | "synthetic" | "synthetic_fixture";
  note?: string;
}

export interface Finding {
  id: string;
  element_id: string;
  element_kind: "edge" | "node";
  state: VerdictState;
  severity: "critical" | "advisory" | "info";
  reason_code: ReasonCode;
  rule_id?: string | null;
  profile_id: string;
  phase_id: string;
  explanation: string;
  evidence_ids?: string[];
  attributes?: ResolvedAttribute[];
  remedy_hint?: string;
}

export interface FreshnessPolicy {
  max_age_days?: number | null;
  requires_verified?: boolean;
}

export interface GraphEdit {
  op: "add_node" | "split_edge" | "add_edge" | "remove_edge" | "set_direction" | "link_crossing" | "update_attribute" | "close_edge" | "activate_temporary_edge";
  target_id: string;
  params?: Record<string, unknown>;
  reason?: string;
}

export interface Intervention {
  id: string;
  name?: string;
  description?: string;
  enabled?: boolean;
  allowed_ops: string[];
  target_element_ids?: string[];
  phases?: string[];
  requires_intervention_ids?: string[];
  excludes_intervention_ids?: string[];
  preconditions?: InterventionPrecondition[];
  effect?: InterventionEffect | null;
  costs?: InterventionCost[];
  constructible_in_field?: boolean;
  geometry_provided?: boolean;
  note?: string;
}

export interface InterventionCost {
  id: string;
  label: string;
  provenance?: CostProvenance;
  currency?: string;
  quantity: number;
  unit?: string;
  unit_price_min?: number | null;
  unit_price_nominal?: number | null;
  unit_price_max?: number | null;
  setup_cost_nominal?: number | null;
  removal_cost_nominal?: number | null;
  note?: string;
}

export interface InterventionEffect {
  edits?: GraphEdit[];
  temporary_edges?: TemporaryEdge[];
  phase_changes?: InterventionPhaseChange[];
}

export interface InterventionPhaseChange {
  phase_id: string;
  close_edge_ids?: string[];
  unclose_edge_ids?: string[];
  activate_temporary_edge_ids?: string[];
  deactivate_temporary_edge_ids?: string[];
}

export interface InterventionPrecondition {
  check: "edge_exists" | "node_exists" | "phase_exists" | "edge_closed_in_phase" | "edge_open_in_phase" | "temporary_edge_active_in_phase" | "field_known" | "field_unknown";
  target_id: string;
  phase_id?: string | null;
  field?: string | null;
  description?: string;
}

export interface MobilityProfile {
  id: string;
  name: string;
  description: string;
  is_demo_profile?: boolean;
  preference_weights?: Record<string, number>;
  notes?: string;
}

export interface NetworkEdge {
  id: string;
  u: string;
  v: string;
  length_m: number;
  edge_type: string;
  closed_in_phase: boolean;
  temporary: boolean;
  state?: string | null;
  reason_codes?: string[];
}

export interface NetworkNode {
  id: string;
  x: number;
  y: number;
  node_type: string;
  name?: string;
}

export interface Node {
  id: string;
  x: number;
  y: number;
  node_type?: NodeType;
  name?: string;
  provenance_class?: ProvenanceClass;
  evidence_ids?: string[];
}

export type NodeType = "junction" | "curb_interface" | "crossing_interface" | "access_node" | "origin" | "destination";

export interface ODPairResult {
  origin_id: string;
  destination_id: string;
  origin_node_id: string;
  destination_node_id: string;
  confirmed_reachable: boolean;
  possibly_reachable: boolean;
  confirmed_path_edge_ids?: string[];
  confirmed_distance_m?: number | null;
  possible_path_edge_ids?: string[];
  possible_distance_m?: number | null;
  possible_distance_label?: string;
  confirmed_route_cost?: number | null;
  possible_route_cost?: number | null;
  route_note?: string;
  blocking_finding_ids?: string[];
  relevant_finding_ids?: string[];
  reason_codes?: ReasonCode[];
}

export interface ODTransition {
  origin_id: string;
  destination_id: string;
  before_confirmed: boolean;
  before_possible: boolean;
  after_confirmed: boolean;
  after_possible: boolean;
  before_distance_m?: number | null;
  after_distance_m?: number | null;
  added_distance_m?: number | null;
}

export interface ObservationComparison {
  evidence_id: string;
  value?: number | string | boolean | null;
  unit?: string | null;
  method: string;
  source: string;
  source_url?: string | null;
  observed_at?: string | null;
  verification_status: string;
  quality: string;
  reviewer?: string | null;
  provenance_class: string;
  synthetic: boolean;
  invalidated: boolean;
  note?: string;
  conversion?: Record<string, unknown> | null;
}

export type Operator = "gte" | "lte" | "gt" | "lt" | "eq" | "one_of" | "exists";

export interface OriginDestination {
  id: string;
  label?: string;
  node_id: string;
  kind: "origin" | "destination" | "both";
  essential?: boolean;
  priority?: number;
  weight_source?: string;
  weight?: number | null;
}

export interface PairTransition {
  pair_id: string;
  origin_id: string;
  destination_id: string;
  profile_id: string;
  phase_id: string;
  before_confirmed: boolean;
  before_possible: boolean;
  before_distance_m?: number | null;
  after_confirmed: boolean;
  after_possible: boolean;
  after_distance_m?: number | null;
  distance_delta_m?: number | null;
  observation: EngineeringObservation;
  explanation: string;
  new_fail_verdicts?: string[];
  new_unknown_verdicts?: string[];
  reference_route_comparison?: boolean;
}

export interface Phase {
  id: string;
  order: number;
  label?: string;
  boundary_convention?: "[start,end)" | "logical_ordinal";
  start_ordinal?: number | null;
  end_ordinal?: number | null;
  closed_edge_ids?: string[];
  temporary_edge_ids?: string[];
  notes?: string;
}

export interface PhaseProfileOutcome {
  phase_id: string;
  profile_id: string;
  available: boolean;
  phase_graph_id?: string | null;
  phase_graph_hash?: string | null;
  analysis_semantic_hash?: string | null;
  counts?: Record<string, number>;
  unavailable_reason?: string;
}

export type ProvenanceClass = "measured" | "external_source" | "derived" | "assumed" | "synthetic" | "synthetic_fixture";

export type QueueState = "open";

export interface RankingPolicy {
  id?: string;
  version?: string;
  monetary_default?: string;
  order?: string[];
  description?: string;
}

export type ReasonCode = "RULE_PASS" | "RULE_FAIL" | "RULE_NOT_APPLICABLE" | "RULE_UNKNOWN_ATTRIBUTE" | "NO_EVIDENCE" | "CONFLICTING_EVIDENCE" | "UNSUPPORTED_UNIT" | "INVALID_NUMERIC_VALUE" | "EVIDENCE_EXPIRED" | "EVIDENCE_NOT_VERIFIED" | "EVIDENCE_INVALIDATED" | "NO_FRESHNESS_POLICY" | "EDGE_CLOSED_IN_PHASE" | "EDGE_NOT_ACTIVE_IN_PHASE" | "NODE_BLOCKED" | "NO_APPLICABLE_RULES" | "DUPLICATE_ID" | "UNKNOWN_NODE_REFERENCE" | "SELF_LOOP" | "CROSSING_WITHOUT_NODE" | "CONFIRMED_ROUTE_FOUND" | "POSSIBLE_ROUTE_ONLY" | "NO_ROUTE" | "ORIGIN_NODE_MISSING" | "DESTINATION_NODE_MISSING" | "DEMO_RULEPACK_NOT_LEGAL" | "SYNTHETIC_DATA_NOTICE" | "NOT_CERTIFIED";

export interface ReportAlternativePlan {
  search_id: string;
  scenario_revision: number;
  phase_id: string;
  profile_ids?: string[];
  evaluation_instant: string;
  solver_status: string;
  exhaustive: boolean;
  limits_hit?: string[];
  best_proposal_id?: string | null;
  domain_eligible_intervention_ids?: string[];
  domain_evaluated_count: number;
  domain_combination_count: number;
  truncated_by?: string[];
  scope_note: string;
  permitted_interventions?: Record<string, unknown>[];
  selected_candidates?: ReportCandidate[];
  semantic_hash: string;
  budget_note?: string;
}

export interface ReportCandidate {
  proposal_id: string;
  classification: string;
  intervention_ids?: string[];
  restored_all_profiles?: string[];
  requires_verification: boolean;
  introduced_unknown_verdict_count: number;
  introduced_fail_verdict_count: number;
  cost_currency?: string | null;
  cost_nominal?: number | null;
  cost_maximum?: number | null;
  cost_unknown: boolean;
  cost_note: string;
  preview_scenario_hash?: string;
}

export interface ReportEvidenceIssue {
  issue_id: string;
  element_id: string;
  attribute: string;
  resolution_status: string;
  status_label: string;
  criticality: string;
  rationale?: string[];
  evidence_record_ids?: string[];
  investigation_target: string;
}

export interface ReportEvidenceRow {
  evidence_id: string;
  element_id: string;
  field: string;
  value?: number | string | boolean | null;
  unit?: string | null;
  method: string;
  source: string;
  observed_at?: string | null;
  verification_status: string;
  provenance_class: string;
  synthetic: boolean;
  note?: string;
}

export interface ReportExperiment {
  experiment_id: string;
  status: string;
  scenario_revision: number;
  phase_ids?: string[];
  profile_ids?: string[];
  evaluation_instant: string;
  faulted_evaluation_instant: string;
  fault_kinds?: string[];
  fault_labels?: string[];
  fault_semantic_hashes?: string[];
  fault_targets?: string[];
  observations?: string[];
  transitions?: Record<string, unknown>[];
  element_changes?: Record<string, unknown>[];
  evidence_change_log?: Record<string, unknown>[];
  error?: Record<string, unknown> | null;
  semantic_hash: string;
  input_hash: string;
}

export interface ReportFinding {
  finding_id: string;
  element_id: string;
  element_kind: string;
  state: string;
  severity: string;
  reason_code: string;
  rule_id?: string | null;
  rule_version?: string | null;
  rulepack_version: string;
  profile_id: string;
  phase_id: string;
  explanation: string;
  evidence_ids?: string[];
  attributes?: Record<string, unknown>[];
}

export interface ReportIdentity {
  report_id: string;
  project_id: string;
  project_name: string;
  project_jurisdiction: string;
  project_owner: string;
  project_study_area: string;
  scenario_id: string;
  scenario_name: string;
  scenario_revision: number;
  scenario_content_hash: string;
  parent_scenario_id?: string | null;
  dataset_notice: string;
  dataset_license: string;
  dataset_attribution: string;
  dataset_provenance_class: string;
}

export interface ReportLimitations {
  statements: string[];
  field_measurements_independently_verified?: boolean;
  legal_applicability_reviewed?: boolean;
  physical_safety_established?: boolean;
  manual_accessibility_review_performed?: boolean;
  costs_available?: boolean;
  phases_not_analysed?: string[];
  rules_are_demonstration_only?: boolean;
}

export interface ReportModification {
  phase_id: string;
  order: number;
  label: string;
  closed_edge_ids?: string[];
  temporary_edge_ids?: string[];
  notes?: string;
}

export interface ReportNetwork {
  phase_id: string;
  profile_id: string;
  phase_graph_id: string;
  phase_graph_hash: string;
  nodes?: NetworkNode[];
  edges?: NetworkEdge[];
  unlinked_crossings?: Record<string, unknown>[];
  bound_x: number;
  bound_y: number;
  bound_width: number;
  bound_height: number;
}

export interface ReportODRow {
  profile_id: string;
  phase_id: string;
  pair_id: string;
  origin_id: string;
  destination_id: string;
  confirmed_reachable: boolean;
  possibly_reachable: boolean;
  confirmed_distance_m?: number | null;
  possible_distance_m?: number | null;
  confirmed_route_cost?: number | null;
  confirmed_path_edge_ids?: string[];
  possible_path_edge_ids?: string[];
  blocking_finding_ids?: string[];
  relevant_finding_ids?: string[];
  reason_codes?: string[];
  distance_note?: string;
}

export interface ReportReproducibility {
  report_schema_version: string;
  report_generator_version: string;
  engine_version: string;
  scenario_id: string;
  scenario_revision: number;
  scenario_content_hash: string;
  base_graph_version_id: string;
  base_graph_hash: string;
  rulepack_id: string;
  rulepack_version: string;
  rulepack_hash: string;
  selected_run_ids?: string[];
  selected_run_semantic_hashes?: string[];
  selected_run_input_hashes?: string[];
  selected_search_ids?: string[];
  selected_search_semantic_hashes?: string[];
  selected_experiment_ids?: string[];
  selected_experiment_semantic_hashes?: string[];
  selected_experiment_input_hashes?: string[];
  reproduction_steps?: string[];
  canonical_json_bytes?: number;
}

export interface ReportScope {
  synthetic_dataset: boolean;
  synthetic_dataset_reason: string;
  coordinate_basis_kind: string;
  coordinate_basis_note: string;
  local_origin_label?: string | null;
  graph_version_id: string;
  graph_content_hash: string;
  node_count: number;
  edge_count: number;
  evidence_record_count: number;
  rulepack_id: string;
  rulepack_version: string;
  rulepack_hash: string;
  rulepack_legal_applicability: string;
  rulepack_disclaimer: string;
  rule_count: number;
  profiles?: Record<string, unknown>[];
  phases_analysed?: Record<string, unknown>[];
  phases_declared?: Record<string, unknown>[];
  origin_destination_requirements?: Record<string, unknown>[];
  evaluation_instants?: string[];
}

export interface ReportSection12 {
  review_recorded?: boolean;
  reviewer?: string | null;
  reviewer_role?: string | null;
  reviewed_at?: string | null;
  note?: string;
  approval_status?: string;
}

export interface ResolvedAttribute {
  element_id: string;
  field: string;
  known: boolean;
  value?: number | string | boolean | null;
  canonical_unit?: string | null;
  reason_code?: ReasonCode | null;
  explanation?: string;
  evidence_ids?: string[];
  conflicting_values?: string[];
  conversions?: Record<string, unknown>[];
  conversions_explicit?: boolean;
}

export interface ReviewReport {
  schema_version?: string;
  generator_version?: string;
  engine_version?: string;
  identity: ReportIdentity;
  scope: ReportScope;
  network: ReportNetwork;
  modifications?: ReportModification[];
  executive_summary?: Record<string, unknown>;
  od_rows?: ReportODRow[];
  findings?: ReportFinding[];
  evidence_rows?: ReportEvidenceRow[];
  evidence_issues?: ReportEvidenceIssue[];
  alternative_plans?: ReportAlternativePlan[];
  experiments?: ReportExperiment[];
  robustness?: Record<string, unknown> | null;
  limitations: ReportLimitations;
  reproducibility: ReportReproducibility;
  human_review: ReportSection12;
  section_availability?: Record<string, SectionAvailability>;
  disclaimer?: string;
  not_certified_note?: string;
}

export interface RobustnessSummary {
  schema_version?: string;
  scenario_id: string;
  scenario_revision: number;
  scenario_content_hash: string;
  phase_ids: string[];
  profile_ids: string[];
  evaluation_instant: string;
  rulepack_id: string;
  rulepack_hash: string;
  base_graph_hash: string;
  experiments_requested: number;
  experiments_completed: number;
  experiments_partially_completed: number;
  experiments_invalid: number;
  experiments_failed: number;
  fault_kinds_available: FaultKind[];
  fault_kinds_tested: FaultKind[];
  fault_kinds_untested: FaultKind[];
  pairs_evaluated: number;
  pairs_retaining_confirmed: number;
  pairs_losing_confirmed: number;
  pairs_becoming_possible_only: number;
  pairs_becoming_disconnected: number;
  pairs_with_new_known_violation: number;
  pairs_with_new_unknown_condition: number;
  pairs_gaining_confirmed: number;
  comparable_routes: number;
  total_distance_delta_m?: number | null;
  per_experiment?: ExperimentRollup[];
  denominator_note: string;
  interpretation_note?: string;
  limitations?: string[];
}

export interface Rule {
  id: string;
  version?: string;
  scope: RuleScope;
  kind?: RuleKind;
  criticality?: RuleCriticality;
  description?: string;
  applies_to_edge_types?: EdgeType[];
  applies_to_node_types?: NodeType[];
  profiles?: string[];
  checks: RuleCheck[];
  requires_verified_evidence?: boolean;
  failure_message?: string;
  basis_label?: string;
  source_reference?: string;
}

export interface RuleCheck {
  field: string;
  operator: Operator;
  threshold?: number | null;
  values?: string[];
  description?: string;
}

export type RuleCriticality = "critical" | "advisory";

export type RuleKind = "hard" | "preference";

export interface RulePack {
  id: string;
  version?: string;
  name?: string;
  basis?: string;
  jurisdiction_scope?: string;
  legal_applicability?: "unverified" | "reviewed" | "not_applicable";
  disclaimer?: string;
  attributes?: Record<string, AttributeSpec>;
  rules: Rule[];
  source: DataSource;
  content_hash?: string;
}

export type RuleScope = "edge" | "node";

export interface RuleVerdict {
  rule_id: string;
  rule_version: string;
  element_id: string;
  scope: RuleScope;
  state: VerdictState;
  reason_code: ReasonCode;
  explanation: string;
  profile_id: string;
  phase_id: string;
  inputs?: ResolvedAttribute[];
  rule_kind?: RuleKind;
  criticality?: RuleCriticality;
  basis_label?: string;
}

export interface Scenario {
  id: string;
  name?: string;
  parent_scenario_id?: string | null;
  base_graph_version_id: string;
  rulepack_id: string;
  rulepack_hash: string;
  profile_ids: string[];
  phases: Phase[];
  edits?: GraphEdit[];
  origins_destinations?: OriginDestination[];
  temporary_edges?: TemporaryEdge[];
  intervention_ids?: string[];
  note?: string;
  revision?: number;
  created_at?: string | null;
  content_hash?: string;
}

export interface SearchBudget {
  amount: number;
  currency?: string;
  basis?: "nominal" | "conservative_max";
}

export interface SearchConfig {
  max_interventions?: number;
  max_candidates?: number;
  max_duration_ms?: number;
  excluded_intervention_ids?: string[];
  budget?: SearchBudget | null;
  monetary_objective?: "off" | "nominal";
}

export interface SearchOutcome {
  schema_version?: string;
  engine_version: string;
  search_id: string;
  created_at: string;
  duration_ms: number;
  scenario_id: string;
  scenario_revision: number;
  scenario_content_hash: string;
  base_graph_version_id: string;
  base_graph_hash: string;
  rulepack_id: string;
  rulepack_hash: string;
  phase_id: string;
  profile_ids: string[];
  evaluation_instant: string;
  config: SearchConfig;
  domain: DomainSummary;
  baseline: BaselineProfile[];
  candidates: CandidateEvaluation[];
  ranking_policy: RankingPolicy;
  status: SearchStatus;
  input_hash?: string;
  semantic_hash?: string;
  disclaimers?: string[];
}

export interface SearchStatus {
  solver_status: SolverStatus;
  exhaustive: boolean;
  limits_hit?: string[];
  best_proposal_id?: string | null;
  scope_note?: string;
  notes?: string[];
}

export interface SectionAvailability {
  status: "available" | "unavailable" | "not_selected";
  reason?: string;
  source_ids?: string[];
}

export type SolverStatus = "OPTIMAL_IN_ENUMERATED_DOMAIN" | "FEASIBLE_NOT_PROVEN_OPTIMAL" | "NO_FEASIBLE_IN_ENUMERATED_DOMAIN" | "INVALID_INPUT" | "INCOMPLETE_OR_UNKNOWN";

export interface TemporaryEdge {
  id: string;
  u: string;
  v: string;
  geometry: Record<string, unknown>[][];
  length_m: number;
  edge_type?: EdgeType;
  name?: string;
  evidence?: EvidenceRecord[];
  constructible_in_field?: boolean;
  field_verification_note?: string;
}

export type VerdictState = "PASS" | "FAIL" | "UNKNOWN" | "NOT_APPLICABLE";

export type VerificationStatus = "verified" | "unverified" | "disputed";
