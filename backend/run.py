"""up-video-strm 启动入口：源码运行 ``python run.py``，打包后由 PyInstaller 直接调用。

两种运行态：

- **源码运行**：切换到 backend 目录，控制台里以 import string 启动 uvicorn，
  ``DEBUG=true`` 时保留热重载，行为与改造前一致（开发时 server 模式配合浏览器调试）。
- **冻结运行（打包 exe）**：不再派生子进程（冻结后 ``sys.executable`` 就是 exe 本身），
  改为后台线程跑 uvicorn + 主线程开原生窗口（pywebview/WebView2）；
  点关闭按钮收进系统托盘继续后台运行，托盘菜单「退出」才结束进程；
  无控制台窗口，日志写入数据目录 ``logs/app.log``。

调试用环境变量：``UP_VIDEO_STRM_UI=window`` 可在源码运行下也打开原生窗口。
"""

from __future__ import annotations

import ctypes
import os
import socket
import sys
import threading
import time
from pathlib import Path

from app.core.paths import APP_DIR_NAME

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
PORT_SCAN_LIMIT = 20
# 单实例互斥体/唤醒事件按应用目录名区分：测试版（up-video-strm-test）可与正式版并存运行
MUTEX_NAME = f"Local\\{APP_DIR_NAME}-single-instance"
ACTIVATE_EVENT = f"Local\\{APP_DIR_NAME}-activate"
ERROR_ALREADY_EXISTS = 183
EVENT_MODIFY_STATE = 0x0002
LOG_MAX_BYTES = 5 * 1024 * 1024

_mutex_handle = None
_log_handle = None


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _debug_enabled() -> bool:
    return os.environ.get("DEBUG", "").lower() in ("true", "1")


def _ui_mode() -> str:
    """UI 形态：window（原生窗口，打包默认）或 server（控制台服务，源码默认）。"""
    mode = os.environ.get("UP_VIDEO_STRM_UI", "").strip().lower()
    if mode in ("window", "server"):
        return mode
    return "window" if _is_frozen() else "server"


def _tray_enabled() -> bool:
    """关闭按钮是否收进托盘：默认开启；``UP_VIDEO_STRM_TRAY=0`` 时关闭（关窗即退出）。"""
    flag = os.environ.get("UP_VIDEO_STRM_TRAY")
    if flag is None:
        return True
    return flag.strip().lower() not in ("0", "false", "no", "off")


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _pick_port(host: str, preferred: int) -> int:
    """从首选端口向后探测可用端口（AGENTS.md 规则 4：端口占用自动切换）。"""
    for offset in range(PORT_SCAN_LIMIT):
        port = preferred + offset
        if port > 65535:
            break
        if _port_available(host, port):
            return port
    raise RuntimeError(f"端口 {preferred}-{preferred + PORT_SCAN_LIMIT - 1} 均被占用")


def _acquire_single_instance() -> bool:
    """Windows 命名互斥体：已有实例运行时返回 False。"""
    global _mutex_handle
    if sys.platform != "win32":
        return True
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return True
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _mutex_handle = handle
    return True


def _signal_activate() -> bool:
    """通知已运行的实例把主窗口显示出来（命名事件，无则返回 False）。"""
    if sys.platform != "win32":
        return False
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, ACTIVATE_EVENT)
    if not handle:
        return False
    try:
        kernel32.SetEvent(handle)
    finally:
        kernel32.CloseHandle(handle)
    return True


def _message_box(text: str, title: str = APP_DIR_NAME, error: bool = False) -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10 if error else 0x40)
    else:
        print(text, file=sys.stderr)


def _fatal(text: str) -> None:
    print(f"[fatal] {text}", file=sys.stderr, flush=True)
    _message_box(text, error=True)
    sys.exit(1)


def _redirect_stdio(log_dir: Path) -> Path:
    """无控制台运行：stdout/stderr 落到日志文件，超过 5MB 轮转一次。"""
    global _log_handle
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"
    try:
        if log_path.exists() and log_path.stat().st_size > LOG_MAX_BYTES:
            backup = log_dir / "app.log.1"
            if backup.exists():
                backup.unlink()
            log_path.replace(backup)
    except OSError:
        pass
    handle = open(log_path, "a", encoding="utf-8", buffering=1)
    _log_handle = handle
    sys.stdout = handle
    sys.stderr = handle
    print(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} 启动 =====", flush=True)
    return log_path


