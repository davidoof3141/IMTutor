export type UserRole = "admin" | "learner";
export type UserStatus = "pending" | "approved" | "rejected";

export interface User {
  id: string;
  username: string;
  role: UserRole;
  status: UserStatus;
  must_change_password: boolean;
  created_at: string;
}

export interface LoginResponse {
  token: string;
  user: User;
}

export interface MeResponse {
  user: User;
  learner_id: string | null;
}

export type Role = "practitioner" | "analyst" | "academic";
export type PriorExperience = "none" | "low" | "moderate" | "high";
export type Goal = "certification" | "applied_competence" | "orientation";
// The learner's working context; decides which world the tutor's examples
// are drawn from (maps to the example_domain control parameter).
export type Industry =
  | "manufacturing"
  | "finance"
  | "public_sector"
  | "healthcare"
  | "retail"
  | "it_software"
  | "logistics"
  | "energy"
  | "consulting"
  | "neutral";
// Lerntyp (Vester): how the learner prefers to take in new material.
export type LearnerType = "visuell" | "auditiv" | "kommunikativ" | "motorisch";

export type Register = "formal" | "neutral" | "informal";
export type ExampleDomain = Industry;
export type AssessmentFrequency = "every_topic" | "every_second_topic" | "on_request";

export interface Profile {
  learner_id: string;
  role: Role;
  prior_experience: PriorExperience;
  goal: Goal;
  industry: Industry;
  learner_type: LearnerType;
  ruleset_version: string;
  created_at: string;
}

export interface ControlVector {
  explanation_depth: number;
  example_density: number;
  concreteness: number;
  example_domain: ExampleDomain;
  register: Register;
  assessment_frequency: AssessmentFrequency;
}

export type Attribution = Record<keyof ControlVector, string>;
export type Override = Partial<ControlVector>;

export interface OnboardingResponse {
  profile: Profile;
  derived: ControlVector;
  attribution: Attribution;
}

export interface ConfigResponse {
  profile: Profile;
  derived: ControlVector;
  override: Override;
  effective: ControlVector;
  attribution: Attribution;
}

export interface Rule {
  id: string;
  priority: number;
  when: Record<string, string[]>;
  set: Record<string, unknown>;
}

export interface RuleSet {
  version: string;
  defaults: Record<string, unknown>;
  rules: Rule[];
}

export interface ClauseCatalogue {
  version: string;
  base_instruction: string;
  clauses: Record<string, Record<string, string>>;
}

export interface RulesResponse {
  ruleset: RuleSet;
  catalogue: ClauseCatalogue;
}

export interface Section {
  number: string;
  title: string;
  page_start: number;
  page_end: number;
}

export interface Chapter {
  number: string;
  title: string;
  page_start: number;
  page_end: number;
  sections: Section[];
}

export interface CurriculumResponse {
  chapters: Chapter[];
}

export type StudyModeName = "exploration" | "training";

export interface StudyModeState {
  mode: StudyModeName;
  chapter_number: string | null;
  section_number: string | null;
}

export type LessonStepKind = "explain" | "example" | "checkpoint" | "recap";

export interface LessonStep {
  index: number;
  kind: LessonStepKind;
  section_ref: string;
  page_start: number;
  page_end: number;
}

export interface LessonPlan {
  lesson_id: string;
  learner_id: string;
  conversation_id: string;
  ruleset_version: string;
  planner_version: string;
  chapter_ref: string;
  section_ref: string | null;
  vector_snapshot: ControlVector;
  steps: LessonStep[];
  created_at: string;
}

export type LessonStatus = "active" | "completed" | "abandoned";

export interface LessonResponse {
  plan: LessonPlan;
  /** step index (as a string -- JSON object keys) -> "parameter=value", or "always" for recap. */
  rationale: Record<string, string>;
  current_step: number;
  status: LessonStatus;
  vector_drifted: boolean;
  message: string | null;
}

export interface TurnLogRecord {
  learner_id: string;
  ruleset_version: string;
  effective_vector: ControlVector;
  system_prompt_sha256: string;
  model: string;
  temperature: number;
  book_context?: string;
  study_mode?: StudyModeState | null;
  conversation_id?: string | null;
  prompt: string;
  completion: string;
  prompt_tokens: number;
  completion_tokens: number;
  timestamp: string;
}

export interface Conversation {
  id: string;
  learner_id: string;
  title: string | null;
  mode: StudyModeName | null;
  chapter_number: string | null;
  section_number: string | null;
  created_at: string;
  last_message_at: string;
  message_count: number;
}

export type AttachmentKind = "image" | "document";

export interface Attachment {
  id: string;
  filename: string;
  mime_type: string;
  kind: AttachmentKind;
  size_bytes: number;
}

export interface BookImageRef {
  id: string;
  page: number;
}

export interface ConversationMessage {
  role: "learner" | "tutor";
  text: string;
  created_at: string;
  attachments?: Attachment[];
  book_images?: BookImageRef[];
  page_refs?: number[];
}
