import { useEffect, useState } from 'react'
import { statusLabel } from './types'
import type { Analysis, CvDocument, CvTemplate, Item, JobDetail, Match, Requirement, RoleView, Stage } from './types'

// --- shared --------------------------------------------------------------------------

export type RequirementRow = Requirement & { kind: 'must' | 'nice'; match?: Match }

export function requirementRows(analysis: Analysis): RequirementRow[] {
  const matches = new Map(analysis.mapping.matches.map((m) => [m.requirement_id, m]))
  return [
    ...analysis.requirements.must_have.map((r) => ({ ...r, kind: 'must' as const, match: matches.get(r.id) })),
    ...analysis.requirements.nice_to_have.map((r) => ({ ...r, kind: 'nice' as const, match: matches.get(r.id) })),
  ]
}

type EditableTextProps = {
  value: string
  onSave: (value: string) => void
  placeholder?: string
  className?: string
  ariaLabel?: string
}

/** Textarea that grows with its content and saves on blur when changed. */
export function EditableText({ value, onSave, placeholder, className, ariaLabel }: EditableTextProps) {
  const [draft, setDraft] = useState(value)
  useEffect(() => setDraft(value), [value])
  return (
    <textarea
      className={`editable ${className ?? ''}`}
      value={draft}
      placeholder={placeholder}
      aria-label={ariaLabel}
      rows={1}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => draft !== value && onSave(draft)}
    />
  )
}

// --- job header ----------------------------------------------------------------------

type JobPanelProps = {
  detail: JobDetail
  onUpdate: (fields: Record<string, string | boolean | null>) => void
  onRerun: () => void
  onDelete: () => void
}

