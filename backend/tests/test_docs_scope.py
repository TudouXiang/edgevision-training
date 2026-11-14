"""Documentation/link regressions only; passing these is not business acceptance."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def test_entry_document_links_resolve_locally():
    for name in ('README.md', 'docs/acceptance.md'):
        path = ROOT / name
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text()):
            if '://' in target or target.startswith('#'):
                continue
            assert (path.parent / target.split('#', 1)[0]).is_file(), (name, target)


def test_current_acceptance_matrix_keeps_all_sixteen_conditions_once():
    current = (ROOT / 'docs/acceptance.md').read_text().split('## 旧版 A0–A9')[0]
    assert re.findall(r'^\|(A\d{2})\|', current, re.M) == [f'A{number:02}' for number in range(1, 17)]
    assert '当前轮次到此停止' not in current
    assert 'T060 E' in current and 'E 限定 accepted' in current and 'T070 已进入管理员任务切片' in current and '整体仍未验收' in current


def test_readme_does_not_restore_obsolete_training_or_report_claims():
    text = (ROOT / 'README.md').read_text()
    assert '训练、模型和部署仍明确未实现' not in text
    assert '浏览器报告只包含用例名' not in text
    assert 'T050-ci-acceptance-2026-11-04.md' in text
    assert 'schema v2' in text and 'E 限定 accepted' in text


def test_legacy_acceptance_wording_remains_explicitly_historical():
    legacy = (ROOT / 'docs/acceptance.md').read_text().split('## 旧版 A0–A9')[1]
    assert '仅指早期骨架记录' in legacy
    assert '不能覆盖上方当前阶段边界' in legacy


def test_export_acceptance_keeps_incremental_native_evidence_separate():
    text = (ROOT / 'docs/evidence/T060-export-acceptance-2026-11-05.md').read_text()
    assert '76af48f5eb86568f778efe5555f8e76074f3b978' in text
    assert '7e322689831216f53fd3c26eea009c580c8c35f3' in text
    assert '新提交没有重跑原生 ML' in text
    assert '旧训练/导出 probe 记录不可复用' in text
    assert 'T060 整体尚未 accepted' in text


def test_current_image_and_package_acceptance_remain_scoped_and_version_bound():
    readme = (ROOT / 'README.md').read_text()
    assert '单图工程限定 accepted' in readme and 'bd8d554' in readme
    assert '独立源码包工程限定 accepted' in readme and '685f2ef' in readme
    assert '每个实际环境仍须当前源码绑定的 probe' in readme
    assert 'ZIP 不含 Python/wheels' in readme
    assert 'T070、正式实验与全项目交付尚未验收' in readme
    current = (ROOT / 'docs/status.md').read_text().split('以下为历史检查点')[0]
    assert 'T060 P 限定工程 accepted' in current
    assert 'f3822aa07269b52407df203368b3ff7039802588' in current
    assert 'T070' in current and '全项目交付未验收' in current
    evidence = (ROOT / 'docs/evidence/T060-package-acceptance-2026-11-14.md').read_text()
    assert '43632501786' in evidence and 'package_browser' in evidence
    assert 'standalone_execution=not_run_for_this_artifact' in evidence
    assert '不含 Python 解释器或 wheels' in evidence


def test_current_api_and_export_text_does_not_restore_pre_inference_claims():
    readme = (ROOT / 'README.md').read_text()
    api = (ROOT / 'docs/api.md').read_text()
    contracts = (ROOT / 'docs/contracts.md').read_text()
    assert '仍是静态审查方案，实际隔离/ML 未执行' not in readme
    assert 'I 十阶段已于' in readme and 'P 或全项目通过' in readme
    assert '目前 501，无图片解析' not in api
    assert '训练、模型和部署仍不可用' not in api
    assert '二者继续 501' not in contracts
    assert 'I源码已实现' in api and '已限定验收' in api
    adr = (ROOT / 'docs/adr/0014-t060-image-inference.md').read_text()
    assert '旧“尚未接通”只描述设计阶段' in adr and 'P 可进入独立设计实施，尚未验收' in adr
