# T060 online preparation correction

Date: 2026-11-05 UTC. Scope: source, negative tests, documentation and lightweight checks only. Real Docker/image/ML execution remains **NOT_RUN**; E is not accepted. No change to main or automatic ML triggers.

## Finding and source comparison

The prior `b9cbc568774d8ddfdfb4a312009ebf39bebe4437` to `30eaaff01e8590e2f5b7af8e8bc50ca6c0537cb9` difference affected only eight README/docs/synthetic-recovery test files. The acquisition, Docker, installer and execution implementation were unchanged. This review nevertheless found a pre-existing preparation gap: `install_ml.py` started `python -m pip check` after installing the 67 locked wheels, while image build networking was still available. The installer's outer `-I -S` flags do not propagate to that child, whose site initialization may execute wheel `.pth` or customize hooks. No such build was executed and no telemetry transmission was observed.

A harmless standard-library test creates a temporary venv with no pip, model or download. Its `.pth` only writes a local marker. An outer `-I -S` interpreter launching an inner `-I` child still produces the marker. This demonstrates the startup gap, not malicious ML behavior.

## Minimal correction and trust boundary

- Docker explicitly selects `--delivery --defer-check`. Existing directories, files and dangling links at the venv target are rejected before modification. Ordinary explicit installer mode retains its dependency check; it is not the reviewed isolated build route.
- The host prefix copy rejects `._pth` overrides before starting the copied Python. Installer inspection runs under `-I -S`, before venv creation, and rejects `.pth`, sitecustomize/usercustomize modules, bytecode, packages and native-extension names in fixed Linux 3.12 startup roots. This includes lib/lib64, stdlib, lib-dynload, site-packages and python312.zip. Escaping links and invalid/unreadable archives fail closed. Unimportable nested test fixtures are not treated as startup roots.
- The fixed official Python distribution and bundled ensurepip remain trusted inputs. Fresh-venv inspection happens before the sole `python -I -m pip install` child. It retains `--only-binary=:all:` and `--require-hashes`; no source builds, lifecycle hooks or install-time model probe are added. `-S` is deliberately not used for pip because Python 3.12 relies on site initialization for correct venv prefix handling.
- After the 67 wheels are installed, the same installer process checks the venv and base prefix again for `._pth` overrides, without starting another Python child. This closes a second issue found during independent review: an installed wheel could add an override that defeats `-I -S` on the next entry. A separate harmless stdlib marker regression demonstrates that behavior. Ordinary post-install `.pth` files are left for the isolated runtime. Only after the existing non-root/network-none kernel checks pass may `dependency_check` run `python -I -m pip check`. Its logs stay private, share the 450-second child budget and a failure prevents all five ML stages.
- The closed anonymous execution schema is now v2, with seven ordered stages. Old v1/six-stage receipts are rejected. This differs from the separate browser-receipt schema, which was already v2.
- Official ORT opt-out is still set before any Python/native initialization; it is defense in depth, never a substitute for network isolation or proof that an unexecuted wheel behaves safely.

## Evidence

Initial source checkpoint: `9c8454c01bbe68a9da26b2919c8f1ecffb804bb8` (based on remote `30eaaff`). Independent review rejected that checkpoint because it lacked the post-install `._pth` scan. The corrected source adds that scan and four more regression cases; the earlier checkpoint is historical and must not be executed as the reviewed candidate. The following command ran from `backend` with opt-ins cleared:

```sh
EDGEVISION_ML_POLICY_ROOT='' EDGEVISION_ONNX_POLICY_ROOT='' EDGEVISION_RUN_ISOLATED_ML=false .venv/bin/python -m pytest tests/test_isolated_ml_ci.py tests/test_delivery_install_plan.py tests/test_ml_privacy.py -q -p no:cacheprovider
```

Exit 0: **174 passed**, including 31 added cases. Coverage includes fresh/reused/dangling targets, isolated pip flags and hashes, no interpreter restart after wheels, bootstrap path/module/zip/native hooks, malformed archive/escaping link, unrelated fixture acceptance, boundary-before-dependency ordering, failure stopping every ML stage, shared deadline/private logs and v1 rejection. These are static/mock/stdlib tests, not proof of actual Docker or ML isolation.

Independent review accepted corrected source `36e70cdf64b2700e42b27c62d081745b742821a2` (tree `dcfe828746c9db3272ea8b7d8036ee234f3ed72c`) with an independent **174 passed**, exit 0, and `git diff --check` passing. This is source-only acceptance, not authorization or proof of real isolation. Final local aggregate checks completed on this corrected code: **429 backend passed, 9 native opt-in skipped, 47 frontend passed**, type/build and generated contracts passed, exit 0. `python3 scripts/dev.py check` used the same cleared opt-ins; the separate `backend/.venv/bin/python tests/http_restart_probe.py` also exited 0 with API restart, independent Worker and tree exit all passed. Only documentation changed afterward. Exact remote CI belongs to the publication receipt for the published SHA; earlier CI success is not carried forward to changed source.

## Remaining execution gate

No real Docker build, asset download, dependency installation, model import, training/export, ORT inference or ML browser validation was performed. The prior denial over unknown telemetry is not bypassed. A future attempt needs review and approval for the changed exact commit, plus a normal authorized workflow-dispatch route. Web login was verified, but does not itself authenticate the cloud GitHub CLI; the current workflow page does not show a Run workflow button. No change to main, permission grant, token extraction or alternate execution environment was used to work around this.
