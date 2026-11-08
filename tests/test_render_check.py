import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = os.environ.get("ACCKB_NODE") or shutil.which("node")
LOCAL_MODULES = ROOT / "node_modules"
if not all((LOCAL_MODULES / name).exists() for name in ("markdown-it", "markdown-it-texmath", "katex")):
    candidates = sorted(
        (Path.home() / ".vscode" / "extensions").glob("goessner.mdmath-*/node_modules"),
        reverse=True,
    )
    LOCAL_MODULES = candidates[0] if candidates else LOCAL_MODULES


@pytest.mark.skipif(
    not NODE
    or not all((LOCAL_MODULES / name).exists() for name in ("markdown-it", "markdown-it-texmath", "katex")),
    reason="Node Math deps unavailable",
)
def test_render_check_detects_good_and_legacy_delimiters(tmp_path):
    good = tmp_path / "good.md"
    good.write_text("公式 $x^2$\n\n$$y^2$$ (1)\n", encoding="utf-8")
    bad = tmp_path / "bad.md"
    bad.write_text("公式 \\(x^2\\)\n", encoding="utf-8")
    script = ROOT / "extensions" / "translation" / "render_check.cjs"
    env = dict(os.environ)
    env["NODE_PATH"] = str(LOCAL_MODULES)
    ok = subprocess.run([NODE, str(script), str(good)], capture_output=True, text=True, env=env)
    warning = subprocess.run(
        [NODE, str(script), str(bad)], capture_output=True, text=True, env=env
    )
    assert ok.returncode == 0
    assert warning.returncode == 1
    assert '"legacy_delimiters"' in warning.stdout
