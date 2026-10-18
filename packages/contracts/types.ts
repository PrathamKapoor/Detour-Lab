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

export interface CoordinateBasis {
  kind: "local_planar_meters" | "wgs84_degrees";
  unit: "m" | "degree";
  local_origin_label?: string | null;
  crs_note?: string;
  projected_crs?: string | null;
}

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

export interface MobilityProfile {
  id: string;
  name: string;
  description: string;
  is_demo_profile?: boolean;
  preference_weights?: Record<string, number>;
  notes?: string;
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

export type ProvenanceClass = "measured" | "external_source" | "derived" | "assumed" | "synthetic" | "synthetic_fixture";

export type ReasonCode = "RULE_PASS" | "RULE_FAIL" | "RULE_NOT_APPLICABLE" | "RULE_UNKNOWN_ATTRIBUTE" | "NO_EVIDENCE" | "CONFLICTING_EVIDENCE" | "UNSUPPORTED_UNIT" | "INVALID_NUMERIC_VALUE" | "EVIDENCE_EXPIRED" | "EVIDENCE_NOT_VERIFIED" | "EVIDENCE_INVALIDATED" | "NO_FRESHNESS_POLICY" | "EDGE_CLOSED_IN_PHASE" | "EDGE_NOT_ACTIVE_IN_PHASE" | "NODE_BLOCKED" | "NO_APPLICABLE_RULES" | "DUPLICATE_ID" | "UNKNOWN_NODE_REFERENCE" | "SELF_LOOP" | "CROSSING_WITHOUT_NODE" | "CONFIRMED_ROUTE_FOUND" | "POSSIBLE_ROUTE_ONLY" | "NO_ROUTE" | "ORIGIN_NODE_MISSING" | "DESTINATION_NODE_MISSING" | "DEMO_RULEPACK_NOT_LEGAL" | "SYNTHETIC_DATA_NOTICE" | "NOT_CERTIFIED";

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
