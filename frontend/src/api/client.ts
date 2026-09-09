import type {
  Attachment,
  BookImageRef,
  ConfigResponse,
  Conversation,
  ConversationMessage,
  CurriculumResponse,
  LessonResponse,
  LoginResponse,
  MeResponse,
  OnboardingResponse,
  Override,
  Role,
  PriorExperience,
  Goal,
  StudyTime,
  LearnerType,
  RulesResponse,
  StudyModeState,
  TurnLogRecord,
  User,
  UserRole,
  UserStatus,
} from "../types";

export const BASE_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(
  /\/+$/,
  ""
);

const TOKEN_KEY = "itm-token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // ignore — private mode or blocked storage
  }
}

class ApiError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

/** Fired when a request comes back 401 so the app can drop to the login screen. */
export const AUTH_EXPIRED_EVENT = "itm-auth-expired";

function authHeaders(): Record<string, string> {
  const token = getToken();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function throwFromResponse(response: Response): Promise<never> {
  const body = await response.json().catch(() => ({ detail: response.statusText }));
  if (response.status === 401 && getToken()) {
    // A token we sent was rejected — drop it and let the app show the login screen.
    setToken(null);
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
  }
  throw new ApiError(response.status, body.detail ?? response.statusText);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, { headers: authHeaders(), ...init });
  if (!response.ok) await throwFromResponse(response);
  return response.json() as Promise<T>;
}

// --- Auth ---

