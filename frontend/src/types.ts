// Mirrors the JSON returned by api.py.

export type Requirement = { id: string; text: string; keywords: string[] }

export type Requirements = {
  company: string
  role: string
  location: string | null
  description: string
  responsibilities: string[]
  must_have: Requirement[]
  nice_to_have: Requirement[]
}

export type Match = {
  requirement_id: string
  strength: 'strong' | 'partial' | 'none'
  evidence_ids: string[]
  rationale: string
}

export type Analysis = {
  requirements: Requirements
  mapping: { matches: Match[] }
  headline: string
  my_contribution: string
  my_profile: string[]
  core_skills: string[]
}

export type Answer = { question: string; answer: string }

export type Clarification = { questions: string[]; answers: Answer[] | null }

export type Item = {
  id: number
  role_id: string
  requirement_id: string
  bullet: string | null
  source_ids: string[]
  selected: boolean
  position: number
  clarification: Clarification | null
}

export type RoleView = {
  role_id: string
  period: string
  employer: string
  original_title: string
  title: string
  items: Item[]
  /** Bullets from the CV database the export uses when no item of the role is selected. */
  baseline: string[]
}

export type Stage =
  | 'queued'
  | 'load_cv'
  | 'load_job'
  | 'extract_requirements'
  | 'map_requirements'
  | 'write_cv'
  | 'render_cv'
  | 'saving'
  | 'done'
  | 'error'

/** Application pipeline, in order (mirrors db.STATUSES). */
export const STATUSES = [
  { id: 'incoming', label: 'Incoming' },
  { id: 'tailored', label: 'Tailored' },
  { id: 'submitted', label: 'Submitted' },
  { id: 'sent_to_rav', label: 'Sent to RAV' },
] as const

export const statusLabel = (id: string) => STATUSES.find((s) => s.id === id)?.label ?? id

export type JobSummary = {
  id: number
  url: string | null
  company: string | null
  role: string | null
  location: string | null
  status: string
  interview_scheduled: boolean
  stage: Stage
  submitted_at: string | null
  created_at: string
}

export type Job = JobSummary & {
  description: string | null
  error: string | null
  updated_at: string
  status_history: { status: string; changed_at: string }[]
}

/** A reference/*cv*.pdf; `styled` when it has its own CSS, otherwise the default style is used. */
export type CvTemplate = { name: string; styled: boolean }

export type CvDocument ={ id: number; markdown: string; path: string | null; created_at: string }

export type JobDetail = {
  job: Job
  statuses: string[]
  analysis: Analysis | null
  roles: RoleView[]
  document: CvDocument | null
}
