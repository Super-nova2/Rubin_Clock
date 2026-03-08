from __future__ import annotations

import ctypes
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import customtkinter as ctk
import pystray
from PIL import Image, ImageDraw

from .astro_core import SkyState, Site, classify_sky_state, compute_solar_altitude, compute_true_solar_time, next_transition
from .config_store import (
    AppConfig,
    create_site_id,
    ensure_unique_site_id,
    load_config,
    set_language,
    set_selected_site,
    upsert_site,
)


RESIZE_MARGIN = 10
MIN_WIDTH = 420
MIN_HEIGHT = 300

if sys.platform == "win32":
    HWND_BOTTOM = 1
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOACTIVATE = 0x0010
    SWP_NOOWNERZORDER = 0x0200
    SWP_ASYNCWINDOWPOS = 0x4000
    BOTTOM_FLAGS = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_NOOWNERZORDER | SWP_ASYNCWINDOWPOS

RESIZE_CURSOR = {
    "n": "size_ns",
    "s": "size_ns",
    "e": "size_we",
    "w": "size_we",
    "ne": "size_ne_sw",
    "sw": "size_ne_sw",
    "nw": "size_nw_se",
    "se": "size_nw_se",
}

LANGUAGE_LABELS = {
    "zh": "中文",
    "en": "English",
}

I18N = {
    "zh": {
        "app_title": "Rubin 太阳时钟",
        "tray_title": "Rubin 太阳时钟",
        "clock_title": "Rubin 台址真太阳时",
        "settings": "设置",
        "hide": "隐藏",
        "exit": "退出",
        "state_prefix": "状态",
        "observe_prefix": "观测判定",
        "observable": "适合观测",
        "not_observable": "不适合观测",
        "solar_altitude": "太阳高度角",
        "next_countdown": "下一节点倒计时",
        "next_state": "下一状态",
        "no_transition": "48 小时内无状态切换",
        "drag_hint": "拖动窗口上半部分可移动；边界可拖拽调节尺寸",
        "local_date": "当地日期",
        "show_window": "显示窗口",
        "hide_window": "隐藏窗口",
        "switch_site": "切换站点",
        "open_settings": "打开设置",
        "tray_exit": "退出",
        "language": "语言",
        "settings_title": "站点设置",
        "current_site": "当前站点",
        "set_current": "设为当前",
        "new_site": "新增站点",
        "site_name_placeholder": "站点名称",
        "lat_placeholder": "纬度 (例如 38.6068)",
        "lon_placeholder": "经度 (例如 93.8961)",
        "elev_placeholder": "海拔米数 (可选)",
        "save_site": "保存新站点",
        "builtin_hint": "提示: 内置 Rubin 与 WFST 站点会自动保留。",
        "err_site_name": "请输入站点名称",
        "err_parse": "经纬度/海拔格式错误",
        "err_range": "纬度需在 [-90, 90] 且经度需在 [-180, 180]",
        "saved_ok": "站点保存成功",
        "interface_language": "界面语言",
        "apply_language": "应用语言",
        "state_day": "白天",
        "state_civil": "民用晨昏",
        "state_nautical": "航海晨昏",
        "state_astronomical_twilight": "天文晨昏",
        "state_astronomical_night": "天文夜",
    },
    "en": {
        "app_title": "Rubin Solar Clock",
        "tray_title": "Rubin Solar Clock",
        "clock_title": "Rubin Local Apparent Solar Time",
        "settings": "Settings",
        "hide": "Hide",
        "exit": "Exit",
        "state_prefix": "State",
        "observe_prefix": "Observing",
        "observable": "Suitable",
        "not_observable": "Not Suitable",
        "solar_altitude": "Solar Altitude",
        "next_countdown": "Next Transition",
        "next_state": "Next State",
        "no_transition": "No transition within 48 hours",
        "drag_hint": "Drag upper area to move; drag borders to resize",
        "local_date": "Local Date",
        "show_window": "Show Window",
        "hide_window": "Hide Window",
        "switch_site": "Switch Site",
        "open_settings": "Open Settings",
        "tray_exit": "Exit",
        "language": "Language",
        "settings_title": "Site Settings",
        "current_site": "Current Site",
        "set_current": "Set Current",
        "new_site": "Add Site",
        "site_name_placeholder": "Site Name",
        "lat_placeholder": "Latitude (e.g. 38.6068)",
        "lon_placeholder": "Longitude (e.g. 93.8961)",
        "elev_placeholder": "Elevation in meters (optional)",
        "save_site": "Save Site",
        "builtin_hint": "Note: Built-in Rubin and WFST are always kept.",
        "err_site_name": "Please enter a site name",
        "err_parse": "Invalid latitude/longitude/elevation",
        "err_range": "Latitude must be [-90, 90], longitude [-180, 180]",
        "saved_ok": "Site saved",
        "interface_language": "Interface Language",
        "apply_language": "Apply Language",
        "state_day": "Daylight",
        "state_civil": "Civil Twilight",
        "state_nautical": "Nautical Twilight",
        "state_astronomical_twilight": "Astronomical Twilight",
        "state_astronomical_night": "Astronomical Night",
    },
}

