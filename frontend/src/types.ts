export type UserRole = "admin" | "learner";
export type UserStatus = "pending" | "approved" | "rejected";

export interface User {
  id: string;
  username: string;
  role: UserRole;
  status: UserStatus;
  must_change_password: boolean;
  has_login_link: boolean;
  created_at: string;
}

export interface LoginResponse {
  token: string;
  user: User;
}

export interface LinkUserResponse {
  user: User;
  /** The raw token, visible only in this response -- turn it into a link
   * immediately, it can't be retrieved again afterwards. */
  link_token: string;
}

export interface MeResponse {
  user: User;
  learner_id: string | null;
}

export interface KindPreferenceCount {
  kind: VariantKind;
  count: number;
}

export interface ReasonCount {
  reason: string;
  count: number;
}

export interface OverrideFieldCount {
  field: string;
  count: number;
}

export interface AdminStats {
  comparisons_decided: number;
  comparisons_pending: number;
  preference_by_kind: KindPreferenceCount[];
  learners_decided: number;
  learners_personalized_more: number;
  learners_generic_more: number;
  learners_tied: number;
  reason_counts: ReasonCount[];
  override_changes_total: number;
  override_changes_by_field: OverrideFieldCount[];
}

export interface DiagnosticResultRow {
  username: string;
  chapter_id: string;
  chapter_title: string;
  correct_count: number;
  item_count: number | null;
  self_estimate: PriorKnowledge;
  quiz_level: PriorKnowledge;
  taken_at: string;
}

// Self-reported general IT-management experience. At onboarding this is only
// the SEED; a per-chapter diagnostic replaces it for that chapter's mapping.
export type PriorKnowledge = "none" | "low" | "moderate" | "high";
export type LearningGoal = "certification" | "applied" | "orientation";
export type RetentionHorizon = "within_2_weeks" | "1_to_3_months" | "long_term";
// Preference, not a mapping input: only selects a fixed prompt clause.
export type PresentationStyle = "concise" | "balanced" | "verbose";
// Lerntyp nach Vester; a preference like the above ("none" = keine Angabe).
export type LearnerType = "none" | "visuell" | "auditiv" | "kommunikativ" | "motorisch";
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
export type Register = "polite" | "direct";
export type ReviewSchedule = 2 | 7 | 14;
export type ExampleDomain = Industry;
export type AssessmentFrequency = "every_topic" | "every_second_topic" | "on_request";

export interface Profile {
  learner_id: string;
  // mapping inputs
  prior_knowledge_seed: PriorKnowledge;
  learning_goal: LearningGoal;
  retention_horizon: RetentionHorizon;
  industry: Industry;
  // preferences (prompt assembly only)
  simplified_language: boolean;
  presentation_style: PresentationStyle;
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
  review_schedule: ReviewSchedule;
}

export type Attribution = Record<keyof ControlVector, string>;
export type Override = Partial<ControlVector>;

export interface OnboardingResponse {
  profile: Profile;
  derived: ControlVector;
  attribution: Attribution;
}

export interface ChapterDiagnosticInfo {
  diagnostic_key: string;
  correct_count: number;
  experience_seed: PriorKnowledge;
  /** Chapter-level level; replaced the seed for this chapter's mapping only. */
  prior_knowledge: PriorKnowledge;
  override: Override;
}

export interface ConfigResponse {
  profile: Profile;
  derived: ControlVector;
  override: Override;
  effective: ControlVector;
  attribution: Attribution;
  chapter_diagnostic?: ChapterDiagnosticInfo | null;
}

export interface DiagnosticItem {
  stem: string;
  options: { text: string }[];
}

export interface DiagnosticResult {
  diagnostic_key: string;
  correct_count: number;
  item_count: number;
  experience_seed: PriorKnowledge;
  prior_knowledge: PriorKnowledge;
  derived: ControlVector;
  attribution: Attribution;
  override: Override;
  effective: ControlVector;
}

export interface DiagnosticStatus {
  required: boolean;
  key: string | null;
  items: DiagnosticItem[];
  result: DiagnosticResult | null;
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
  concreteness: number;
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

// The two on-screen slots a comparison turn's variants are randomly assigned
// to (see backend app/api/chat.py's /compare) -- deliberately uninformative
// about which one is personalized.
export type VariantLabel = "a" | "b";
export type VariantKind = "personalized" | "generic";
export type ReasonTag = "detail" | "tone" | "clarity" | "examples" | "difficulty" | "other";

export interface ConversationMessage {
  role: "learner" | "tutor";
  text: string;
  created_at: string;
  attachments?: Attachment[];
  book_images?: BookImageRef[];
  page_refs?: number[];
}
