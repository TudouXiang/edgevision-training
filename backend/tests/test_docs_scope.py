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
    assert 'T060 E' in current and 'E 限定 accepted' in current and 'T070 前置仍为 T060 accepted' in current


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


def test_current_image_source_status_does_not_claim_native_acceptance():
    readme = (ROOT / 'README.md').read_text()
    assert '真实图片推理与独立部署包尚未实现' not in readme
    assert 'I 未验收' in readme and '真实图片模型执行与浏览器验证仍 **NOT_RUN**' in readme
    assert 'P：独立部署包尚未实现' in readme
    current = (ROOT / 'docs/status.md').read_text().split('以下保留各阶段原始状态')[0]
    assert 'I 源码审查通过、原生待验收' in current and '真实I ML/ORT/probe/HTTP/浏览器全部NOT_RUN' in current
    assert 'P仍501且blocked' in current


def test_current_api_and_export_text_does_not_restore_pre_inference_claims():
    readme = (ROOT / 'README.md').read_text()
    api = (ROOT / 'docs/api.md').read_text()
    contracts = (ROOT / 'docs/contracts.md').read_text()
    assert '仍是静态审查方案，实际隔离/ML 未执行' not in readme
    assert '新 I 十阶段入口仍未执行' in readme
    assert '目前 501，无图片解析' not in api
    assert '训练、模型和部署仍不可用' not in api
    assert '二者继续 501' not in contracts
    assert 'I源码已实现' in api and '真实模型验收未执行' in api
    adr = (ROOT / 'docs/adr/0014-t060-image-inference.md').read_text()
    assert '旧“尚未接通”只描述设计阶段' in adr and 'I业务未accepted，P仍blocked' in adr