export function register(username: string, password: string): Promise<{ status: string }> {
  return request("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function login(username: string, password: string): Promise<LoginResponse> {
  return request("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function getMe(): Promise<MeResponse> {
  return request("/api/auth/me");
}

// --- User management (admin) ---

export function listUsers(): Promise<User[]> {
  return request("/api/users");
}

export function createUser(username: string, password: string, role: UserRole): Promise<User> {
  return request("/api/users", {
    method: "POST",
    body: JSON.stringify({ username, password, role }),
  });
}

export function setUserStatus(userId: string, status: UserStatus): Promise<User> {
  return request(`/api/users/${userId}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
}

export function setUserRole(userId: string, role: UserRole): Promise<User> {
  return request(`/api/users/${userId}/role`, {
    method: "POST",
    body: JSON.stringify({ role }),
  });
}

export function onboard(answers: {
  role: Role;
  prior_experience: PriorExperience;
  goal: Goal;
  study_time: StudyTime;
  learner_type: LearnerType;
}): Promise<OnboardingResponse> {
  return request("/api/onboarding", { method: "POST", body: JSON.stringify(answers) });
}

export function getConfig(learnerId: string): Promise<ConfigResponse> {
  return request(`/api/config/${learnerId}`);
}

export function setOverride(learnerId: string, override: Override): Promise<ConfigResponse> {
  return request(`/api/config/${learnerId}/override`, {
    method: "PUT",
    body: JSON.stringify(override),
  });
}

export function revertOverrideField(learnerId: string, param: string): Promise<ConfigResponse> {
  return request(`/api/config/${learnerId}/override/${param}`, { method: "DELETE" });
}

export function resetOverrides(learnerId: string): Promise<ConfigResponse> {
  return request(`/api/config/${learnerId}/override`, { method: "DELETE" });
}

export function getRules(version = "v1"): Promise<RulesResponse> {
  return request(`/api/rules?version=${version}`);
}

export interface ChatStreamResult {
  conversationId: string;
  /** Book figures relevant to this turn (see `X-Book-Image-Ids`), in relevance order. */
  bookImages: BookImageRef[];
  /** Source pages this turn drew on (see `X-Book-Reference-Pages`), in relevance order. */
  pageRefs: number[];
}

/**
 * Sends one tutoring turn and streams the reply back as plain-text deltas,
 * calling `onDelta` for each chunk. Resolves once the stream ends.
 */
export async function streamChatMessage(
  learnerId: string,
  message: string,
  model: string | undefined,
  conversationId: string | null,
  attachmentIds: string[],
  onDelta: (chunk: string) => void,
): Promise<ChatStreamResult> {
  const body: Record<string, unknown> = { message };
  if (model) body.model = model;
  if (conversationId) body.conversation_id = conversationId;
  if (attachmentIds.length > 0) body.attachment_ids = attachmentIds;

  const response = await fetch(`${BASE_URL}/api/chat/${learnerId}`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  if (!response.ok || !response.body) {
    await throwFromResponse(response);
  }
  const resolvedId = response.headers.get("X-Conversation-Id") ?? conversationId ?? "";
  const bookImages = (response.headers.get("X-Book-Image-Ids") ?? "")
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean)
    .map((entry) => {
      const [id, page] = entry.split(":");
      return { id, page: Number(page) };
    });
  const pageRefs = (response.headers.get("X-Book-Reference-Pages") ?? "")
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean)
    .map(Number);
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    if (chunk) onDelta(chunk);
  }
  return { conversationId: resolvedId, bookImages, pageRefs };
}

/** Uploads a file, returning its metadata. `conversationId` may be null for
 * a fresh, unsaved thread -- the server links the attachment once the turn
 * that references it actually resolves a conversation. */
export async function uploadAttachment(
  learnerId: string,
  file: File,
  conversationId: string | null,
): Promise<Attachment> {
  const form = new FormData();
  form.append("file", file);
  if (conversationId) form.append("conversation_id", conversationId);

  const token = getToken();
  const response = await fetch(`${BASE_URL}/api/attachments/${learnerId}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: form,
  });
  if (!response.ok) await throwFromResponse(response);
  return response.json() as Promise<Attachment>;
}

/** Fetches an attachment's bytes (auth'd) and returns a blob object URL for
 * rendering (`<img src>`) or downloading. Caller should `URL.revokeObjectURL`
 * it once no longer needed. */
export async function fetchAttachmentObjectUrl(
  learnerId: string,
  attachmentId: string,
): Promise<string> {
  const response = await fetch(`${BASE_URL}/api/attachments/${learnerId}/${attachmentId}`, {
    headers: authHeaders(),
  });
  if (!response.ok) await throwFromResponse(response);
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

/** Fetches an extracted book figure's bytes (auth'd) and returns a blob
 * object URL for rendering. Caller should `URL.revokeObjectURL` it once no
 * longer needed. */
export async function fetchBookImageObjectUrl(imageId: string): Promise<string> {
  const response = await fetch(`${BASE_URL}/api/book-images/${imageId}`, {
    headers: authHeaders(),
  });
  if (!response.ok) await throwFromResponse(response);
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

/** Three candidate follow-up questions, generated fresh from `conversationId`'s
 * history so far. */
export function getFollowUpSuggestions(
  learnerId: string,
  conversationId: string,
): Promise<{ questions: string[] }> {
  return request(`/api/chat/${learnerId}/suggestions`, {
    method: "POST",
    body: JSON.stringify({ conversation_id: conversationId }),
  });
}

let bookPdfObjectUrl: Promise<string> | null = null;

/** Fetches the course textbook PDF (auth'd) once and caches its blob object
 * URL for the life of the tab, so repeated reference clicks don't re-fetch
 * an ~11MB file. Append `#page=N` to the returned URL when opening it. */
export function getBookPdfObjectUrl(): Promise<string> {
  if (!bookPdfObjectUrl) {
    bookPdfObjectUrl = fetch(`${BASE_URL}/api/book/pdf`, { headers: authHeaders() }).then(
      async (response) => {
        if (!response.ok) {
          bookPdfObjectUrl = null;
          await throwFromResponse(response);
        }
        const blob = await response.blob();
        return URL.createObjectURL(blob);
      },
    );
  }
  return bookPdfObjectUrl;
}

/** Generates a fresh chapter/section overview for the learner's current
 * training-mode selection. Not persisted anywhere -- call again whenever the
 * selection changes; discard the result once real messages exist. */
export function getChapterIntro(learnerId: string): Promise<{ text: string }> {
  return request(`/api/chapter-intro/${learnerId}`);
}

export function createLesson(learnerId: string): Promise<LessonResponse> {
  return request(`/api/lesson/${learnerId}`, { method: "POST" });
}

export function getLesson(conversationId: string): Promise<LessonResponse> {
  return request(`/api/lesson/${conversationId}`);
}

export function advanceLesson(conversationId: string): Promise<LessonResponse> {
  return request(`/api/lesson/${conversationId}/advance`, { method: "POST" });
}

export function abandonLesson(conversationId: string): Promise<LessonResponse> {
  return request(`/api/lesson/${conversationId}/abandon`, { method: "POST" });
}

export function listConversations(learnerId: string): Promise<Conversation[]> {
  return request(`/api/conversations/${learnerId}`);
}

export function getConversationMessages(
  learnerId: string,
  conversationId: string,
): Promise<ConversationMessage[]> {
  return request(`/api/conversations/${learnerId}/${conversationId}/messages`);
}

export function exportLog(learnerId: string): Promise<TurnLogRecord[]> {
  return request(`/api/export/${learnerId}`);
}

export function getCurriculum(): Promise<CurriculumResponse> {
  return request("/api/curriculum");
}

export function getStudyMode(learnerId: string): Promise<StudyModeState> {
  return request(`/api/mode/${learnerId}`);
}

export function updateStudyMode(
  learnerId: string,
  body: { mode: StudyModeState["mode"]; chapter_number?: string | null; section_number?: string | null },
): Promise<StudyModeState> {
  return request(`/api/mode/${learnerId}`, { method: "PUT", body: JSON.stringify(body) });
}

export { ApiError };
