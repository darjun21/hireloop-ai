// Types mirror src/models/career_profile.py's model_dump(mode="json")
// output exactly. Every field here maps to a real backend field.

export type FieldProvenance =
  | "RESUME_DERIVED"
  | "USER_CONFIRMED"
  | "APPLICATION_ANSWER"
  | "SYSTEM_DERIVED"
  | "HUMAN_CONFIRMATION";

export interface PersonalInfo {
  first_name: string;
  middle_name: string | null;
  last_name: string;
  preferred_name: string | null;
  professional_email: string;
  phone: string | null;
  linkedin_url: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  postal_code: string | null;
  provenance: FieldProvenance;
}

export interface WorkAuthorization {
  target_country: string | null;
  authorized_to_work: boolean | null;
  authorization_type: string | null;
  requires_sponsorship_now: boolean | null;
  requires_sponsorship_future: boolean | null;
  expiration_date: string | null;
  notes: string | null;
  provenance: FieldProvenance;
}

export interface TargetRole {
  title: string;
  priority: "PRIMARY" | "SECONDARY" | "EXPLORATORY" | null;
  provenance: FieldProvenance;
}

export interface CareerEmploymentPreferences {
  locations: string[];
  work_arrangements: string[];
  employment_types: string[];
  target_compensation_min: number | null;
  target_compensation_max: number | null;
  compensation_unit: string | null;
  relocation_willing: boolean | null;
  travel_willingness: string | null;
  industry_preferences: string[];
  company_size_preference: string | null;
  excluded_companies: string[];
  preferred_companies: string[];
  provenance: FieldProvenance;
}

export interface ProfileSkill {
  name: string;
  provenance: FieldProvenance;
  resume_evidence_ids: string[];
  evidence_summaries: string[];
  notes: string | null;
}

export interface ProfileWorkExperience {
  entry_id: string;
  company: string;
  title: string;
  start_date: string | null;
  end_date: string | null;
  description: string | null;
  skills_used: string[];
  provenance: FieldProvenance;
}

export interface ProfileEducation {
  entry_id: string;
  institution: string;
  degree: string | null;
  field_of_study: string | null;
  start_date: string | null;
  end_date: string | null;
  provenance: FieldProvenance;
}

export interface ProfileCertification {
  entry_id: string;
  name: string;
  issuer: string | null;
  date: string | null;
  provenance: FieldProvenance;
}

export interface ProfileProject {
  entry_id: string;
  name: string;
  description: string | null;
  skills_used: string[];
  provenance: FieldProvenance;
}

export interface ProfileLanguage {
  name: string;
  proficiency: string | null;
  provenance: FieldProvenance;
}

export interface ApplicationAnswers {
  authorized_to_work: boolean | null;
  requires_sponsorship: boolean | null;
  willing_to_relocate: boolean | null;
  earliest_start_date: string | null;
  notice_period: string | null;
  desired_compensation: number | null;
  compensation_unit: string | null;
  preferred_employment_type: string | null;
  preferred_work_mode: string | null;
  provenance: FieldProvenance;
}

export interface EEODemographics {
  gender: string;
  race_ethnicity: string;
  veteran_status: string;
  disability_status: string;
}

export interface ReferenceContact {
  reference_id: string;
  name: string;
  relationship: string | null;
  company: string | null;
  email: string | null;
  phone: string | null;
}

export interface ResumeSourceInfo {
  original_filename: string | null;
  uploaded_at: string | null;
  parsed_profile_version: number;
  source_candidate_id: string | null;
  resume_file_path: string | null;
  extraction_warnings: string[];
}

export interface CareerProfile {
  profile_id: string;
  owner_id: string;
  created_at: string;
  updated_at: string;
  personal_info: PersonalInfo | null;
  work_authorization: WorkAuthorization | null;
  target_roles: TargetRole[];
  employment_preferences: CareerEmploymentPreferences;
  professional_summary: string;
  total_experience_years: number | null;
  work_experience: ProfileWorkExperience[];
  projects: ProfileProject[];
  skills: ProfileSkill[];
  education: ProfileEducation[];
  certifications: ProfileCertification[];
  languages: ProfileLanguage[];
  application_answers: ApplicationAnswers;
  demographics: EEODemographics;
  references: ReferenceContact[];
  resume_source: ResumeSourceInfo;
  confirmed_at: string | null;
}

export type CompletenessStatus = "COMPLETE" | "NEEDS_REVIEW" | "MISSING";

export interface CategoryCompleteness {
  category: string;
  status: CompletenessStatus;
  missing_fields: string[];
  review_reasons: string[];
}

export interface ProfileCompleteness {
  categories: CategoryCompleteness[];
  overall_percent_complete: number;
}

export interface ProfileConflict {
  category: string;
  description: string;
  existing_provenance: FieldProvenance;
}

export interface ProfileUpdateDiff {
  new_skills: string[];
  new_work_experience: string[];
  new_education: string[];
  new_certifications: string[];
  changed_work_experience: string[];
  removed_resume_derived: string[];
  potential_conflicts: ProfileConflict[];
  summary_changed: boolean;
}

export interface ResumeUploadResponse {
  upload_id: string;
  diff: ProfileUpdateDiff;
  validation_warnings: string[];
  validation_errors: string[];
}

export type SessionMode = "PERSONAL" | "CERTIFICATION_DEMO";
