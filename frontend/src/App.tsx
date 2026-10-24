import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { ClarifyModal } from './ClarifyModal'
import { JobsTable, type JobFields } from './JobsTable'
import {
  EditableText,
  ExportModal,
  GroupBySwitch,
  JobPanel,
  ProgressPanel,
  RoleSection,
  SkillSection,
  SkillsOverview,
  Tracker,
  ValueProposition,
  requirementRows,
  type GroupBy,
} from './components'
import type { CvDocument, CvTemplate, Item, JobDetail, JobSummary, RoleView } from './types'

const FINISHED = new Set(['done', 'error'])
const LAST_JOB_KEY = 'job-tailored-cv:last-job'
const GROUP_BY_KEY = 'job-tailored-cv:group-by'
const TEMPLATE_KEY = 'job-tailored-cv:pdf-template'

export default function App() {
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [jobId, setJobId] = useState<number | null>(() => {
    const saved = Number(localStorage.getItem(LAST_JOB_KEY))
    return Number.isFinite(saved) && saved > 0 ? saved : null
  })
  const [detail, setDetail] = useState<JobDetail | null>(null)
  const [url, setUrl] = useState('')
  const [pasted, setPasted] = useState('')
  const [showPaste, setShowPaste] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hideEmpty, setHideEmpty] = useState(false)
  const [groupBy, setGroupBy] = useState<GroupBy>(() =>
    localStorage.getItem(GROUP_BY_KEY) === 'skill' ? 'skill' : 'period',
  )
  const [clarifying, setClarifying] = useState<{ item: Item; role: RoleView } | null>(null)
  const [exported, setExported] = useState<CvDocument | null>(null)
  const [exporting, setExporting] = useState(false)
  const [templates, setTemplates] = useState<CvTemplate[]>([])
  const [template, setTemplate] = useState(() => localStorage.getItem(TEMPLATE_KEY) ?? '')
  const [exportingPdf, setExportingPdf] = useState(false)

  const fail = (e: unknown) => setError((e as Error).message)
  const refreshJobs = useCallback(() => api.listJobs().then(setJobs).catch(fail), [])

  useEffect(() => {
    void refreshJobs()
  }, [refreshJobs])

  // Keep the jobs table current while any analysis runs in the background.
  const anyRunning = jobs.some((j) => !FINISHED.has(j.stage))
  useEffect(() => {
    if (jobId !== null || !anyRunning) return
    const timer = setInterval(() => void refreshJobs(), 3000)
    return () => clearInterval(timer)
  }, [jobId, anyRunning, refreshJobs])

  const showJobs = () => {
    localStorage.removeItem(LAST_JOB_KEY)
    setJobId(null)
    void refreshJobs()
  }

  const updateJobFields = (job: JobSummary, fields: JobFields) => {
    setJobs((list) => list.map((j) => (j.id === job.id ? { ...j, ...fields } : j))) // optimistic
    api
      .updateJob(job.id, fields)
      .then((next) => {
        if (detail?.job.id === job.id) setDetail(next)
        return refreshJobs() // picks up the submitted date set on "Submitted"
      })
      .catch((err) => {
        fail(err)
        void refreshJobs()
      })
  }

  useEffect(() => {
    api
      .listTemplates()
      .then((list) => {
        setTemplates(list)
        // Keep the remembered template while it still exists in reference/.
        setTemplate((current) => (list.some((t) => t.name === current) ? current : (list[0]?.name ?? '')))
      })
      .catch(fail)
  }, [])

  useEffect(() => {
    if (jobId === null) {
      setDetail(null)
      return
    }
    localStorage.setItem(LAST_JOB_KEY, String(jobId))
    api.getJob(jobId).then(setDetail).catch(() => {
      localStorage.removeItem(LAST_JOB_KEY)
      setJobId(null)
    })
  }, [jobId])

  // Poll while the analysis graph runs in the background.
  const stage = detail?.job.stage
  useEffect(() => {
    if (!jobId || !stage || FINISHED.has(stage)) return
    const timer = setInterval(async () => {
      const next = await api.getJob(jobId).catch(() => null)
      if (!next) return
      setDetail(next)
      if (FINISHED.has(next.job.stage)) void refreshJobs()
    }, 2000)
    return () => clearInterval(timer)
  }, [jobId, stage, refreshJobs])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const created = await api.createJob(url, pasted)
      setDetail(created)
      setJobId(created.job.id)
      setUrl('')
      setPasted('')
      setShowPaste(false)
      void refreshJobs()
    } catch (err) {
      fail(err)
    } finally {
      setSubmitting(false)
    }
  }

  const requirements = useMemo(() => (detail?.analysis ? requirementRows(detail.analysis) : []), [detail?.analysis])

  const replaceItem = (item: Item) =>
    setDetail((d) =>
      d && {
        ...d,
        roles: d.roles.map((r) =>
          r.role_id !== item.role_id
            ? r
            : r.items.some((i) => i.id === item.id)
              ? { ...r, items: r.items.map((i) => (i.id === item.id ? item : i)) }
              : { ...r, items: [...r.items, item] },
        ),
      },
    )

  const changeGroupBy = (value: GroupBy) => {
    setGroupBy(value)
    localStorage.setItem(GROUP_BY_KEY, value)
  }

  const createItem = async (role: RoleView, requirementId: string) => {
    if (!detail) return
    try {
      const item = await api.createItem(detail.job.id, role.role_id, requirementId)
      replaceItem(item)
      return item
    } catch (err) {
      fail(err)
    }
  }

  const saveItem = (item: Item, fields: { bullet?: string | null; selected?: boolean }) => {
    if (!detail) return
    replaceItem({ ...item, ...fields }) // optimistic
    api.updateItem(detail.job.id, item.id, fields).then(replaceItem).catch(fail)
  }

  const withJob = (action: (id: number) => Promise<JobDetail>) => {
    if (!detail) return
    action(detail.job.id)
      .then((next) => {
        setDetail(next)
        void refreshJobs()
      })
      .catch(fail)
  }

  const deleteJob = async () => {
    if (!detail || !window.confirm(`Delete ${detail.job.company ?? 'this job'} and its tailored CV?`)) return
    await api.deleteJob(detail.job.id).catch(fail)
    showJobs()
  }

  const exportCv = async () => {
    if (!detail) return
    setExporting(true)
    try {
      const document = await api.exportCv(detail.job.id)
      setExported(document)
      setDetail({ ...detail, document })
    } catch (err) {
      fail(err)
    } finally {
      setExporting(false)
    }
  }

  const changeTemplate = (name: string) => {
    setTemplate(name)
    localStorage.setItem(TEMPLATE_KEY, name)
  }

  const exportPdf = async () => {
    if (!detail || !template) return
    setExportingPdf(true)
    try {
      const { blob, filename } = await api.exportPdf(detail.job.id, template)
      const link = Object.assign(window.document.createElement('a'), { href: URL.createObjectURL(blob), download: filename })
      link.click()
      URL.revokeObjectURL(link.href)
      setDetail(await api.getJob(detail.job.id)) // the Markdown is saved with it
    } catch (err) {
      fail(err)
    } finally {
      setExportingPdf(false)
    }
  }

  const ready = detail?.analysis && detail.job.stage === 'done'

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <strong>Job-tailored CV</strong>
          <button className={jobId === null ? 'secondary small active' : 'secondary small'} onClick={showJobs}>
            All jobs ({jobs.length})
          </button>
        </div>
        <form className="url-form" onSubmit={submit}>
          <input
            type="url"
            placeholder="Paste the job ad URL…"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            aria-label="Job ad URL"
          />
          <button type="button" className="secondary" onClick={() => setShowPaste(!showPaste)}>
            {showPaste ? 'Hide text' : 'Paste Job description'}
          </button>
          <button className="primary" disabled={submitting || (!url.trim() && !pasted.trim())}>
            {submitting ? 'Starting…' : 'Analyze'}
          </button>
          {showPaste && (
            <textarea
              className="paste"
              placeholder="LinkedIn and other login-walled sites can't be fetched — paste the job description here (the URL is still saved)."
              value={pasted}
              onChange={(e) => setPasted(e.target.value)}
              rows={6}
            />
          )}
        </form>
      </header>

      {error && (
        <div className="banner error" role="alert">
          {error}
          <button className="icon-button" onClick={() => setError(null)} aria-label="Dismiss">
            ×
          </button>
        </div>
      )}

      {!detail && jobs.length > 0 && <JobsTable jobs={jobs} onOpen={setJobId} onUpdate={updateJobFields} />}
      {!detail && jobs.length === 0 && (
        <main className="empty-state">
          <h1>Tailor your CV to a job</h1>
          <p className="muted">
            Paste a job ad URL above (or its text). The CV writer extracts the requirements, maps them to every work
            period of your CV database and drafts goal-oriented bullets you can pick, edit and clarify.
          </p>
        </main>
      )}

      {detail && (
        <div className={ready ? 'layout' : 'layout single'}>
          <main className="content">
            <JobPanel
              detail={detail}
              onUpdate={(fields) => withJob((id) => api.updateJob(id, fields))}
              onRerun={() => withJob(api.rerun)}
              onDelete={deleteJob}
            />
            {!ready && <ProgressPanel stage={detail.job.stage} error={detail.job.error} onRerun={() => withJob(api.rerun)} />}
            {ready && detail.analysis && (
              <>
                <ValueProposition
                  analysis={detail.analysis}
                  onSave={(fields) => withJob((id) => api.updateAnalysis(id, fields))}
                />
                <div className="section-bar">
                  <h2 className="section-title">Business Experience</h2>
                  <GroupBySwitch value={groupBy} onChange={changeGroupBy} />
                </div>
                <label className="cv-title-field">
                  CV title — shown under your name on the CV and PDF
                  <EditableText
                    className="cv-title"
                    value={detail.analysis.headline}
                    ariaLabel="CV title"
                    placeholder="e.g. Senior Backend Engineer | Java & Spring Boot"
                    onSave={(value) => value.trim() && withJob((id) => api.updateAnalysis(id, { headline: value.trim() }))}
                  />
                </label>
                {groupBy === 'period' &&
                  detail.roles.map((role) => (
                    <RoleSection
                      key={role.role_id}
                      role={role}
                      requirements={requirements}
                      hideEmpty={hideEmpty}
                      onItemSave={saveItem}
                      onClarify={(item, r) => setClarifying({ item, role: r })}
                      onTitleSave={(title) => withJob((id) => api.updateRoleTitle(id, role.role_id, title))}
                    />
                  ))}
                {groupBy === 'skill' && (
                  <>
                    <SkillsOverview requirements={requirements} roles={detail.roles} />
                    {requirements.map((requirement) => (
                      <SkillSection
                        key={requirement.id}
                        requirement={requirement}
                        roles={detail.roles}
                        onItemSave={saveItem}
                        onItemCreate={createItem}
                        onClarify={(item, r) => setClarifying({ item, role: r })}
                      />
                    ))}
                  </>
                )}
              </>
            )}
          </main>
          {ready && (
            <Tracker
              requirements={requirements}
              roles={detail.roles}
              document={detail.document}
              groupBy={groupBy}
              hideEmpty={hideEmpty}
              onHideEmptyChange={setHideEmpty}
              onExport={exportCv}
              exporting={exporting}
              templates={templates}
              template={template}
              onTemplateChange={changeTemplate}
              onExportPdf={exportPdf}
              exportingPdf={exportingPdf}
            />
          )}
        </div>
      )}

      {clarifying && detail && (
        <ClarifyModal
          jobId={detail.job.id}
          item={clarifying.item}
          role={clarifying.role}
          requirement={requirements.find((r) => r.id === clarifying.item.requirement_id)!}
          onClose={() => setClarifying(null)}
          onItemChange={replaceItem}
        />
      )}
      {exported && <ExportModal document={exported} onClose={() => setExported(null)} />}
    </div>
  )
}
