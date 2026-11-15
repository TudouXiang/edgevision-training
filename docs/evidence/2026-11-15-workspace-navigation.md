# Workspace navigation design and verification (2026-11-15)

Scope: presentation-only navigation improvement, based on main d109572. No API, schema, storage, training, role or capability-contract changes. Owner delegated product decisions and asked for a complete usable graduation project; no new dependencies or frameworks.

Chosen approach: reuse the current Vue components, separate workspace/system/account/admin areas, add explicit project entry and workflow controls, keep mounted panels for draft and polling continuity. Rejected a full router/component rewrite because it would unnecessarily change request lifecycle and accepted task restoration. Rejected only adding anchors because it leaves the crowded all-in-one presentation.

Returning to the project list only hides the active project; reopening the same project retains component instances. Selecting a different project retains the existing revision/abort cleanup and project-key remount boundaries. Existing stage URLs select their corresponding workflow when a project is chosen. The new buttons are local presentation controls, not new shareable routes: reload returns to the current URL's stage after selecting a project, and does not promise persistence of unsaved drafts.

The project picker remains available for existing workflows and selecting loaded projects. All existing pagination remains in place. No user database, old checkout or running deployment was changed. Worktree and dependency cache are on D:.

Plan: add failing navigation tests; implement explicit entry and areas; preserve drafts; adapt browser regression paths; run frontend suite/typecheck/build and disposable backend/browser harness; independent review before integration.

Review identified hidden-selector browser regressions and draft loss on returning to the list. Both were addressed: browser scenarios navigate explicitly, and list/detail presentation is separate from selected project identity.

Verification will be recorded below. Synthetic browser fixtures are not real model/GPU evidence.

## Final verification

- `npm test`: 11 files, 159 tests passed; exit 0. Two new navigation tests were first observed failing before implementation, then passed. Existing 157 tests remain passing.
- `npm run build`: Vue/TypeScript and Vite production build passed, exit 0.
- `npm run typecheck:e2e`: passed, exit 0.
- Disposable Windows `scripts/e2e.py`: 6 discovered, 5 executed/passed, 1 expected ML skip, 0 failed/timed out/flaky/unexpected; cleanup passed; harness exit 0. Safe receipt: `2026-11-15-workspace-navigation-browser.json`.
- Intermediate browser runs caught two outdated navigation sequences in T020/T030; corrected and rerun on the stable tree. First attempt used an incorrect local browser-cache directory, corrected without new installation.
- Independent source review rechecked the fixes and found no additional blocking issue.
- `git diff --check`: passed.

Not executed: optional ML training/export/inference/package browser scenarios, GPU/CUDA verification, visual screenshot review (connected Edge inspection timed out). The test adaptations for those optional cases type-check but their business behavior is not claimed verified by this change. Existing production deployment remains untouched; publishing a branch does not deploy it.
