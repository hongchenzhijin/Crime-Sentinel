import { Card, ErrorBox, Loading } from '../components/ui'
import { api } from '../lib/api'
import { fmtDateTime } from '../lib/categories'
import { useAsync } from '../lib/useAsync'

const DOES = [
  'Runs a governed research persona that seeks admission to closed communities on the sandbox platform, then observes them.',
  'Checks every persona message with an independent Safety Governor (hard rules + Muse judge) before a human approves it.',
  'Classifies observed content (text and images) and assesses whole communities with cited evidence.',
  'Drafts evidence-backed reports for the platform integrity team. Nothing is sent without human approval.',
  'Lets reviewers confirm, correct, or mark items uncertain, with a full audit trail.',
]
const DOES_NOT = [
  'Post, praise, encourage, agree to plans, or start violent topics (rules R1-R3, R8).',
  'Pose as a minor or student, or impersonate police, officials, journalists or researchers (R4, R9).',
  'Enter victim, survivor, or support spaces (R6).',
  'Identify, deanonymise, locate, or profile people outside the platform.',
  'Produce individual threat scores, or contact police or schools. Humans decide escalations.',
  'Operate on a real platform. This prototype runs only on the sandbox. A real deployment would have to be operated by the platform itself.',
]

export function SafetyPage() {
  const audit = useAsync(() => api.audit(100), [])
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="What Crime Sentinel does">
        <ul className="list-disc space-y-1 pl-4 text-sm">{DOES.map((d) => <li key={d}>{d}</li>)}</ul>
      </Card>
      <Card title="What it does not do">
        <ul className="list-disc space-y-1 pl-4 text-sm">{DOES_NOT.map((d) => <li key={d}>{d}</li>)}</ul>
      </Card>
      <Card title="Privacy safeguards">
        <ul className="list-disc space-y-1 pl-4 text-sm text-ink-2">
          <li>Emails, links, @handles, and phone numbers are redacted from text at ingestion.</li>
          <li>Author references are salted one-way hashes; the salt is discarded after each load, so no mapping exists.</li>
          <li>Interaction references are kept only when they point to other posts, never accounts.</li>
          <li>Data is stored locally in SQLite with a configurable retention period and a delete-all command.</li>
          <li>Exports contain aggregates and redacted excerpts; harmful-category text is withheld.</li>
        </ul>
      </Card>
      <Card title="Reviewer wellbeing">
        <ul className="list-disc space-y-1 pl-4 text-sm text-ink-2">
          <li>Harmful-category text is hidden in lists and behind an explicit "show text" step.</li>
          <li>The UI never generates graphic descriptions; it only shows the original permitted text.</li>
          <li>Take regular breaks and use your organisation's support services after difficult sessions.</li>
        </ul>
      </Card>
      <Card title="Audit log" subtitle="Ingestion, reviewer actions, and exports (most recent first)." className="lg:col-span-2">
        {audit.error && <ErrorBox error={audit.error} onRetry={audit.reload} />}
        {audit.loading && !audit.data && <Loading />}
        {audit.data && (
          <div className="max-h-96 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-surface">
                <tr className="text-left text-ink-2"><th className="py-1 font-medium">Time</th><th className="font-medium">Actor</th><th className="font-medium">Action</th><th className="font-medium">Post</th><th className="font-medium">Details</th></tr>
              </thead>
              <tbody className="divide-y divide-line">
                {audit.data.map((e) => (
                  <tr key={e.id} className="align-top">
                    <td className="py-1.5 whitespace-nowrap text-ink-3">{fmtDateTime(e.timestamp)}</td>
                    <td>{e.actor}</td>
                    <td>{e.action}</td>
                    <td className="font-mono">{e.post_id ?? '—'}</td>
                    <td className="max-w-md truncate font-mono text-[11px] text-ink-3" title={JSON.stringify(e.details)}>{JSON.stringify(e.details)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <button onClick={audit.reload} className="mt-2 text-xs text-accent hover:underline">Refresh</button>
      </Card>
    </div>
  )
}
