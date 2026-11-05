import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { FullConfig, FullResult, Suite, TestCase, TestResult } from '@playwright/test/reporter'
import SafeReporter from './safe-reporter'

const secret = 'PRIVATE-credential-cookie-path-title-stack'
const dirs: string[] = []
afterEach(() => { vi.restoreAllMocks(); for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true }) })
function testCase(id: number, expectedStatus: TestResult['status'] = 'passed', outcome = 'expected') {
  return { id: `${secret}-${id}`, expectedStatus, outcome: () => outcome, title: secret,
    titlePath: () => [secret], location: { file: secret, line: 1, column: 1 }, annotations: [{ type: secret, description: secret }] } as unknown as TestCase
}
function run(tests: TestCase[], discoveryOnly = false) {
  const dir = mkdtempSync(join(tmpdir(), 'safe-reporter-')); dirs.push(dir)
  const log = vi.spyOn(console, 'log').mockImplementation(() => {})
  const reporter = new SafeReporter({ reportDir: dir, discoveryOnly })
  reporter.onBegin({} as FullConfig, { allTests: () => tests } as Suite)
  return { reporter, finish(status: FullResult['status'] = 'passed') {
    reporter.onEnd({ status } as FullResult)
    const json = readFileSync(join(dir, 'summary.json'), 'utf8')
    const md = readFileSync(join(dir, 'summary.md'), 'utf8')
    const stdout = log.mock.calls.flat().join('\n')
    expect(json + md + stdout).not.toContain(secret)
    return { payload: JSON.parse(json), md, stdout }
  } }
}
function end(reporter: SafeReporter, test: TestCase, status: TestResult['status'], retry = 0) {
  reporter.onTestEnd(test, { status, retry, duration: 12, errors: [{ message: secret, stack: secret }],
    attachments: [{ name: secret, path: secret }], stdout: [secret], stderr: [secret] } as unknown as TestResult)
}

describe('anonymous browser evidence (mocked callbacks, no browser)', () => {
  it('separates four passed cases from the optional skipped ML case', () => {
    const tests = [...Array.from({ length: 4 }, (_, i) => testCase(i)), testCase(4, 'skipped', 'skipped')]
    const { reporter, finish } = run(tests)
    tests.forEach((test, i) => end(reporter, test, i === 4 ? 'skipped' : 'passed'))
    const { payload, stdout } = finish()
    expect(payload.schema_version).toBe(2)
    expect(payload.counts).toEqual({ passed: 4, failed: 0, timedOut: 0, interrupted: 0, skipped: 1, NOT_RUN: 0, executed: 4, expected_skipped: 1, unexpected_skipped: 0 })
    expect(payload.attempts).toEqual({ passed: 4, failed: 0, timedOut: 0, interrupted: 0, skipped: 1, total: 5, executed: 4 })
    expect(stdout).toContain('discovered=5 executed=4 passed=4')
    expect(stdout).not.toContain('completed=')
    expect(Object.keys(payload.cases[0])).toEqual(['case_number', 'status', 'outcome', 'executed', 'attempts'])
  })

  it('discovery lists all cases as NOT_RUN, never skipped or passed', () => {
    const tests = [testCase(0), testCase(1, 'skipped', 'skipped')]
    const { reporter, finish } = run(tests, true)
    end(reporter, tests[0]!, 'passed') // Even an unexpected callback cannot turn listing into execution.
    const { payload } = finish()
    expect(payload).toMatchObject({ stage: 'discovery', status: 'listed', browser_status: 'NOT_RUN', discovered: 2,
      counts: { NOT_RUN: 2, executed: 0, skipped: 0, passed: 0 }, attempts: { total: 0 } })
  })

  it('does not hide discovery failure behind listed', () => {
    const { reporter, finish } = run([], true)
    reporter.onError()
    expect(finish('failed').payload).toMatchObject({ status: 'failed', browser_status: 'NOT_RUN', reporter_errors: 1 })
  })

  it('distinguishes expected skip, unexpected skip and cases never reported', () => {
    const tests = [testCase(0, 'skipped', 'skipped'), testCase(1, 'passed', 'skipped'), testCase(2)]
    const { reporter, finish } = run(tests)
    end(reporter, tests[0]!, 'skipped'); end(reporter, tests[1]!, 'skipped')
    expect(finish().payload).toMatchObject({ browser_status: 'NOT_RUN', counts: { executed: 0, skipped: 2,
      expected_skipped: 1, unexpected_skipped: 1, NOT_RUN: 1 } })
  })

  it('counts failed, timed out and interrupted results without turning them into passes', () => {
    const tests = [0, 1, 2, 3].map(i => testCase(i, 'passed', 'unexpected'))
    const { reporter, finish } = run(tests)
    end(reporter, tests[0]!, 'failed'); end(reporter, tests[1]!, 'timedOut'); end(reporter, tests[2]!, 'interrupted')
    expect(finish('interrupted').payload).toMatchObject({ status: 'interrupted', browser_status: 'interrupted',
      counts: { passed: 0, failed: 1, timedOut: 1, interrupted: 1, NOT_RUN: 1, executed: 3 } })
  })

  it('keeps retry attempts separate from unique cases and retains flaky outcome', () => {
    const test = testCase(0, 'passed', 'flaky')
    const { reporter, finish } = run([test])
    end(reporter, test, 'failed'); end(reporter, test, 'passed', 1)
    expect(finish().payload).toMatchObject({ discovered: 1, counts: { executed: 1, passed: 1, failed: 0 },
      outcomes: { flaky: 1 }, attempts: { total: 2, executed: 2, failed: 1, passed: 1 } })
  })

  it('does not erase an executed failure when a retry is skipped', () => {
    const test = testCase(0, 'passed', 'unexpected')
    const { reporter, finish } = run([test])
    end(reporter, test, 'failed'); end(reporter, test, 'skipped', 1)
    expect(finish('failed').payload).toMatchObject({ counts: { executed: 1, skipped: 1, unexpected_skipped: 1 },
      attempts: { total: 2, failed: 1, skipped: 1, executed: 1 } })
  })

  it('separates expected failure and unexpected pass from actual terminal status', () => {
    const tests = [testCase(0, 'failed', 'expected'), testCase(1, 'failed', 'unexpected')]
    const { reporter, finish } = run(tests)
    end(reporter, tests[0]!, 'failed'); end(reporter, tests[1]!, 'passed')
    expect(finish('failed').payload).toMatchObject({ counts: { executed: 2, failed: 1, passed: 1 },
      outcomes: { expected: 1, unexpected: 1 } })
  })

  it('keeps an empty run NOT_RUN, even when Playwright exits successfully', () => {
    expect(run([]).finish().payload).toMatchObject({ browser_status: 'NOT_RUN', discovered: 0, counts: { executed: 0 } })
  })
})
