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
    assert 'T060 E' in current and 'E 未 accepted' in current and 'T070 前置仍为 T060 accepted' in current


def test_readme_does_not_restore_obsolete_training_or_report_claims():
    text = (ROOT / 'README.md').read_text()
    assert '训练、模型和部署仍明确未实现' not in text
    assert '浏览器报告只包含用例名' not in text
    assert 'T050-ci-acceptance-2026-11-04.md' in text
    assert 'schema v2' in text and 'E 未 accepted' in text


def test_legacy_acceptance_wording_remains_explicitly_historical():
    legacy = (ROOT / 'docs/acceptance.md').read_text().split('## 旧版 A0–A9')[1]
    assert '仅指早期骨架记录' in legacy
    assert '不能覆盖上方当前阶段边界' in legacy
