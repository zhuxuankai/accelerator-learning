import importlib.util
from pathlib import Path


def _module():
    path = Path(__file__).resolve().parents[1] / "extensions" / "translation" / "translation.py"
    spec = importlib.util.spec_from_file_location("translation_extension", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_translation_formula_audit_remains_strict():
    module = _module()
    assert module._math_segment_issues(r"\frac{a}{b}", "块公式") == []
    assert module._math_segment_issues(r"\text{中文}", "块公式")
    assert module._math_segment_issues(r"\tag{1}", "块公式")
