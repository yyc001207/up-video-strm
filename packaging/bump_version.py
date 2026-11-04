"""版本号统一更新脚本。

唯一版本源：``backend/app/version.py`` 的 ``__version__``；
本脚本同时同步 ``frontend/package.json``、``frontend/package-lock.json`` 与
``packaging/version_info.txt``，避免多处不一致。

用法（仓库根目录）：
    python packaging/bump_version.py patch     # 1.1.0 -> 1.1.1
    python packaging/bump_version.py minor     # 1.1.0 -> 1.2.0
    python packaging/bump_version.py major     # 1.1.0 -> 2.0.0
    python packaging/bump_version.py 1.3.0     # 指定版本
    python packaging/bump_version.py --show    # 只打印当前版本
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_PY = ROOT / "backend" / "app" / "version.py"
PACKAGE_JSON = ROOT / "frontend" / "package.json"
PACKAGE_LOCK = ROOT / "frontend" / "package-lock.json"
VERSION_INFO = ROOT / "packaging" / "version_info.txt"

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def read_version() -> str:
    match = re.search(r'__version__\s*=\s*"([^"]+)"', VERSION_PY.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit(f"未能从 {VERSION_PY} 读取 __version__")
    return match.group(1)


def next_version(current: str, part: str) -> str:
    if SEMVER.match(part):
        return part
    if part not in ("major", "minor", "patch"):
        raise SystemExit("参数需为 major / minor / patch 或 x.y.z")
    major, minor, patch = (int(x) for x in current.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def write_version(version: str) -> None:
    major, minor, patch = (int(x) for x in version.split("."))

    text = VERSION_PY.read_text(encoding="utf-8")
    VERSION_PY.write_text(
        re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{version}"', text),
        encoding="utf-8",
    )

    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    package["version"] = version
    PACKAGE_JSON.write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # lockfile 的根版本也同步，避免 npm ci 与 package.json 版本长期漂移
    if PACKAGE_LOCK.exists():
        lock = PACKAGE_LOCK.read_text(encoding="utf-8")
        lock = re.sub(
            r'("version": ")[^"]+(")', rf"\g<1>{version}\g<2>", lock, count=2
        )
        PACKAGE_LOCK.write_text(lock, encoding="utf-8")

    info = VERSION_INFO.read_text(encoding="utf-8")
    info = re.sub(r"filevers=\(\d+, \d+, \d+, \d+\)", f"filevers=({major}, {minor}, {patch}, 0)", info)
    info = re.sub(r"prodvers=\(\d+, \d+, \d+, \d+\)", f"prodvers=({major}, {minor}, {patch}, 0)", info)
    info = re.sub(
        r'StringStruct\("FileVersion", "[^"]*"\)',
        f'StringStruct("FileVersion", "{version}")',
        info,
    )
    info = re.sub(
        r'StringStruct\("ProductVersion", "[^"]*"\)',
        f'StringStruct("ProductVersion", "{version}")',
        info,
    )
    VERSION_INFO.write_text(info, encoding="utf-8")


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return
    if args[0] in ("--show", "show"):
        print(read_version())
        return

    current = read_version()
    target = next_version(current, args[0])
    write_version(target)
    print(f"版本已更新: {current} -> {target}")
    print(f"  {VERSION_PY.relative_to(ROOT)}")
    print(f"  {PACKAGE_JSON.relative_to(ROOT)}")
    print(f"  {VERSION_INFO.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
