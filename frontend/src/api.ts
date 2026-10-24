import type { Answer, CvDocument, CvTemplate, Item, JobDetail, JobSummary } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = body?.detail
    const message = Array.isArray(detail)
      ? detail.map((d: { msg: string }) => d.msg).join('; ')
      : (detail ?? response.statusText)
    throw new Error(message)
  }
  return response.status === 204 ? (undefined as T) : response.json()
}

const json = (body: unknown) => JSON.stringify(body)

export const api = {
  listJobs: () => request<JobSummary[]>('/jobs'),
  getJob: (id: number) => request<JobDetail>(`/jobs/${id}`),
  createJob: (url: string, description: string) =>
    request<JobDetail>('/jobs', { method: 'POST', body: json({ url, description }) }),
  rerun: (id: number) => request<JobDetail>(`/jobs/${id}/analyze`, { method: 'POST' }),
  deleteJob: (id: number) => request<void>(`/jobs/${id}`, { method: 'DELETE' }),
  updateJob: (id: number, fields: Record<string, string | boolean | null>) =>
    request<JobDetail>(`/jobs/${id}`, { method: 'PATCH', body: json(fields) }),
  updateAnalysis: (id: number, fields: { my_contribution?: string; my_profile?: string[]; headline?: string }) =>
    request<JobDetail>(`/jobs/${id}/analysis`, { method: 'PATCH', body: json(fields) }),
  updateRoleTitle: (id: number, roleId: string, title: string) =>
    request<JobDetail>(`/jobs/${id}/roles/${roleId}`, { method: 'PATCH', body: json({ title }) }),
  createItem: (id: number, roleId: string, requirementId: string) =>
    request<Item>(`/jobs/${id}/items`, { method: 'POST', body: json({ role_id: roleId, requirement_id: requirementId }) }),
  updateItem: (id: number, itemId: number, fields: { bullet?: string | null; selected?: boolean }) =>
    request<Item>(`/jobs/${id}/items/${itemId}`, { method: 'PATCH', body: json(fields) }),
  askQuestions: (id: number, itemId: number) =>
    request<Item>(`/jobs/${id}/items/${itemId}/questions`, { method: 'POST' }),
  refine: (id: number, itemId: number, answers: Answer[]) =>
    request<Item>(`/jobs/${id}/items/${itemId}/refine`, { method: 'POST', body: json({ answers }) }),
  exportCv: (id: number) => request<CvDocument>(`/jobs/${id}/export`, { method: 'POST' }),
  listTemplates: () => request<CvTemplate[]>('/cv-templates'),
  exportPdf: async (id: number, template: string) => {
    const response = await fetch(`/api/jobs/${id}/export/pdf`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: json({ template }),
    })
    if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? response.statusText)
    const filename = /filename="(.+)"/.exec(response.headers.get('Content-Disposition') ?? '')?.[1] ?? 'cv.pdf'
    return { blob: await response.blob(), filename }
  },
}
