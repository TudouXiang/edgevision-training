# T060 independent browser evidence correction · static review passed

Date: 2026-11-04. Input baseline: `0455566`. This change does not advance E/I/P.
Project feature-delivery, experiment-evidence and change-review skills were read
manually; automatic skill triggering is not claimed.

## Defect and bounded correction

The old reporter counted every `onTestEnd` callback as `completed`, including a
skipped optional ML case and every retry. Five callbacks could therefore be
mistaken for five executed scenarios. Raw test titles also entered its report.

Schema v2 now reports anonymous discovery-order case numbers, final actual status,
Playwright outcome, unique executed cases, expected/unexpected skips, never-run
cases, and separate attempt totals. It removes title/path/error serialization
entirely. Discovery failure is not called listed, and an empty/all-skipped suite
has browser status NOT_RUN. Harness fallback uses UNKNOWN when launch may have
occurred, retains unknown counts as null, and fails closed if no terminal reporter
receipt exists even when the subprocess exits zero. Opted-in `--ml`/`--delivery`
requires positive execution with passed = executed = discovered; ordinary mode
permits the optional ML skip. Original nonzero process exits are preserved.
Cleanup retains actual prior
reporter evidence. Exact field semantics are in `docs/environment.md`.

Changed implementation/test files: `web/e2e/safe-reporter.ts`,
`web/e2e/safe-reporter.test.ts`, `scripts/e2e.py`,
`backend/tests/test_dev_scripts_unit.py`. No product API or model contract changes.

## Verification actually executed

Dependencies were reused read-only from the existing locked frontend environment;
links and generated Vite caches/build output were local to this worktree. No
package installation, browser installation/launch, ML import/run, Docker, remote
write or network probe was performed.

- `npm test --prefix web -- e2e/safe-reporter.test.ts`: exit 0, 9 mocked tests.
- `npm test --prefix web`: exit 0, 47 tests across 6 files.
- `npm run build --prefix web`: exit 0, TypeScript/Vite build.
- `npm run typecheck:e2e --prefix web`: exit 0.
- `python -m unittest discover -s backend/tests -p test_dev_scripts_unit.py -k BrowserCleanupTests -v`: exit 0, 8 tests.
- `EDGEVISION_E2E_REPORT_DIR=<temporary-directory> npm run test:e2e:list --prefix web`:
  exit 0; discovery only, no services/credentials/browser/ML started. Output below.
- `git diff --check`: exit 0.

```text
browser_e2e discovery=listed browser=NOT_RUN discovered=5 executed=0 passed=0 failed=0 timedOut=0 interrupted=0 skipped=0 NOT_RUN=5 attempts=0 flaky=0 unexpected=0
```

Mocked coverage: four passed plus one expected skip; discovery-only (including
erroneous callback); failed discovery; expected/unexpected skips and missing
callbacks; failed/timed-out/interrupted results; fail-then-pass retry/flaky;
fail-then-skip retry; expected failure/unexpected pass; empty suite. Injected secret
sentinels in titles, IDs, paths, errors, attachments and output are absent from all
three report surfaces. Python checks cover fallback, malformed/missing receipt,
process-versus-reporter outcomes, opted-in ML skip rejection, invalid count
receipts and cleanup retention.

## Not executed / limits

Real browser, ML, ONNX/ORT, HTTP business acceptance, Docker isolation, Windows,
hardware and full backend suite: NOT_RUN. Mocked reporter success is not browser
acceptance. Discovery only confirms collection/typechecking and reporting. Existing
historical receipts remain unchanged. Independent review is still required.

## Independent-review correction after initial checkpoint f436c22

Review found that aggregate validation alone accepted five null cases alongside
plausible totals. The follow-up now validates exact top-level, case and attempt
fields and recomputes final, executed, skip, attempt and outcome aggregates.
It rejects duplicate/out-of-order case ordinals, invalid retry indexes, boolean
or non-finite numeric metadata, missing/extra fields and contradictory outcomes.
Playwright 1.64's installed `computeTestCaseOutcome` was read to match its final
expected-status semantics, including interrupted attempts and fail-then-skip.
Opted-in ML additionally rejects flaky/unexpected outcomes and reporter errors.

The bounded reader rejects inputs over 1 MiB, invalid UTF-8 and excessive nesting
before any raw contents can be included in the fallback. Fixtures now carry the
full anonymous schema rather than placeholder cases.

Follow-up validation: `python -m unittest discover -s backend/tests -p
test_dev_scripts_unit.py -k BrowserCleanupTests -v` exited 0 with **12 tests**,
including 25 malformed/contradictory mutation subcases, five missing-field cases,
nine retry/failure/skip outcome scenarios, and strict-mode flaky-pass rejection.
`git diff --check` exited 0. No browser, ML or other business acceptance was run.

## 最终整合回归和复审（后于上述独立工作区记录）

整合源码 `bb6c1b1533e6fed5806dbb1b2e470f78ca83a98b` 同时包含独立批准 SHA 门禁，标准 `python scripts/dev.py check` 退出 0：6 项契约 unittest、21 项脚本 unittest；后端 **371 passed、9 skipped**；前端 **47 passed**；TypeScript/Vite 构建与契约漂移检查通过。9 个跳过项仍是原生 ML opt-in，未因这次执行变为已验证。

报告器收据校验的独立静态复审已接受：完整匿名字段、逐项重算、负向输入与严格 ML 模式边界未发现新的阻断。独立批准 SHA 门禁亦经静态复审，分支变化或空/错 SHA 在容器准备前拒绝，不直接向 shell 插入输入。

上述补充只更新本轮源码、轻量完整回归与静态审查范围；新报告器的真实浏览器、实际容器隔离和 ML 仍未执行。发布后仅允许普通 Linux/Windows CI，手动 ML job 保持默认关闭。


## 后续远端普通浏览器实测

公开提交 `b9cbc568774d8ddfdfb4a312009ebf39bebe4437` 的 [CI 41871285873](https://github.com/TudouXiang/edgevision-training/actions/runs/41871285873) 完成 success。
Linux job `126718733541` 报告 discovered=5、executed=4、passed=4、skipped=1、failed=0、NOT_RUN=0、attempts=5、flaky=0、unexpected=0。
这验证了普通浏览器路径和 schema v2 的实际报告，不将 skip 回调计为执行。ML job `126718736890` skipped，实际容器隔离和 ML 仍 NOT_RUN。
