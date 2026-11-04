import { mkdirSync, writeFileSync } from 'node:fs'
import { basename, join } from 'node:path'
import type { FullConfig, FullResult, Reporter, Suite, TestCase, TestResult } from '@playwright/test/reporter'

type SafeCase = {
  title: string
  status: string
  duration_ms: number
  location: { file: string; line: number; column: number }
  failure_location?: { file: string; line: number; column: number }
}

export default class SafeReporter implements Reporter {
  private readonly reportDir: string
  private readonly discoveryOnly: boolean
  private readonly cases: SafeCase[] = []
  private discovered = 0

  constructor(options: { reportDir: string; discoveryOnly: boolean }) {
    this.reportDir = options.reportDir
    this.discoveryOnly = options.discoveryOnly
  }

  onBegin(_config: FullConfig, suite: Suite) {
    this.discovered = suite.allTests().length
  }

  onTestEnd(test: TestCase, result: TestResult) {
    const safeStack = result.errors.map(error => error.stack ?? '').join('\n')
    const failure = safeStack.match(/[\\/]e2e[\\/]([^:\n]+\.e2e\.ts):(\d+):(\d+)/)
    const entry: SafeCase = {
      title: test.titlePath().slice(1).join(' > '),
      status: result.status,
      duration_ms: result.duration,
      location: { file: basename(test.location.file), line: test.location.line, column: test.location.column },
    }
    if (failure) entry.failure_location = { file: basename(failure[1]), line: Number(failure[2]), column: Number(failure[3]) }
    this.cases.push(entry)
  }

  onEnd(result: FullResult) {
    mkdirSync(this.reportDir, { recursive: true })
    const stage = this.discoveryOnly ? 'discovery' : 'browser'
    const status = this.discoveryOnly ? 'listed' : result.status
    const counts = this.cases.reduce<Record<string, number>>((summary, entry) => {
      summary[entry.status] = (summary[entry.status] ?? 0) + 1
      return summary
    }, {})
    const payload = {
      schema_version: 1, stage, status, browser_status: this.discoveryOnly ? 'NOT_RUN' : result.status,
      discovered: this.discovered, counts, cases: this.cases,
    }
    writeFileSync(join(this.reportDir, 'summary.json'), `${JSON.stringify(payload, null, 2)}\n`, 'utf8')
    const cases = this.cases.map(entry => {
      const location = entry.failure_location ?? entry.location
      return `- ${entry.status}: ${entry.title} (${entry.duration_ms} ms, ${location.file}:${location.line}:${location.column})`
    }).join('\n')
    writeFileSync(
      join(this.reportDir, 'summary.md'),
      `# T020 browser validation\n\n- Stage: \`${stage}\`\n- Status: \`${status}\`\n- Browser status: \`${this.discoveryOnly ? 'NOT_RUN' : result.status}\`\n- Discovered: ${this.discovered}\n- Credentials, cookies, traces, screenshots, service logs and database files are excluded.\n\n${cases || '- No browser cases completed.'}\n`,
      'utf8',
    )
    console.log(`browser_e2e ${stage}=${status} browser=${this.discoveryOnly ? 'NOT_RUN' : result.status} discovered=${this.discovered} completed=${this.cases.length}`)
  }

  printsToStdio() { return true }
}
