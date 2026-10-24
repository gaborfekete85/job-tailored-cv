import type { ReactNode } from 'react'
import { STATUSES, type JobSummary } from './types'

export type JobFields = { status?: string; interview_scheduled?: boolean }

type Props = {
  jobs: JobSummary[]
  onOpen: (id: number) => void
  onUpdate: (job: JobSummary, fields: JobFields) => void
}

const COLUMNS = 7

/** Furthest along first, so ↑ moves a job into the table above (its next status). */
const ORDER = [...STATUSES].reverse()

/** All jobs, one table per pipeline status. */
export function JobsTable({ jobs, onOpen, onUpdate }: Props) {
  const onStatusChange = (job: JobSummary, status: string) => onUpdate(job, { status })
  return (
    <main className="jobs">
      {ORDER.map((status, n) => {
        const rows = jobs.filter((j) => j.status === status.id)
        const interviews = rows.filter((j) => j.interview_scheduled)
        const others = rows.filter((j) => !j.interview_scheduled)
        const above = ORDER[n - 1]
        const below = ORDER[n + 1]
        // Interviews first, under their own sub-heading when the table has both kinds.
        const group = (title: string, list: JobSummary[]): ReactNode[] => [
          interviews.length > 0 && others.length > 0 && list.length > 0 && (
            <tr key={title} className="group-row">
              <td colSpan={COLUMNS}>{title}</td>
            </tr>
          ),
          ...list.map(row),
        ]
        const row = (job: JobSummary) => (
          <tr key={job.id} className={job.interview_scheduled ? 'interview' : ''}>
            <td>
              <button className="link-button" onClick={() => onOpen(job.id)}>
                {job.company ?? `Job #${job.id}`}
              </button>
              {job.url && (
                <a href={job.url} target="_blank" rel="noreferrer" title="Open the original job ad">
                  {' ↗'}
                </a>
              )}
              {job.interview_scheduled && <span className="badge interview">Interview</span>}
              {job.stage !== 'done' && (
                <span className={job.stage === 'error' ? 'stage error' : 'stage'}>
                  {job.stage === 'error' ? 'failed' : 'analyzing…'}
                </span>
              )}
            </td>
            <td>{job.role ?? '—'}</td>
            <td className="muted">{job.location ?? '—'}</td>
            <td className="nowrap">{job.created_at.slice(0, 10)}</td>
            <td className="nowrap">{job.submitted_at ?? '—'}</td>
            <td>
              <select
                aria-label={`Status of ${job.company ?? `job ${job.id}`}`}
                value={job.status}
                onChange={(e) => onStatusChange(job, e.target.value)}
              >
                {ORDER.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
            </td>
            <td className="move">
              <button
                className={job.interview_scheduled ? 'small interview-toggle on' : 'secondary small interview-toggle'}
                aria-pressed={job.interview_scheduled}
                title={job.interview_scheduled ? 'Interview scheduled — click to clear' : 'Mark: interview scheduled'}
                onClick={() => onUpdate(job, { interview_scheduled: !job.interview_scheduled })}
              >
                Interview
              </button>
              <button
                className="secondary small"
                disabled={!above}
                title={above && `Move on to ${above.label}`}
                aria-label={above ? `Move on to ${above.label}` : 'Already last status'}
                onClick={() => above && onStatusChange(job, above.id)}
              >
                ↑
              </button>
              <button
                className="secondary small"
                disabled={!below}
                title={below && `Move back to ${below.label}`}
                aria-label={below ? `Move back to ${below.label}` : 'Already first status'}
                onClick={() => below && onStatusChange(job, below.id)}
              >
                ↓
              </button>
            </td>
          </tr>
        )
        return (
          <section key={status.id} className={`card jobs-group status-${status.id}`}>
            <header className="jobs-head">
              <h2>{status.label}</h2>
              <span className="pill">{rows.length}</span>
              {interviews.length > 0 && <span className="badge interview">{interviews.length} interview{interviews.length > 1 ? 's' : ''}</span>}
            </header>
            {rows.length === 0 ? (
              <p className="muted small-text">No jobs.</p>
            ) : (
              <table className="jobs-table">
                <thead>
                  <tr>
                    <th>Company</th>
                    <th>Role</th>
                    <th>Location</th>
                    <th>Added</th>
                    <th>Submitted</th>
                    <th>Status</th>
                    <th aria-label="Move" />
                  </tr>
                </thead>
                <tbody>
                  {group('Interview scheduled', interviews)}
                  {group('Other', others)}
                </tbody>
              </table>
            )}
          </section>
        )
      })}
    </main>
  )
}