STATE_TEXT_KEYS = {
    SkyState.DAY: "state_day",
    SkyState.CIVIL_TWILIGHT: "state_civil",
    SkyState.NAUTICAL_TWILIGHT: "state_nautical",
    SkyState.ASTRONOMICAL_TWILIGHT: "state_astronomical_twilight",
    SkyState.ASTRONOMICAL_NIGHT: "state_astronomical_night",
}

STATE_THEMES = {
    SkyState.DAY: {
        "border": "#f59e0b",
        "badge_bg": "#422006",
        "badge_fg": "#fde68a",
        "obs_bg": "#7f1d1d",
        "obs_fg": "#fecaca",
        "site_bg": "#431407",
        "site_fg": "#fed7aa",
    },
    SkyState.CIVIL_TWILIGHT: {
        "border": "#f97316",
        "badge_bg": "#4c0519",
        "badge_fg": "#fbcfe8",
        "obs_bg": "#7f1d1d",
        "obs_fg": "#fecaca",
        "site_bg": "#3b0764",
        "site_fg": "#e9d5ff",
    },
    SkyState.NAUTICAL_TWILIGHT: {
        "border": "#38bdf8",
        "badge_bg": "#082f49",
        "badge_fg": "#bae6fd",
        "obs_bg": "#9a3412",
        "obs_fg": "#fed7aa",
        "site_bg": "#1e3a8a",
        "site_fg": "#dbeafe",
    },
    SkyState.ASTRONOMICAL_TWILIGHT: {
        "border": "#8b5cf6",
        "badge_bg": "#2e1065",
        "badge_fg": "#ddd6fe",
        "obs_bg": "#334155",
        "obs_fg": "#e2e8f0",
        "site_bg": "#312e81",
        "site_fg": "#e0e7ff",
    },
    SkyState.ASTRONOMICAL_NIGHT: {
        "border": "#22c55e",
        "badge_bg": "#052e16",
        "badge_fg": "#bbf7d0",
        "obs_bg": "#14532d",
        "obs_fg": "#dcfce7",
        "site_bg": "#0f172a",
        "site_fg": "#a7f3d0",
    },
}


