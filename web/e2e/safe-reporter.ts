import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import type { FullConfig, FullResult, Reporter, Suite, TestCase, TestResult } from '@playwright/test/reporter'

const statuses = ['passed', 'failed', 'timedOut', 'interrupted', 'skipped'] as const
type Status = typeof statuses[number]
type Outcome = 'expected' | 'unexpected' | 'flaky' | 'skipped' | 'NOT_RUN'
type Attempt = { status: Status; expected_status: Status; retry: number; duration_ms: number }
const statusCounts = () => ({ passed: 0, failed: 0, timedOut: 0, interrupted: 0, skipped: 0 })
const safeNumber = (value: number) => Number.isFinite(value) && value >= 0 ? Math.floor(value) : 0
const safeStatus = (value: Status): Status => statuses.includes(value) ? value : 'interrupted'

/** Only anonymous ordinals, closed enums and numbers leave this reporter.
 * Never serialize test IDs/titles, filenames, errors, annotations or attachments.
 */
export default class SafeReporter implements Reporter {
  private readonly reportDir: string
  private readonly discoveryOnly: boolean
  private readonly tests = new Map<string, { test: TestCase; attempts: Attempt[] }>()
  private errors = 0

  constructor(options: { reportDir: string; discoveryOnly: boolean }) {
    this.reportDir = options.reportDir
    this.discoveryOnly = options.discoveryOnly
  }

  onBegin(_config: FullConfig, suite: Suite) {
    this.tests.clear()
    this.errors = 0
    for (const test of suite.allTests()) this.tests.set(test.id, { test, attempts: [] })
  }

  onTestEnd(test: TestCase, result: TestResult) {
    const entry = this.tests.get(test.id)
    if (!entry || this.discoveryOnly) return
    entry.test = test
    entry.attempts.push({
      status: safeStatus(result.status), expected_status: safeStatus(test.expectedStatus),
      retry: safeNumber(result.retry), duration_ms: safeNumber(result.duration),
    })
  }

  onError() { this.errors += 1 }

  onEnd(result: FullResult) {
    const counts = { ...statusCounts(), NOT_RUN: 0, executed: 0, expected_skipped: 0, unexpected_skipped: 0 }
    const outcomes = { expected: 0, unexpected: 0, flaky: 0, skipped: 0, NOT_RUN: 0 }
    const attempts = { ...statusCounts(), total: 0, executed: 0 }
    const cases = [...this.tests.values()].map(({ test, attempts: results }, index) => {
      const last = results.at(-1)
      const status = last?.status ?? 'NOT_RUN'
      const executed = results.some(attempt => attempt.status !== 'skipped')
      let outcome: Outcome = 'NOT_RUN'
      if (last) {
        const reported = test.outcome()
        outcome = ['expected', 'unexpected', 'flaky', 'skipped'].includes(reported) ? reported : 'unexpected'
      }
      counts[status] += 1
      counts.executed += Number(executed)
      outcomes[outcome] += 1
      if (last?.status === 'skipped') counts[last.expected_status === 'skipped' ? 'expected_skipped' : 'unexpected_skipped'] += 1
      for (const attempt of results) {
        attempts[attempt.status] += 1
        attempts.total += 1
        attempts.executed += Number(attempt.status !== 'skipped')
      }
      return { case_number: index + 1, status, outcome, executed, attempts: results }
    })
    const stage = this.discoveryOnly ? 'discovery' : 'browser'
    const runStatus = ['passed', 'failed', 'timedout', 'interrupted'].includes(result.status) ? result.status : 'failed'
    const status = this.discoveryOnly && runStatus === 'passed' ? 'listed' : runStatus
    const browserStatus = this.discoveryOnly || counts.executed === 0 ? 'NOT_RUN' : runStatus
    const payload = {
      schema_version: 2, stage, status, browser_status: browserStatus, evidence_available: true,
      discovered: this.tests.size, counts, outcomes, attempts, reporter_errors: this.errors, cases,
    }
    mkdirSync(this.reportDir, { recursive: true })
    writeFileSync(join(this.reportDir, 'summary.json'), `${JSON.stringify(payload, null, 2)}\n`, 'utf8')
    writeFileSync(join(this.reportDir, 'summary.md'), [
      '# EdgeVision browser validation', '',
      `- Stage: ${stage}`, `- Status: ${status}`, `- Browser status: ${browserStatus}`,
      `- Discovered: ${this.tests.size}`, `- Executed cases: ${counts.executed}`,
      ...Object.entries(counts).filter(([key]) => key !== 'executed').map(([key, value]) => `- ${key}: ${value}`),
      `- Attempts: ${attempts.total} (${attempts.executed} non-skipped)`,
      `- Flaky cases: ${outcomes.flaky}`, `- Unexpected outcomes: ${outcomes.unexpected}`,
      `- Reporter errors: ${this.errors}`,
      '- Counts describe observed test results, not proof of browser launch or acceptance.',
      '- Titles, paths, errors, credentials, cookies, traces, screenshots, service logs and database files are excluded.', '',
      ...cases.map(entry => `- Case ${entry.case_number}: ${entry.status}; outcome=${entry.outcome}; executed=${entry.executed}; attempts=${entry.attempts.length}`), '',
    ].join('\n'), 'utf8')
    console.log(`browser_e2e ${stage}=${status} browser=${browserStatus} discovered=${this.tests.size} executed=${counts.executed} passed=${counts.passed} failed=${counts.failed} timedOut=${counts.timedOut} interrupted=${counts.interrupted} skipped=${counts.skipped} NOT_RUN=${counts.NOT_RUN} attempts=${attempts.total} flaky=${outcomes.flaky} unexpected=${outcomes.unexpected}`)
  }

  printsToStdio() { return true }
}