def _run_console(host: str, port: int) -> None:
    import uvicorn

    if _debug_enabled():
        uvicorn.run("app.main:app", host=host, port=port, reload=True, access_log=False)
    else:
        from app.main import app

        uvicorn.run(app, host=host, port=port, access_log=False)


def _run_desktop(
    host: str, port: int, url: str, root: Path, log_path: Path, prefs: dict
) -> None:
    import uvicorn

    from app.desktop import run_window
    from app.main import app

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=False,
        # 退出时最多等 2 秒处理在途请求/WebSocket，避免关窗后还要拖好几秒
        timeout_graceful_shutdown=2,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="uvicorn", daemon=True)
    thread.start()

    deadline = time.time() + 40
    while time.time() < deadline and not server.started:
        if not thread.is_alive():
            _fatal(f"服务启动失败，详情见日志：\n{log_path}")
        time.sleep(0.1)
    if not server.started:
        _fatal(f"服务启动超时，详情见日志：\n{log_path}")

    try:
        run_window(
            url,
            root / "webview",
            enable_tray=_tray_enabled(),
            start_minimized=bool(prefs.get("start_minimized")),
            activate_event=ACTIVATE_EVENT,
        )
    except Exception as exc:  # noqa: BLE001  # 缺 WebView2 等环境问题需给出可读提示
        _fatal(
            f"窗口启动失败：{exc}\n\n"
            "请确认已安装 Microsoft Edge WebView2 运行时。\n"
            f"日志：{log_path}"
        )
    finally:
        server.should_exit = True
        thread.join(timeout=3)
        if thread.is_alive():
            # 仍有连接未断开时强制退出，保证关窗/托盘退出后进程立即结束
            server.force_exit = True
            thread.join(timeout=2)


def main() -> None:
    frozen = _is_frozen()
    log_path: Path | None = None

    if frozen:
        from app.core.paths import data_root

        root = data_root() or Path.cwd()
        root.mkdir(parents=True, exist_ok=True)
        # 统一工作目录：任务输出目录的相对路径、.env、执行日志都落在数据目录下
        os.chdir(root)
        log_path = _redirect_stdio(root / "logs")
        if not _acquire_single_instance():
            # 已有实例：先请它把窗口显示出来；若它正在退出（互斥体尚未释放），
            # 等最多 3 秒再抢一次，避免「刚关掉却提示已在运行」的误判。
            _signal_activate()
            for _ in range(8):
                time.sleep(0.25)
                if _acquire_single_instance():
                    break
            else:
                print(f"{APP_DIR_NAME} 已在运行，已请求其显示窗口", flush=True)
                return
        from app.core.desktop_prefs import load_prefs

        # 在注册托盘图标之前先写入「默认收进 ^」，避免升级后首次启动仍出现在外侧
        try:
            from app.core.tray_win import hide_tray_icon

            hide_tray_icon(retries=1, delay=0.0)
        except Exception:  # noqa: BLE001 - 托盘可见性失败不影响启动
            pass

        prefs: dict = load_prefs()
    else:
        root = Path(__file__).resolve().parent
        os.chdir(root)
        prefs = {}

    host = os.environ.get("UP_VIDEO_STRM_HOST", DEFAULT_HOST)
    try:
        preferred_port = int(os.environ.get("UP_VIDEO_STRM_PORT", DEFAULT_PORT))
    except ValueError:
        preferred_port = DEFAULT_PORT

    try:
        port = _pick_port(host, preferred_port)
    except RuntimeError as exc:
        _fatal(str(exc))

    url = f"http://{host}:{port}"
    print(f"正在启动 {APP_DIR_NAME} ...")
    if port != preferred_port:
        print(f"端口 {preferred_port} 已被占用，自动切换到 {port}")
    print(f"服务地址: {url}")
    print(f"数据目录: {root}")
    print("-" * 40, flush=True)

    mode = _ui_mode()
    try:
        if mode == "window":
            from app.core.desktop_prefs import refresh_autostart_path

            # 应用被移动/重装后修正注册表里的自启路径
            refresh_autostart_path()
            _run_desktop(
                host,
                port,
                url,
                root,
                log_path or (root / "logs" / "app.log"),
                prefs,
            )
        else:
            _run_console(host, port)
    except KeyboardInterrupt:
        print("\n服务已停止")
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001  # 启动期失败需给出可读提示而非堆栈
        _fatal(f"启动失败：{exc}")
    finally:
        print("服务已停止", flush=True)


if __name__ == "__main__":
    main()
