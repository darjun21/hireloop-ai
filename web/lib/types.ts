// Types mirror the JSON shapes produced by api/serializers.py exactly.
// Every field here is real backend data — nothing in the UI layer invents
// a value that doesn't map to one of these fields.

export type StageStatus = "done" | "active" | "human" | "waiting";

export interface StageStatusMap {
  DISCOVER: StageStatus;
  SCORE: StageStatus;
  TAILOR: StageStatus;
  VERIFY: StageStatus;
  APPLY: StageStatus;
  TRACK: StageStatus;
  LEARN: StageStatus;
  IMPROVE: StageStatus;
}

export interface Kpi {
  icon: string;
  value: string;
  label: string;
}

export interface TopOpportunity {
  job_id: string;
  title: string;
  company: string;
  location: string;
  work_mode: string | null;
  score: number;
  recommendation: string;
  confidence: string;
  strengths: string[];
  gaps: string[];
  selectable: boolean;
}

export interface LatestInsight {
  category: string;
  evidence: string;
  observation: string;
  recommendation: string;
  sample_size: number;
  confidence: string;
  actionability?: string;
}

export interface AgentActivityRow {
  name: string;
  status: string;
  note: string;
}

export interface ClaimCard {
  claim: string;
  reason?: string;
  evidence?: string;
  result: string;
}

export interface TruthGuardSummary {
  counts: { verified: number; blocked: number; review: number };
  blocked_example: ClaimCard | null;
  verified_example: ClaimCard | null;
}

export interface ActivityEvent {
  message: string;
  timestamp: string | null;
}

export interface EligibleSelection {
  job_id: string;
  [key: string]: unknown;
}

export interface Interrupt {
  eligible_selections?: EligibleSelection[];
  action_required?: string;
  modifications?: { modification_id: string; [key: string]: unknown }[];
  clarification_required?: {
    proposed_claim: string;
    explanation: string;
    closest_evidence_ids?: string[];
    safe_option?: string | null;
  };
  application?: {
    job_id: string;
    current_status: string;
    opportunity_score?: number;
    [key: string]: unknown;
  };
  allowed_actions?: string[];
  warning?: string | null;
  [key: string]: unknown;
}

export interface MissionControlView {
  demo_mode: boolean;
  candidate_first_name: string | null;
  has_run: boolean;
  stage_status: StageStatusMap;
  kpis: Kpi[];
  top_opportunity: TopOpportunity | null;
  latest_insight: LatestInsight | null;
  agent_activity: AgentActivityRow[];
  truth_guard_summary: TruthGuardSummary;
  recent_activity: ActivityEvent[];
  interrupt: Interrupt | null;
}

export interface OpportunityRow {
  job_id: string;
  title: string;
  company: string;
  location: string;
  work_mode: string | null;
  source: string | null;
  url: string | null;
  score: number;
  recommendation: string;
  confidence: string;
  scoring_version: string | null;
  components: Record<string, { value: number; weight: number; weighted_contribution: number }>;
  requirement_completeness: string | null;
  strengths: string[];
  gaps: string[];
  risks: string[];
  explanation: string;
  selectable: boolean;
}

export interface OpportunitiesView {
  opportunities: OpportunityRow[];
  counts: Record<string, number>;
}

export interface OpportunityFunnel {
  discovered: number;
  unique_after_dedup: number;
  scored: number;
  analyzed: number;
}

export interface OpportunityDetail {
  job_id: string;
  title: string;
  company: string;
  location: string;
  work_mode: string | null;
  source: string | null;
  url: string | null;
  score: number;
  recommendation: string;
  confidence: string;
  scoring_version: string | null;
  components: Record<string, { value: number; weight: number; weighted_contribution: number }>;
  listing_confidence: string | null;
  requirement_completeness: string | null;
  quality_score: number | null;
  quality_flags: string[];
  strengths: string[];
  gaps: string[];
  risks: string[];
  explanation: string;
  selectable: boolean;
  funnel: OpportunityFunnel;
}

export interface ModificationRow {
  modification_id: string;
  section: string;
  original_text: string | null;
  proposed_text: string;
  reason: string;
  evidence_ids: string[];
  status: string;
  status_label: string;
  explanation: string;
}

export interface ResumeStudioView {
  selected_job_id: string | null;
  counts: Record<string, number>;
  modifications: ModificationRow[];
  rejected: { modification_id: string; label: string; reason: string }[];
  interrupt: Interrupt | null;
  current_resume_version_id: string | null;
  approved_modification_ids: string[];
}

export interface ApplicationsView {
  pending_application_interrupt: Record<string, unknown> | null;
  applications: {
    application: {
      application_id: string;
      job_id: string;
      title?: string | null;
      company?: string | null;
      role_family?: string | null;
      opportunity_score?: number | null;
      current_status: string;
      applied_at?: string | null;
      selected_resume_version_id?: string | null;
    };
    history: { occurred_at: string; event_type: string }[];
  }[];
}

export interface GroupAnalytics {
  sample_size: number;
  positive_responses: number;
  response_rate: number;
  interviews: number;
  interview_rate: number;
  offers: number;
  offer_rate: number;
  confidence: string;
}

export interface StrategyView {
  demo_mode: boolean;
  analytics: {
    by_role_family: Record<string, GroupAnalytics>;
    by_resume_version: Record<string, GroupAnalytics>;
    by_work_mode: Record<string, GroupAnalytics>;
    total_applications: number;
    total_resolved: number;
  };
  insights: LatestInsight[];
}

export interface SystemView {
  demo_mode: boolean;
  llm_provider: { name: string; status: string };
  fallback_llm: { name: string; status: string };
  evidence_retrieval: string;
  you_search: string;
}