export function JobPanel({ detail, onUpdate, onRerun, onDelete }: JobPanelProps) {
  const { job, statuses } = detail
  const running = job.stage !== 'done' && job.stage !== 'error'
  return (
    <section className="card job-panel">
      <div className="job-title">
        <div>
          <p className="eyebrow">{job.company ?? 'Company pending'}</p>
          <h1>{job.role ?? 'Analyzing job ad…'}</h1>
          <p className="muted">
            {job.location ?? '—'}
            {job.url && (
              <>
                {' · '}
                <a href={job.url} target="_blank" rel="noreferrer">
                  Job ad ↗
                </a>
              </>
            )}
          </p>
        </div>
        <div className="job-actions">
          <button className="secondary small" onClick={onRerun} disabled={running}>
            Re-run analysis
          </button>
          <button className="danger small" onClick={onDelete} disabled={running}>
            Delete
          </button>
        </div>
      </div>

      <div className="status-row">
        <label>
          Status
          <select value={job.status} onChange={(e) => onUpdate({ status: e.target.value })}>
            {statuses.map((s) => (
              <option key={s} value={s}>
                {statusLabel(s)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Submitted
          <input
            type="date"
            value={job.submitted_at ?? ''}
            onChange={(e) => onUpdate({ submitted_at: e.target.value || null })}
          />
        </label>
        <button
          className={job.interview_scheduled ? 'small interview-toggle on' : 'secondary small interview-toggle'}
          aria-pressed={job.interview_scheduled}
          onClick={() => onUpdate({ interview_scheduled: !job.interview_scheduled })}
        >
          {job.interview_scheduled ? 'Interview scheduled ✓' : 'Interview scheduled?'}
        </button>
        <label>
          Job ad link
          <input
            key={job.url ?? ''}
            type="url"
            placeholder="https://…"
            defaultValue={job.url ?? ''}
            onBlur={(e) => {
              const value = e.target.value.trim()
              if (value !== (job.url ?? '')) onUpdate({ url: value || null })
            }}
          />
        </label>
        <span className="muted small-text">Added {job.created_at.slice(0, 10)}</span>
      </div>

      {job.description && (
        <details className="description">
          <summary>Job description</summary>
          <div className="description-text">{job.description}</div>
        </details>
      )}
    </section>
  )
}

// --- analysis progress -----------------------------------------------------------------

const STAGES: { stage: Stage; label: string }[] = [
  { stage: 'load_cv', label: 'Loading your CV database' },
  { stage: 'load_job', label: 'Reading the job ad' },
  { stage: 'extract_requirements', label: 'Extracting company, role and requirements' },
  { stage: 'map_requirements', label: 'Mapping requirements to your experience' },
  { stage: 'write_cv', label: 'Writing tailored bullets for every work period' },
  { stage: 'render_cv', label: 'Rendering the CV' },
  { stage: 'saving', label: 'Saving' },
]

export function ProgressPanel({ stage, error, onRerun }: { stage: Stage; error: string | null; onRerun: () => void }) {
  if (stage === 'error') {
    return (
      <section className="card progress error-card">
        <h2>Analysis failed</h2>
        <p className="error">{error}</p>
        <button className="primary" onClick={onRerun}>
          Try again
        </button>
      </section>
    )
  }
  const current = STAGES.findIndex((s) => s.stage === stage)
  return (
    <section className="card progress">
      <h2>Tailoring your CV…</h2>
      <p className="muted">This takes 2–3 minutes. You can leave this page open.</p>
      <ol className="steps">
        {STAGES.map((s, n) => (
          <li key={s.stage} className={n < current ? 'done' : n === current ? 'active' : ''}>
            {s.label}
          </li>
        ))}
      </ol>
    </section>
  )
}

// --- value proposition -------------------------------------------------------------------

type ValuePropositionProps = {
  analysis: Analysis
  onSave: (fields: { my_contribution?: string; my_profile?: string[] }) => void
}

export function ValueProposition({ analysis, onSave }: ValuePropositionProps) {
  const profile = analysis.my_profile
  const saveProfile = (next: string[]) => onSave({ my_profile: next.map((p) => p.trim()).filter(Boolean) })
  return (
    <section className="card">
      <h2>Value Proposition</h2>
      <h3>My Contribution</h3>
      <EditableText
        className="contribution"
        value={analysis.my_contribution}
        ariaLabel="My Contribution"
        onSave={(my_contribution) => onSave({ my_contribution })}
      />
      <h3>My Profile</h3>
      <ul className="profile-list">
        {profile.map((point, n) => (
          <li key={`${n}-${point}`}>
            <EditableText
              value={point}
              ariaLabel={`Profile bullet ${n + 1}`}
              onSave={(value) => saveProfile(profile.map((p, i) => (i === n ? value : p)))}
            />
          </li>
        ))}
      </ul>
      <button className="link-button" onClick={() => onSave({ my_profile: [...profile, 'New profile bullet'] })}>
        + Add bullet
      </button>
    </section>
  )
}

// --- one work period: requirements left, candidate bullets right -------------------------

type RoleSectionProps = {
  role: RoleView
  requirements: RequirementRow[]
  hideEmpty: boolean
  onItemSave: (item: Item, fields: { bullet?: string | null; selected?: boolean }) => void
  onClarify: (item: Item, role: RoleView) => void
  onTitleSave: (title: string) => void
}

export function RoleSection({ role, requirements, hideEmpty, onItemSave, onClarify, onTitleSave }: RoleSectionProps) {
  const items = new Map(role.items.map((i) => [i.requirement_id, i]))
  const rows = requirements.filter((r) => items.has(r.id) && (!hideEmpty || items.get(r.id)!.bullet))
  const selectedCount = role.items.filter((i) => i.selected && i.bullet).length
  return (
    <section className="card role" id={`role-${role.role_id}`}>
      <header className="role-header">
        <span className="period">{role.period}</span>
        <EditableText className="role-title" value={role.title} ariaLabel="Role title" onSave={onTitleSave} />
        <span className="muted">{role.employer}</span>
        <span className="pill">{selectedCount} in CV</span>
      </header>
      <div className="grid-head">
        <span>Job requirement</span>
        <span>Tailored bullet candidate</span>
        <span />
      </div>
      {rows.map((req) => {
        const item = items.get(req.id)!
        return (
          <div key={req.id} className={`row ${item.selected && item.bullet ? 'selected' : ''} ${item.bullet ? '' : 'empty'}`}>
            <div className="req">
              <span className="req-id">{req.id}</span>
              <span className={`tag ${req.kind}`}>{req.kind === 'must' ? 'Must' : 'Nice'}</span>
              {req.match && <span className={`strength ${req.match.strength}`} title={req.match.rationale} />}
              <p>{req.text}</p>
            </div>
            <EditableText
              className="bullet"
              value={item.bullet ?? ''}
              ariaLabel={`Bullet for ${req.id}`}
              placeholder="No evidence in this role — use Clarify to add one"
              onSave={(bullet) => onItemSave(item, { bullet: bullet || null })}
            />
            <div className="row-actions">
              <label className="use" title="Use this bullet in the CV — marks the requirement as fulfilled">
                <input
                  type="checkbox"
                  checked={item.selected && !!item.bullet}
                  disabled={!item.bullet}
                  onChange={(e) => onItemSave(item, { selected: e.target.checked })}
                />
                Use
              </label>
              <button className="secondary small" onClick={() => onClarify(item, role)}>
                Clarify{item.clarification?.answers ? ' ✓' : ''}
              </button>
            </div>
          </div>
        )
      })}
      {rows.length === 0 && <p className="muted empty-note">No matching evidence in this period.</p>}
      {selectedCount === 0 && <BaselineNote role={role} />}
    </section>
  )
}

function BaselineNote({ role }: { role: RoleView }) {
  return (
    <details className="baseline-note">
      <summary>No bullet selected — the CV uses {role.baseline.length} baseline bullets from cv.md</summary>
      <ul>
        {role.baseline.map((text) => (
          <li key={text}>{text}</li>
        ))}
      </ul>
    </details>
  )
}

// --- one requirement: candidate bullets from every work period ----------------------------

/** Whether a role is in the CV for the requirement, has a draft, or only has evidence. */
type Suggestion = 'in-cv' | 'draft' | 'evidence' | 'none'

const SUGGESTION_ORDER: Suggestion[] = ['in-cv', 'draft', 'evidence', 'none']

function suggestion(item: Item | undefined, evidence: string[]): Suggestion {
  if (item?.bullet && item.selected) return 'in-cv'
  if (item?.bullet) return 'draft'
  return evidence.length ? 'evidence' : 'none'
}

function isCovered(requirementId: string, roles: RoleView[]) {
  return roles.some((r) => r.items.some((i) => i.requirement_id === requirementId && i.selected && i.bullet))
}

type SkillSectionProps = {
  requirement: RequirementRow
  roles: RoleView[]
  onItemSave: (item: Item, fields: { bullet?: string | null; selected?: boolean }) => void
  onItemCreate: (role: RoleView, requirementId: string) => Promise<Item | undefined>
  onClarify: (item: Item, role: RoleView) => void
}

export function SkillSection({ requirement, roles, onItemSave, onItemCreate, onClarify }: SkillSectionProps) {
  const evidenceIds = requirement.match?.evidence_ids ?? []
  const periods = roles
    .map((role) => {
      const item = role.items.find((i) => i.requirement_id === requirement.id)
      const evidence = evidenceIds.filter((id) => id.startsWith(`${role.role_id}.`))
      return { role, item, evidence, suggestion: suggestion(item, evidence) }
    })
    .sort((a, b) => SUGGESTION_ORDER.indexOf(a.suggestion) - SUGGESTION_ORDER.indexOf(b.suggestion))
  const proposed = periods.filter((p) => p.suggestion !== 'none')
  const others = periods.filter((p) => p.suggestion === 'none')
  const inCv = periods.filter((p) => p.suggestion === 'in-cv').length

  const row = ({ role, item, evidence, suggestion }: (typeof periods)[number]) => (
    <div key={role.role_id} className={`row ${suggestion === 'in-cv' ? 'selected' : ''} ${item?.bullet ? '' : 'empty'}`}>
      <div className="req">
        <span className="period">{role.period}</span>
        {suggestion === 'evidence' && <span className="tag suggest" title={`Evidence: ${evidence.join(', ')}`}>Suggested</span>}
        <p>
          {role.title}
          <span className="muted"> · {role.employer}</span>
        </p>
      </div>
      <EditableText
        className="bullet"
        value={item?.bullet ?? ''}
        ariaLabel={`Bullet for ${requirement.id} in ${role.period}`}
        placeholder={`During ${role.period}: what you did for this — and the measurable result. Start lines with - for several bullets.`}
        onSave={async (text) => {
          const bullet = text.trim() || null
          const target = item ?? (bullet ? await onItemCreate(role, requirement.id) : undefined)
          // A bullet written into a gap is meant for the CV.
          if (target) onItemSave(target, target.bullet ? { bullet } : { bullet, selected: !!bullet })
        }}
      />
      <div className="row-actions">
        <label className="use" title="Use this bullet in the CV — marks the requirement as fulfilled">
          <input
            type="checkbox"
            checked={!!item?.selected && !!item.bullet}
            disabled={!item?.bullet}
            onChange={(e) => item && onItemSave(item, { selected: e.target.checked })}
          />
          Use
        </label>
        <button
          className="secondary small"
          onClick={async () => {
            const target = item ?? (await onItemCreate(role, requirement.id))
            if (target) onClarify(target, role)
          }}
        >
          Clarify{item?.clarification?.answers ? ' ✓' : ''}
        </button>
      </div>
    </div>
  )

  return (
    <section className={`card skill ${inCv ? '' : 'gap'}`} id={`skill-${requirement.id}`}>
      <header className="skill-header">
        <div className="req">
          <span className="req-id">{requirement.id}</span>
          <span className={`tag ${requirement.kind}`}>{requirement.kind === 'must' ? 'Must' : 'Nice'}</span>
          {requirement.match && <span className={`strength ${requirement.match.strength}`} title={requirement.match.rationale} />}
          <p>{requirement.text}</p>
        </div>
        <span className={inCv ? 'pill' : 'pill gap'}>{inCv ? `In CV · ${inCv} period${inCv > 1 ? 's' : ''}` : 'Gap'}</span>
      </header>
      {requirement.match?.rationale && <p className="muted small-text skill-rationale">{requirement.match.rationale}</p>}
      <div className="grid-head">
        <span>Work period</span>
        <span>Tailored bullet</span>
        <span />
      </div>
      {proposed.map(row)}
      {proposed.length === 0 && (
        <p className="muted empty-note">No period has evidence yet — add a bullet to one below.</p>
      )}
      {others.length > 0 && (
        <details className="other-periods" open={proposed.length === 0}>
          <summary>Add a bullet from another period ({others.length})</summary>
          {others.map(row)}
        </details>
      )}
    </section>
  )
}

/** Gap summary on top of the skills view, and the periods that fall back to baseline bullets. */
export function SkillsOverview({ requirements, roles }: { requirements: RequirementRow[]; roles: RoleView[] }) {
  const gaps = requirements.filter((r) => !isCovered(r.id, roles))
  const fallback = roles.filter((r) => !r.items.some((i) => i.selected && i.bullet))
  return (
    <section className="card skills-overview">
      <p>
        <strong>
          {requirements.length - gaps.length} / {requirements.length}
        </strong>{' '}
        requirements covered.{' '}
        {gaps.length > 0 ? (
          <>
            Gaps:{' '}
            {gaps.map((r, n) => (
              <span key={r.id}>
                {n > 0 && ' · '}
                <a href={`#skill-${r.id}`}>{r.id}</a>
              </span>
            ))}
          </>
        ) : (
          'No gaps.'
        )}
      </p>
      {fallback.length > 0 && (
        <p className="muted small-text">
          No selected bullet in {fallback.map((r) => r.period).join(', ')} — the CV uses their baseline bullets from
          cv.md.
        </p>
      )}
    </section>
  )
}

export type GroupBy = 'period' | 'skill'

export function GroupBySwitch({ value, onChange }: { value: GroupBy; onChange: (value: GroupBy) => void }) {
  const options: { value: GroupBy; label: string }[] = [
    { value: 'period', label: 'Group by work period' },
    { value: 'skill', label: 'Group by skills' },
  ]
  return (
    <div className="segmented" role="radiogroup" aria-label="Group bullets">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          className={value === o.value ? 'active' : ''}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

// --- status tracker ----------------------------------------------------------------------

type TrackerProps = {
  requirements: RequirementRow[]
  roles: RoleView[]
  document: CvDocument | null
  groupBy: GroupBy
  hideEmpty: boolean
  onHideEmptyChange: (value: boolean) => void
  onExport: () => void
  exporting: boolean
  templates: CvTemplate[]
  template: string
  onTemplateChange: (name: string) => void
  onExportPdf: () => void
  exportingPdf: boolean
}

export function Tracker({
  requirements,
  roles,
  document,
  groupBy,
  hideEmpty,
  onHideEmptyChange,
  onExport,
  exporting,
  templates,
  template,
  onTemplateChange,
  onExportPdf,
  exportingPdf,
}: TrackerProps) {
  const uses = new Map<string, string[]>()
  for (const role of roles) {
    for (const item of role.items) {
      if (item.selected && item.bullet) uses.set(item.requirement_id, [...(uses.get(item.requirement_id) ?? []), role.period])
    }
  }
  const groups = [
    { title: 'Must-have', rows: requirements.filter((r) => r.kind === 'must') },
    { title: 'Nice-to-have', rows: requirements.filter((r) => r.kind === 'nice') },
  ]
  const totalBullets = [...uses.values()].reduce((sum, periods) => sum + periods.length, 0)

  return (
    <aside className="tracker">
      {groups.map(({ title, rows }) => {
        if (rows.length === 0) return null
        const done = rows.filter((r) => uses.has(r.id)).length
        return (
          <section key={title} className="tracker-group">
            <div className="tracker-head">
              <h3>{title}</h3>
              <span className={done === rows.length ? 'count complete' : 'count'}>
                {done} / {rows.length}
              </span>
            </div>
            <div className="progress-bar" aria-hidden>
              <span style={{ width: `${(done / rows.length) * 100}%` }} />
            </div>
            <p className="muted small-text">{rows.length - done} left</p>
            <ul className="tracker-list">
              {rows.map((r) => {
                const periods = uses.get(r.id)
                return (
                  <li key={r.id} className={periods ? 'fulfilled' : 'open'} title={periods ? `In CV: ${periods.join(', ')}` : r.match?.rationale}>
                    <span className="mark">{periods ? '✓' : '○'}</span>
                    <span className="req-id">{r.id}</span>
                    <span className="tracker-text">{r.text}</span>
                    {periods && periods.length > 1 && <span className="times">{periods.length}×</span>}
                  </li>
                )
              })}
            </ul>
          </section>
        )
      })}

      <section className="tracker-group">
        {/* The skills view always shows every period: empty ones are where the gaps get filled. */}
        {groupBy === 'period' && (
          <label className="toggle">
            <input type="checkbox" checked={hideEmpty} onChange={(e) => onHideEmptyChange(e.target.checked)} />
            Hide rows without evidence
          </label>
        )}
        <p className="muted small-text">{totalBullets} bullets selected for the CV</p>
        <button className="primary wide" onClick={onExport} disabled={exporting}>
          {exporting ? 'Exporting…' : 'Export CV (Markdown)'}
        </button>
        <label className="template-pick">
          PDF template
          <select value={template} onChange={(e) => onTemplateChange(e.target.value)} disabled={templates.length === 0}>
            {templates.length === 0 && <option value="">No reference/*cv*.pdf found</option>}
            {templates.map((t) => (
              <option key={t.name} value={t.name}>
                {t.name}
                {t.styled ? '' : ' (default style)'}
              </option>
            ))}
          </select>
        </label>
        <button className="secondary wide" onClick={onExportPdf} disabled={exportingPdf || !template}>
          {exportingPdf ? 'Printing PDF…' : 'Export CV (PDF)'}
        </button>
        {document && (
          <p className="muted small-text">
            Last saved {document.created_at.slice(0, 16).replace('T', ' ')}
            {document.path && (
              <>
                <br />
                <code>{document.path.split('/').slice(-2).join('/')}</code>
              </>
            )}
          </p>
        )}
      </section>
    </aside>
  )
}

// --- export preview ------------------------------------------------------------------------

export function ExportModal({ document, onClose }: { document: CvDocument; onClose: () => void }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    await navigator.clipboard.writeText(document.markdown)
    setCopied(true)
  }
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal wide" role="dialog" aria-modal="true" aria-labelledby="export-title">
        <header className="modal-header">
          <div>
            <p className="eyebrow">Saved to {document.path}</p>
            <h2 id="export-title">Tailored CV</h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>
        <pre className="markdown-preview">{document.markdown}</pre>
        <footer className="modal-footer">
          <button className="secondary" onClick={copy}>
            {copied ? 'Copied' : 'Copy Markdown'}
          </button>
          <button className="primary" onClick={onClose}>
            Done
          </button>
        </footer>
      </div>
    </div>
  )
}
