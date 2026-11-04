"""桌面窗口外壳：把本地服务渲染进原生窗口（pywebview + Edge WebView2）。

冻结运行的默认 UI 形态。窗口创建在主线程，uvicorn 在后台线程。

交互约定：
- 点窗口关闭按钮 → **收进系统托盘**，服务继续后台运行（适合长时间执行任务）
- 托盘图标：左键/「打开主界面」恢复窗口；「设置…」直接跳到设置页；
  「快捷设置」子菜单可勾选开机自启、启动最小化、关窗收进托盘；「退出」才真正结束进程
- 托盘不可用（或 ``VIDEO_STRM_TRAY=0``）时，关闭窗口即退出

不依赖浏览器：页面直接在 WebView2 中加载，窗口状态（主题、localStorage）
持久化在数据目录的 ``webview`` 子目录下。
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path

WINDOW_TITLE = "video-strm"
WINDOW_SIZE = (1360, 900)
WINDOW_MIN_SIZE = (1080, 700)
TRAY_HINT = "程序已收进托盘，服务继续在后台运行。右键托盘图标可打开或退出。"

logger = logging.getLogger("navly")


def build_icon_image(size: int = 256):
    """生成应用图标（圆角方块 + 播放三角），供 exe 图标、任务栏与托盘复用。"""
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    pad = round(size * 0.06)
    draw.rounded_rectangle(
        (pad, pad, size - pad, size - pad),
        radius=round(size * 0.18),
        fill=(12, 68, 124, 255),
    )
    draw.polygon(
        [
            (size * 0.40, size * 0.31),
            (size * 0.40, size * 0.69),
            (size * 0.72, size * 0.50),
        ],
        fill=(230, 241, 251, 255),
    )
    return image


def export_icon(path: Path) -> Path:
    """导出多尺寸 .ico（打包时作为 exe 与安装包图标）。"""
    image = build_icon_image(256)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(
        path,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    return path


def run_window(
    url: str,
    storage_dir: Path,
    title: str = WINDOW_TITLE,
    enable_tray: bool = True,
    start_minimized: bool = False,
    activate_event: str | None = None,
) -> None:
    """打开主窗口并阻塞到窗口销毁。

    Args:
        url: 本地服务地址（http://127.0.0.1:<port>）。
        storage_dir: WebView2 用户数据目录，用于持久化 localStorage 等状态。
        title: 窗口标题。
        enable_tray: 是否启用托盘；关闭时点关闭按钮即退出。
        start_minimized: 启动时只留托盘、不显示窗口（依赖托盘）。
        activate_event: 命名事件名；再次双击 exe 时用它唤起已有窗口。
    """
    import webview

    storage_dir.mkdir(parents=True, exist_ok=True)
    window = webview.create_window(
        title,
        url,
        width=WINDOW_SIZE[0],
        height=WINDOW_SIZE[1],
        min_size=WINDOW_MIN_SIZE,
        # 仅在有托盘时隐藏启动，避免没有入口可以唤出窗口
        hidden=bool(enable_tray and start_minimized),
    )

    def pick_directory(start_dir: str = "") -> str:
        """唤起系统文件夹选择框（Windows 下为 IFileDialog，即 Win11 现代选择器）。

        供前端「输出根目录 → 选择」按钮通过 ``window.pywebview.api.pick_directory()`` 调用，
        返回所选绝对路径；取消时返回空字符串。
        """
        directory = start_dir or str(Path.home())
        try:
            result = window.create_file_dialog(webview.FOLDER_DIALOG, directory=directory)
        except Exception:  # noqa: BLE001  # 对话框异常不应影响窗口主流程
            return ""
        if not result:
            return ""
        if isinstance(result, (list, tuple)):
            return str(result[0]) if result else ""
        return str(result)

    # 必须在 start() 之前注册，前端才能通过 window.pywebview.api 调用
    window.expose(pick_directory)

    state: dict[str, object] = {
        "quitting": False,
        "hint_shown": False,
        "tray_hint_shown": False,
        "tray": None,
    }

    def quit_app() -> None:
        """真正退出：先停托盘，再销毁窗口（销毁后 start() 返回，调用方停服务）。"""
        if state["quitting"]:
            return
        state["quitting"] = True
        tray = state["tray"]
        if tray is not None:
            try:
                tray.stop()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
        try:
            window.destroy()
        except Exception:  # noqa: BLE001
            pass

    def show_window() -> None:
        try:
            window.show()
            window.restore()
            window.on_top = False
        except Exception:  # noqa: BLE001
            pass

    def open_data_dir() -> None:
        try:
            os.startfile(str(storage_dir.parent))  # noqa: S606  # 本地打开资源管理器
        except Exception:  # noqa: BLE001
            pass

    def open_settings() -> None:
        """托盘「设置…」：恢复窗口并直接跳到设置页（不整页刷新，保留当前界面状态）。"""
        show_window()
        # 页面可能尚未加载完成，短暂重试；仍失败则退化为整页打开 /settings
        for _ in range(4):
            try:
                if window.evaluate_js(
                    "window.__videoStrmNavigate "
                    "? (window.__videoStrmNavigate('/settings'), true) : false"
                ):
                    return
            except Exception as exc:  # noqa: BLE001
                logger.warning("托盘打开设置页失败: %s", exc)
                break
            time.sleep(0.3)
        try:
            window.load_url(url.rstrip("/") + "/settings")
        except Exception as exc:  # noqa: BLE001
            logger.warning("托盘打开设置页（整页）失败: %s", exc)

    def pref_enabled(key: str) -> bool:
        from app.core import desktop_prefs

        return bool(desktop_prefs.load_prefs().get(key))

    def close_to_tray_enabled() -> bool:
        """关窗行为以 desktop.json 为准（默认收进托盘）。"""
        from app.core import desktop_prefs

        return bool(desktop_prefs.load_prefs().get("close_to_tray", True))

    def toggle_pref(key: str) -> None:
        """托盘快捷开关：写 desktop.json，立即生效。"""
        from app.core import desktop_prefs

        try:
            prefs = desktop_prefs.save_prefs(**{key: not pref_enabled(key)})
        except OSError as exc:
            logger.warning("托盘切换 %s 失败: %s", key, exc)
            return
        logger.info("托盘快捷开关 %s -> %s", key, prefs[key])

    def toggle_autostart() -> None:
        from app.core import desktop_prefs

        if not desktop_prefs.autostart_supported():
            return
        try:
            desktop_prefs.set_autostart(not desktop_prefs.is_autostart_enabled())
        except (OSError, RuntimeError) as exc:
            logger.warning("托盘切换开机自启失败: %s", exc)

    def autostart_checked() -> bool:
        from app.core import desktop_prefs

        return desktop_prefs.is_autostart_enabled()

    def autostart_supported() -> bool:
        from app.core import desktop_prefs

        return desktop_prefs.autostart_supported()

    def hide_to_tray() -> None:
        """在关闭事件返回后再隐藏：事件内直接 hide 会被 WinForms 的取消关闭流程重新显示。"""
        for delay in (0.05, 0.35):
            time.sleep(delay)
            try:
                window.hide()
            except Exception:  # noqa: BLE001
                pass
        if not state["hint_shown"]:
            state["hint_shown"] = True
            try:
                state["tray"].notify(TRAY_HINT, title)  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass

    def on_closing() -> bool:
        """关闭按钮：按偏好收进托盘或直接退出。

        每次关窗都现读 desktop.json，让设置页/托盘开关改完立即生效，不必重启应用。
        """
        if state["quitting"] or state["tray"] is None:
            return True
        if not close_to_tray_enabled():
            return True
        threading.Thread(target=hide_to_tray, name="tray-hide", daemon=True).start()
        return False

    window.events.closing += on_closing

    def watch_activation() -> None:
        """等待「再次双击 exe」的命名事件，收到后把已有窗口唤到前台。"""
        if not activate_event or sys.platform != "win32":
            return
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateEventW(None, False, False, activate_event)
        if not handle:
            return
        try:
            while not state["quitting"]:
                if kernel32.WaitForSingleObject(handle, 500) == 0:
                    show_window()
                    try:
                        # 先置顶再取消，确保窗口从后台跳到最前
                        window.on_top = True
                        window.on_top = False
                    except Exception:  # noqa: BLE001
                        pass
        finally:
            kernel32.CloseHandle(handle)

    def check_tray(icon) -> None:
        """校验图标是否真的注册进系统托盘，并在 Win11 下尽量固定到任务栏。"""
        from app.core.paths import is_frozen
        from app.core.tray_win import notify_icon_rect, promote_tray_icon

        time.sleep(0.8)
        rect = None
        try:
            rect = notify_icon_rect(getattr(icon, "_hwnd", 0) or 0)
            logger.info("托盘图标注册状态: %s", rect or "未注册")
        except Exception as exc:  # noqa: BLE001
            logger.warning("查询托盘图标失败: %s", exc)

        # 图标落在屏幕外 = 被 Win11 折叠进「^」，首次给一次气泡提示
        if rect and not state["tray_hint_shown"]:
            try:
                import ctypes

                if rect[1] >= ctypes.windll.user32.GetSystemMetrics(1):
                    state["tray_hint_shown"] = True
                    icon.notify(
                        "图标在任务栏「^」折叠区：可在任务栏设置中打开，或拖到任务栏固定",
                        title,
                    )
            except Exception:  # noqa: BLE001
                pass

        if not is_frozen():
            return
        try:
            logger.info("托盘图标固定到任务栏: %s", promote_tray_icon())
        except Exception as exc:  # noqa: BLE001
            logger.warning("固定托盘图标失败: %s", exc)

    tray_icon = None
    if enable_tray:
        try:
            import pystray

            tray_icon = pystray.Icon(
                "video-strm",
                build_icon_image(64),
                title,
                pystray.Menu(
                    pystray.MenuItem("打开主界面", lambda *_: show_window(), default=True),
                    pystray.MenuItem("设置…", lambda *_: open_settings()),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem(
                        "快捷设置",
                        pystray.Menu(
                            pystray.MenuItem(
                                "开机自动启动",
                                lambda *_: toggle_autostart(),
                                checked=lambda _item: autostart_checked(),
                                enabled=lambda _item: autostart_supported(),
                            ),
                            pystray.MenuItem(
                                "启动时最小化到托盘",
                                lambda *_: toggle_pref("start_minimized"),
                                checked=lambda _item: pref_enabled("start_minimized"),
                            ),
                            pystray.MenuItem(
                                "关闭窗口时最小化到托盘",
                                lambda *_: toggle_pref("close_to_tray"),
                                checked=lambda _item: pref_enabled("close_to_tray"),
                            ),
                        ),
                    ),
                    pystray.MenuItem("打开数据目录", lambda *_: open_data_dir()),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem("退出", lambda *_: quit_app()),
                ),
            )
            state["tray"] = tray_icon
            logger.info("托盘图标已创建（pystray）")
        except Exception as exc:  # noqa: BLE001  # 无托盘环境时退化为「关闭即退出」
            tray_icon = None
            logger.warning("托盘初始化失败，退化为关窗即退出: %s", exc, exc_info=True)

    def start_tray() -> None:
        if tray_icon is None:
            return

        def setup(icon) -> None:
            # pystray：一旦传入自定义 setup，就不会自动设置 visible，必须显式打开
            icon.visible = True
            if start_minimized:
                try:
                    icon.notify("已启动并最小化到托盘，左键图标打开主界面", title)
                except Exception:  # noqa: BLE001
                    pass
            threading.Thread(target=check_tray, args=(icon,), name="tray-check", daemon=True).start()

        try:
            tray_icon.run(setup=setup)
        except Exception as exc:  # noqa: BLE001
            # 托盘启动失败：解禁关闭行为并显示窗口，避免隐藏后无法退出
            state["tray"] = None
            logger.warning("托盘启动失败，退化为关窗即退出: %s", exc, exc_info=True)
            show_window()

    if activate_event:
        threading.Thread(target=watch_activation, name="activate-watch", daemon=True).start()

    if tray_icon is not None:
        webview.start(
            lambda: threading.Thread(target=start_tray, daemon=True).start(),
            private_mode=False,
            storage_path=str(storage_dir),
        )
    else:
        # private_mode=False + storage_path：保留主题等本地存储，不写注册表
        webview.start(private_mode=False, storage_path=str(storage_dir))
