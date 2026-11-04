"""生成 packaging/app.ico（exe 与安装包图标）。

用法（仓库根目录）：
    backend\\.venv\\Scripts\\python.exe packaging\\make_icon.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
sys.path.insert(0, str(PROJECT / "backend"))

from app.desktop import export_icon  # noqa: E402

if __name__ == "__main__":
    target = export_icon(ROOT / "app.ico")
    print(f"已生成 {target} ({target.stat().st_size} bytes)")