class RubinClockApp:
    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.config: AppConfig = load_config()
        self.current_site: Site = self.config.selected_site()

        self.transition_cache = None
        self.settings_window: ctk.CTkToplevel | None = None

        self._drag_origin: tuple[int, int] | None = None
        self._resize_edge: str | None = None
        self._resize_origin: tuple[int, int, int, int, int, int] | None = None

        self._icon: pystray.Icon | None = None

        self.root = ctk.CTk()
        self.root.minsize(MIN_WIDTH, MIN_HEIGHT)
        self.site_var = ctk.StringVar(master=self.root, value=self.current_site.name)

        self._setup_window()
        self._apply_window_icon()
        self._build_widgets()
        self._start_tray_icon()
        self.root.after(120, self._pin_to_desktop_layer)
        self.root.after(1500, self._schedule_bottom_pin)
        self._tick()

    def _lang(self) -> str:
        return self.config.language if self.config.language in I18N else "zh"

    def _t(self, key: str) -> str:
        return I18N[self._lang()].get(key, key)

    def _state_text(self, state: SkyState) -> str:
        return self._t(STATE_TEXT_KEYS[state])

    def _resource_path(self, relative: str) -> Path:
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        return base / relative

    def _setup_window(self) -> None:
        self.root.title(self._t("app_title"))
        self.root.geometry("560x380+120+120")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", False)
        self.root.attributes("-alpha", 0.96)
        self.root.configure(fg_color="#020617")

        self.root.bind("<Motion>", self._on_pointer_motion, add="+")
        self.root.bind("<ButtonPress-1>", self._on_pointer_down, add="+")
        self.root.bind("<B1-Motion>", self._on_pointer_drag, add="+")
        self.root.bind("<ButtonRelease-1>", self._on_pointer_up, add="+")

    def _apply_window_icon(self) -> None:
        icon_path = self._resource_path("assets/app_icon.ico")
        if not icon_path.exists():
            return
        try:
            self.root.iconbitmap(default=str(icon_path))
        except Exception:
            pass

    def _bind_drag(self, widget) -> None:
        widget.bind("<ButtonPress-1>", self._on_drag_start, add="+")
        widget.bind("<B1-Motion>", self._on_drag_move, add="+")

    def _build_widgets(self) -> None:
        self.shell = ctk.CTkFrame(
            self.root,
            corner_radius=24,
            fg_color="#0b1220",
            border_width=2,
            border_color="#334155",
        )
        self.shell.pack(fill="both", expand=True, padx=14, pady=14)

        header = ctk.CTkFrame(self.shell, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(14, 8))
        self._bind_drag(header)

        self.site_chip = ctk.CTkLabel(
            header,
            text=self.current_site.name,
            font=("Microsoft YaHei UI", 13, "bold"),
            fg_color="#1e293b",
            text_color="#e2e8f0",
            corner_radius=999,
            padx=14,
            pady=6,
        )
        self.site_chip.pack(side="left")

        controls = ctk.CTkFrame(header, fg_color="transparent")
        controls.pack(side="right")

        self.lang_btn = ctk.CTkButton(controls, width=58, height=30, command=self._toggle_language)
        self.lang_btn.pack(side="left", padx=(0, 6))

        self.settings_btn = ctk.CTkButton(controls, width=58, height=30, command=self.open_settings)
        self.settings_btn.pack(side="left", padx=(0, 6))

        self.hide_btn = ctk.CTkButton(controls, width=58, height=30, command=self.hide_window)
        self.hide_btn.pack(side="left", padx=(0, 6))

        self.exit_btn = ctk.CTkButton(
            controls,
            width=58,
            height=30,
            command=self.exit_app,
            fg_color="#991b1b",
            hover_color="#7f1d1d",
        )
        self.exit_btn.pack(side="left")

        self.title_label = ctk.CTkLabel(
            self.shell,
            text="",
            font=("Microsoft YaHei UI", 14, "bold"),
            text_color="#93c5fd",
        )
        self.title_label.pack(pady=(6, 2))
        self._bind_drag(self.title_label)

        self.time_label = ctk.CTkLabel(
            self.shell,
            text="--:--:--",
            font=("Cascadia Mono", 64, "bold"),
            text_color="#f8fafc",
        )
        self.time_label.pack(pady=(0, 2))
        self._bind_drag(self.time_label)

        self.date_label = ctk.CTkLabel(
            self.shell,
            text="",
            font=("Microsoft YaHei UI", 13),
            text_color="#cbd5e1",
        )
        self.date_label.pack(pady=(0, 8))
        self._bind_drag(self.date_label)

        badges = ctk.CTkFrame(self.shell, fg_color="transparent")
        badges.pack(pady=(0, 12))
        self._bind_drag(badges)

        self.state_badge = ctk.CTkLabel(
            badges,
            text="",
            font=("Microsoft YaHei UI", 13, "bold"),
            fg_color="#1f2937",
            text_color="#f8fafc",
            corner_radius=999,
            padx=14,
            pady=5,
        )
        self.state_badge.pack(side="left", padx=(0, 10))

        self.observe_badge = ctk.CTkLabel(
            badges,
            text="",
            font=("Microsoft YaHei UI", 13, "bold"),
            fg_color="#334155",
            text_color="#f8fafc",
            corner_radius=999,
            padx=14,
            pady=5,
        )
        self.observe_badge.pack(side="left")

        metrics = ctk.CTkFrame(self.shell, fg_color="transparent")
        metrics.pack(fill="x", padx=16, pady=(0, 10))
        metrics.grid_columnconfigure((0, 1), weight=1)

        self.alt_card = ctk.CTkFrame(metrics, corner_radius=14, fg_color="#111827")
        self.alt_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.alt_title_label = ctk.CTkLabel(self.alt_card, text="", font=("Microsoft YaHei UI", 12), text_color="#9ca3af")
        self.alt_title_label.pack(pady=(8, 2))
        self.alt_value = ctk.CTkLabel(self.alt_card, text="--", font=("Cascadia Mono", 26, "bold"), text_color="#e5e7eb")
        self.alt_value.pack(pady=(0, 8))

        self.next_card = ctk.CTkFrame(metrics, corner_radius=14, fg_color="#111827")
        self.next_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.next_title_label = ctk.CTkLabel(self.next_card, text="", font=("Microsoft YaHei UI", 12), text_color="#9ca3af")
        self.next_title_label.pack(pady=(8, 2))
        self.next_value = ctk.CTkLabel(self.next_card, text="--", font=("Cascadia Mono", 24, "bold"), text_color="#e5e7eb")
        self.next_value.pack(pady=(0, 8))

        self.next_state_label = ctk.CTkLabel(self.shell, text="", font=("Microsoft YaHei UI", 12), text_color="#cbd5e1")
        self.next_state_label.pack(pady=(0, 10))

        self.footer_label = ctk.CTkLabel(
            self.shell,
            text="",
            font=("Microsoft YaHei UI", 11),
            text_color="#64748b",
        )
        self.footer_label.pack(pady=(0, 12))
        self._bind_drag(self.footer_label)

        self._bind_drag(self.shell)
        self._apply_translations()

    def _apply_translations(self) -> None:
        self.root.title(self._t("app_title"))
        self.title_label.configure(text=self._t("clock_title"))
        self.settings_btn.configure(text=self._t("settings"))
        self.hide_btn.configure(text=self._t("hide"))
        self.exit_btn.configure(text=self._t("exit"))
        self.lang_btn.configure(text="EN" if self._lang() == "zh" else "中")
        self.alt_title_label.configure(text=self._t("solar_altitude"))
        self.next_title_label.configure(text=self._t("next_countdown"))
        self.footer_label.configure(text=self._t("drag_hint"))

        if self._icon is not None:
            self._icon.title = self._t("tray_title")

    def _pin_to_desktop_layer(self) -> None:
        if sys.platform != "win32" or not self.root.winfo_exists() or not self.root.winfo_viewable():
            return

        try:
            ctypes.windll.user32.SetWindowPos(
                int(self.root.winfo_id()),
                HWND_BOTTOM,
                0,
                0,
                0,
                0,
                BOTTOM_FLAGS,
            )
        except Exception:
            pass

    def _schedule_bottom_pin(self) -> None:
        self._pin_to_desktop_layer()
        if self.root.winfo_exists():
            self.root.after(1500, self._schedule_bottom_pin)

    def _root_local_xy(self, event) -> tuple[int, int]:
        return (
            event.x_root - self.root.winfo_rootx(),
            event.y_root - self.root.winfo_rooty(),
        )

    def _get_resize_edge(self, x: int, y: int) -> str | None:
        width = self.root.winfo_width()
        height = self.root.winfo_height()

        left = x <= RESIZE_MARGIN
        right = x >= width - RESIZE_MARGIN
        top = y <= RESIZE_MARGIN
        bottom = y >= height - RESIZE_MARGIN

        if top and left:
            return "nw"
        if top and right:
            return "ne"
        if bottom and left:
            return "sw"
        if bottom and right:
            return "se"
        if top:
            return "n"
        if bottom:
            return "s"
        if left:
            return "w"
        if right:
            return "e"
        return None

    def _on_pointer_motion(self, event) -> None:
        if self._resize_edge is not None:
            return

        x, y = self._root_local_xy(event)
        edge = self._get_resize_edge(x, y)
        self.root.configure(cursor=RESIZE_CURSOR.get(edge, "arrow"))

    def _on_pointer_down(self, event):
        x, y = self._root_local_xy(event)
        edge = self._get_resize_edge(x, y)
        if edge is None:
            return None

        self._resize_edge = edge
        self._resize_origin = (
            self.root.winfo_x(),
            self.root.winfo_y(),
            self.root.winfo_width(),
            self.root.winfo_height(),
            event.x_root,
            event.y_root,
        )
        return "break"

    def _on_pointer_drag(self, event):
        if self._resize_edge is None or self._resize_origin is None:
            return None

        start_x, start_y, start_w, start_h, press_x_root, press_y_root = self._resize_origin
        dx = event.x_root - press_x_root
        dy = event.y_root - press_y_root

        new_x = start_x
        new_y = start_y
        new_w = start_w
        new_h = start_h

        if "e" in self._resize_edge:
            new_w = max(MIN_WIDTH, start_w + dx)
        if "s" in self._resize_edge:
            new_h = max(MIN_HEIGHT, start_h + dy)

        if "w" in self._resize_edge:
            proposed = start_w - dx
            if proposed < MIN_WIDTH:
                dx = start_w - MIN_WIDTH
                proposed = MIN_WIDTH
            new_w = proposed
            new_x = start_x + dx

        if "n" in self._resize_edge:
            proposed = start_h - dy
            if proposed < MIN_HEIGHT:
                dy = start_h - MIN_HEIGHT
                proposed = MIN_HEIGHT
            new_h = proposed
            new_y = start_y + dy

        self.root.geometry(f"{int(new_w)}x{int(new_h)}+{int(new_x)}+{int(new_y)}")
        self._pin_to_desktop_layer()
        return "break"

    def _on_pointer_up(self, event):
        self._resize_edge = None
        self._resize_origin = None
        self._drag_origin = None
        self._on_pointer_motion(event)
        self._pin_to_desktop_layer()
        return None

    def _on_drag_start(self, event) -> None:
        if self._resize_edge is not None:
            return

        x, y = self._root_local_xy(event)
        if self._get_resize_edge(x, y) is not None:
            return

        self._drag_origin = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _on_drag_move(self, event) -> None:
        if self._resize_edge is not None or self._drag_origin is None:
            return

        x = event.x_root - self._drag_origin[0]
        y = event.y_root - self._drag_origin[1]
        self.root.geometry(f"+{x}+{y}")
        self._pin_to_desktop_layer()

    def _tick(self) -> None:
        now_utc = datetime.now(timezone.utc)
        site = self.current_site

        solar_time = compute_true_solar_time(now_utc, site.lon)
        altitude = compute_solar_altitude(now_utc, site.lat, site.lon)
        state = classify_sky_state(altitude)

        needs_transition_refresh = (
            self.transition_cache is None
            or now_utc >= self.transition_cache.at_utc
            or self.transition_cache.from_state != state
        )
        if needs_transition_refresh:
            self.transition_cache = next_transition(now_utc, site)

        self._render(now_utc, solar_time, altitude, state)
        self.root.after(1000, self._tick)

    def _render(self, now_utc: datetime, solar_time: datetime, altitude: float, state: SkyState) -> None:
        theme = STATE_THEMES[state]
        self.shell.configure(border_color=theme["border"])
        self.site_chip.configure(text=self.current_site.name, fg_color=theme["site_bg"], text_color=theme["site_fg"])

        self.time_label.configure(text=solar_time.strftime("%H:%M:%S"))
        self.date_label.configure(text=f"{self._t('local_date')} {solar_time.strftime('%Y-%m-%d')}")

        state_text = self._state_text(state)
        self.state_badge.configure(
            text=f"{self._t('state_prefix')} {state_text}",
            fg_color=theme["badge_bg"],
            text_color=theme["badge_fg"],
        )

        is_observable = state == SkyState.ASTRONOMICAL_NIGHT
        observe_text = self._t("observable") if is_observable else self._t("not_observable")
        self.observe_badge.configure(
            text=f"{self._t('observe_prefix')} {observe_text}",
            fg_color=theme["obs_bg"],
            text_color=theme["obs_fg"],
        )

        self.alt_value.configure(text=f"{altitude:+06.2f}°")

        if self.transition_cache and self.transition_cache.found:
            remaining = max(0, int((self.transition_cache.at_utc - now_utc).total_seconds()))
            next_state = self._state_text(self.transition_cache.to_state)
            self.next_value.configure(text=self._format_seconds(remaining))
            self.next_state_label.configure(text=f"{self._t('next_state')}: {next_state}")
        else:
            self.next_value.configure(text="--:--:--")
            self.next_state_label.configure(text=f"{self._t('next_state')}: {self._t('no_transition')}")

    @staticmethod
    def _format_seconds(value: int) -> str:
        hours = value // 3600
        minutes = (value % 3600) // 60
        seconds = value % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _load_tray_image(self) -> Image.Image:
        candidates = [
            self._resource_path("assets/app_icon.png"),
            self._resource_path("assets/app_icon.ico"),
        ]

        for path in candidates:
            if not path.exists():
                continue
            try:
                image = Image.open(path).convert("RGBA")
                resampling = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
                return image.resize((64, 64), resampling)
            except Exception:
                continue

        return self._build_fallback_tray_image()

    @staticmethod
    def _build_fallback_tray_image() -> Image.Image:
        image = Image.new("RGBA", (64, 64), (8, 15, 31, 255))
        draw = ImageDraw.Draw(image)
        draw.ellipse((9, 9, 55, 55), fill=(15, 23, 42, 255), outline=(56, 189, 248, 255), width=3)
        draw.line((32, 32, 32, 18), fill=(226, 232, 240, 255), width=4)
        draw.line((32, 32, 44, 40), fill=(226, 232, 240, 255), width=4)
        draw.ellipse((29, 29, 35, 35), fill=(226, 232, 240, 255))
        return image

    def _start_tray_icon(self) -> None:
        image = self._load_tray_image()
        self._icon = pystray.Icon("rubin_solar_clock", image, self._t("tray_title"))
        self._icon.menu = self._build_tray_menu()
        thread = threading.Thread(target=self._icon.run, daemon=True)
        thread.start()

    def _refresh_tray_menu(self) -> None:
        if self._icon is None:
            return
        self._icon.title = self._t("tray_title")
        self._icon.menu = self._build_tray_menu()
        self._icon.update_menu()

    def _site_switch_action(self, site_id: str) -> Callable:
        def _action(icon, item) -> None:
            self._run_on_ui_thread(self._switch_site, site_id)

        return _action

    def _site_checked_action(self, site_id: str) -> Callable:
        def _checked(item) -> bool:
            return self.current_site.id == site_id

        return _checked

    def _language_switch_action(self, language: str) -> Callable:
        def _action(icon, item) -> None:
            self._run_on_ui_thread(self._set_language, language)

        return _action

    def _language_checked_action(self, language: str) -> Callable:
        def _checked(item) -> bool:
            return self._lang() == language

        return _checked

    def _build_tray_menu(self) -> pystray.Menu:
        site_items: list[pystray.MenuItem] = []
        for site in self.config.sites:
            site_items.append(
                pystray.MenuItem(
                    site.name,
                    self._site_switch_action(site.id),
                    checked=self._site_checked_action(site.id),
                    radio=True,
                )
            )

        lang_items: list[pystray.MenuItem] = []
        for code, label in LANGUAGE_LABELS.items():
            lang_items.append(
                pystray.MenuItem(
                    label,
                    self._language_switch_action(code),
                    checked=self._language_checked_action(code),
                    radio=True,
                )
            )

        return pystray.Menu(
            pystray.MenuItem(self._t("show_window"), lambda icon, item: self._run_on_ui_thread(self.show_window), default=True),
            pystray.MenuItem(self._t("hide_window"), lambda icon, item: self._run_on_ui_thread(self.hide_window)),
            pystray.MenuItem(self._t("switch_site"), pystray.Menu(*site_items)),
            pystray.MenuItem(self._t("language"), pystray.Menu(*lang_items)),
            pystray.MenuItem(self._t("open_settings"), lambda icon, item: self._run_on_ui_thread(self.open_settings)),
            pystray.MenuItem(self._t("tray_exit"), lambda icon, item: self._run_on_ui_thread(self.exit_app)),
        )

    def _run_on_ui_thread(self, callback: Callable, *args) -> None:
        self.root.after(0, lambda: callback(*args))

    def show_window(self) -> None:
        self.root.deiconify()
        self._pin_to_desktop_layer()

    def hide_window(self) -> None:
        self.root.withdraw()

    def exit_app(self) -> None:
        if self._icon is not None:
            self._icon.stop()
            self._icon = None
        self.root.quit()
        self.root.destroy()

    def _switch_site(self, site_id: str) -> None:
        self.config = set_selected_site(self.config, site_id)
        self.current_site = self.config.selected_site()
        self.site_var.set(self.current_site.name)
        self.transition_cache = None
        self._refresh_tray_menu()

    def _toggle_language(self) -> None:
        next_lang = "en" if self._lang() == "zh" else "zh"
        self._set_language(next_lang)

    def _set_language(self, language: str) -> None:
        if language not in LANGUAGE_LABELS:
            return
        if language == self._lang():
            return

        self.config = set_language(self.config, language)
        self._apply_translations()
        self.transition_cache = None
        self._refresh_tray_menu()

        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.destroy()
            self.settings_window = None
            self.open_settings()

    def _language_display(self, code: str) -> str:
        if self._lang() == "zh":
            return "中文" if code == "zh" else "English"
        return "Chinese" if code == "zh" else "English"

    def _language_code_from_display(self, display: str) -> str:
        return "zh" if display in {"中文", "Chinese"} else "en"

    def open_settings(self) -> None:
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.focus()
            self.settings_window.lift()
            return

        self.settings_window = ctk.CTkToplevel(self.root)
        self.settings_window.title(self._t("settings_title"))
        self.settings_window.geometry("460x470")
        self.settings_window.attributes("-topmost", True)
        self.settings_window.configure(fg_color="#020617")

        container = ctk.CTkFrame(self.settings_window, corner_radius=16, fg_color="#0b1220", border_width=1, border_color="#334155")
        container.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(container, text=self._t("current_site"), font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w", padx=14, pady=(14, 6))

        option_values = [site.name for site in self.config.sites]
        option_menu = ctk.CTkOptionMenu(container, variable=self.site_var, values=option_values)
        option_menu.pack(fill="x", padx=14, pady=(0, 8))

        ctk.CTkButton(container, text=self._t("set_current"), command=lambda: self._set_site_from_name(self.site_var.get())).pack(fill="x", padx=14, pady=(0, 14))

        ctk.CTkLabel(container, text=self._t("interface_language"), font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w", padx=14, pady=(0, 6))

        language_values = [self._language_display("zh"), self._language_display("en")]
        language_var = ctk.StringVar(master=self.settings_window, value=self._language_display(self._lang()))
        language_menu = ctk.CTkOptionMenu(container, variable=language_var, values=language_values)
        language_menu.pack(fill="x", padx=14, pady=(0, 8))

        ctk.CTkButton(
            container,
            text=self._t("apply_language"),
            command=lambda: self._set_language(self._language_code_from_display(language_var.get())),
        ).pack(fill="x", padx=14, pady=(0, 14))

        ctk.CTkLabel(container, text=self._t("new_site"), font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w", padx=14, pady=(0, 6))

        name_entry = ctk.CTkEntry(container, placeholder_text=self._t("site_name_placeholder"))
        name_entry.pack(fill="x", padx=14, pady=4)

        lat_entry = ctk.CTkEntry(container, placeholder_text=self._t("lat_placeholder"))
        lat_entry.pack(fill="x", padx=14, pady=4)

        lon_entry = ctk.CTkEntry(container, placeholder_text=self._t("lon_placeholder"))
        lon_entry.pack(fill="x", padx=14, pady=4)

        elev_entry = ctk.CTkEntry(container, placeholder_text=self._t("elev_placeholder"))
        elev_entry.pack(fill="x", padx=14, pady=4)

        result_label = ctk.CTkLabel(container, text="", font=("Microsoft YaHei UI", 12))
        result_label.pack(anchor="w", padx=14, pady=(8, 4))

        ctk.CTkButton(
            container,
            text=self._t("save_site"),
            command=lambda: self._save_site(name_entry, lat_entry, lon_entry, elev_entry, result_label, option_menu),
        ).pack(fill="x", padx=14, pady=6)

        ctk.CTkLabel(
            container,
            text=self._t("builtin_hint"),
            font=("Microsoft YaHei UI", 11),
            text_color="#94a3b8",
        ).pack(anchor="w", padx=14, pady=(8, 12))

    def _set_site_from_name(self, site_name: str) -> None:
        for site in self.config.sites:
            if site.name == site_name:
                self._switch_site(site.id)
                return

    def _save_site(
        self,
        name_entry: ctk.CTkEntry,
        lat_entry: ctk.CTkEntry,
        lon_entry: ctk.CTkEntry,
        elev_entry: ctk.CTkEntry,
        result_label: ctk.CTkLabel,
        option_menu: ctk.CTkOptionMenu,
    ) -> None:
        name = name_entry.get().strip()
        if not name:
            result_label.configure(text=self._t("err_site_name"), text_color="#f87171")
            return

        try:
            lat = float(lat_entry.get().strip())
            lon = float(lon_entry.get().strip())
            elevation_m = float(elev_entry.get().strip()) if elev_entry.get().strip() else 0.0
        except ValueError:
            result_label.configure(text=self._t("err_parse"), text_color="#f87171")
            return

        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            result_label.configure(text=self._t("err_range"), text_color="#f87171")
            return

        candidate_id = create_site_id(name)
        site_id = ensure_unique_site_id(self.config, candidate_id)
        new_site = Site(id=site_id, name=name, lat=lat, lon=lon, elevation_m=elevation_m)

        self.config = upsert_site(self.config, new_site, select_after_insert=True)
        self.current_site = new_site
        self.transition_cache = None

        self.site_var.set(new_site.name)
        option_menu.configure(values=[site.name for site in self.config.sites])

        name_entry.delete(0, "end")
        lat_entry.delete(0, "end")
        lon_entry.delete(0, "end")
        elev_entry.delete(0, "end")

        result_label.configure(text=self._t("saved_ok"), text_color="#4ade80")
        self._refresh_tray_menu()

    def run(self) -> None:
        try:
            self.root.mainloop()
        finally:
            if self._icon is not None:
                self._icon.stop()
                self._icon = None


__all__ = ["RubinClockApp"]
