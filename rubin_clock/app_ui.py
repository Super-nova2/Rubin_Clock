from __future__ import annotations

import threading
from datetime import datetime, timezone
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
    set_selected_site,
    upsert_site,
)


STATE_LABELS = {
    SkyState.DAY: "白天",
    SkyState.CIVIL_TWILIGHT: "民用晨昏",
    SkyState.NAUTICAL_TWILIGHT: "航海晨昏",
    SkyState.ASTRONOMICAL_TWILIGHT: "天文晨昏",
    SkyState.ASTRONOMICAL_NIGHT: "天文夜",
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

        self._drag_origin = (0, 0)
        self._icon: pystray.Icon | None = None

        self.root = ctk.CTk()
        self.site_var = ctk.StringVar(master=self.root, value=self.current_site.name)

        self._setup_window()
        self._build_widgets()
        self._start_tray_icon()
        self._tick()

    def _setup_window(self) -> None:
        self.root.title("Rubin 太阳时钟")
        self.root.geometry("560x360+120+120")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.96)
        self.root.configure(fg_color="#020617")

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

        ctk.CTkButton(controls, text="设置", width=58, height=30, command=self.open_settings).pack(side="left", padx=(0, 6))
        ctk.CTkButton(controls, text="隐藏", width=58, height=30, command=self.hide_window).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            controls,
            text="退出",
            width=58,
            height=30,
            command=self.exit_app,
            fg_color="#991b1b",
            hover_color="#7f1d1d",
        ).pack(side="left")

        title = ctk.CTkLabel(
            self.shell,
            text="Rubin 台址真太阳时",
            font=("Microsoft YaHei UI", 14, "bold"),
            text_color="#93c5fd",
        )
        title.pack(pady=(6, 2))
        self._bind_drag(title)

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
            text="当地日期 --",
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
            text="状态 --",
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
            text="观测判定 --",
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
        ctk.CTkLabel(self.alt_card, text="太阳高度角", font=("Microsoft YaHei UI", 12), text_color="#9ca3af").pack(pady=(8, 2))
        self.alt_value = ctk.CTkLabel(self.alt_card, text="--", font=("Cascadia Mono", 26, "bold"), text_color="#e5e7eb")
        self.alt_value.pack(pady=(0, 8))

        self.next_card = ctk.CTkFrame(metrics, corner_radius=14, fg_color="#111827")
        self.next_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        ctk.CTkLabel(self.next_card, text="下一节点倒计时", font=("Microsoft YaHei UI", 12), text_color="#9ca3af").pack(pady=(8, 2))
        self.next_value = ctk.CTkLabel(self.next_card, text="--", font=("Cascadia Mono", 24, "bold"), text_color="#e5e7eb")
        self.next_value.pack(pady=(0, 8))

        self.next_state_label = ctk.CTkLabel(self.shell, text="下一状态: --", font=("Microsoft YaHei UI", 12), text_color="#cbd5e1")
        self.next_state_label.pack(pady=(0, 10))

        footer = ctk.CTkLabel(
            self.shell,
            text="拖动窗口上半部分可移动；右上角可隐藏到托盘",
            font=("Microsoft YaHei UI", 11),
            text_color="#64748b",
        )
        footer.pack(pady=(0, 12))
        self._bind_drag(footer)

        self._bind_drag(self.shell)

    def _on_drag_start(self, event) -> None:
        self._drag_origin = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _on_drag_move(self, event) -> None:
        x = event.x_root - self._drag_origin[0]
        y = event.y_root - self._drag_origin[1]
        self.root.geometry(f"+{x}+{y}")

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
        self.date_label.configure(text=f"当地日期 {solar_time.strftime('%Y-%m-%d')}")

        state_text = STATE_LABELS[state]
        self.state_badge.configure(
            text=f"状态 {state_text}",
            fg_color=theme["badge_bg"],
            text_color=theme["badge_fg"],
        )

        is_observable = state == SkyState.ASTRONOMICAL_NIGHT
        observe_text = "适合观测" if is_observable else "不适合观测"
        self.observe_badge.configure(
            text=f"观测判定 {observe_text}",
            fg_color=theme["obs_bg"],
            text_color=theme["obs_fg"],
        )

        self.alt_value.configure(text=f"{altitude:+06.2f}°")

        if self.transition_cache and self.transition_cache.found:
            remaining = max(0, int((self.transition_cache.at_utc - now_utc).total_seconds()))
            next_state = STATE_LABELS[self.transition_cache.to_state]
            self.next_value.configure(text=self._format_seconds(remaining))
            self.next_state_label.configure(text=f"下一状态: {next_state}")
        else:
            self.next_value.configure(text="--:--:--")
            self.next_state_label.configure(text="下一状态: 48 小时内无状态切换")

    @staticmethod
    def _format_seconds(value: int) -> str:
        hours = value // 3600
        minutes = (value % 3600) // 60
        seconds = value % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _start_tray_icon(self) -> None:
        image = self._build_tray_image()
        self._icon = pystray.Icon("rubin_solar_clock", image, "Rubin 太阳时钟")
        self._icon.menu = self._build_tray_menu()
        thread = threading.Thread(target=self._icon.run, daemon=True)
        thread.start()

    def _refresh_tray_menu(self) -> None:
        if self._icon is None:
            return
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

        return pystray.Menu(
            pystray.MenuItem("显示窗口", lambda icon, item: self._run_on_ui_thread(self.show_window), default=True),
            pystray.MenuItem("隐藏窗口", lambda icon, item: self._run_on_ui_thread(self.hide_window)),
            pystray.MenuItem("切换站点", pystray.Menu(*site_items)),
            pystray.MenuItem("打开设置", lambda icon, item: self._run_on_ui_thread(self.open_settings)),
            pystray.MenuItem("退出", lambda icon, item: self._run_on_ui_thread(self.exit_app)),
        )

    def _run_on_ui_thread(self, callback: Callable, *args) -> None:
        self.root.after(0, lambda: callback(*args))

    @staticmethod
    def _build_tray_image() -> Image.Image:
        image = Image.new("RGBA", (64, 64), (8, 15, 31, 255))
        draw = ImageDraw.Draw(image)
        draw.ellipse((9, 9, 55, 55), fill=(15, 23, 42, 255), outline=(56, 189, 248, 255), width=3)
        draw.line((32, 32, 32, 18), fill=(226, 232, 240, 255), width=4)
        draw.line((32, 32, 44, 40), fill=(226, 232, 240, 255), width=4)
        draw.ellipse((29, 29, 35, 35), fill=(226, 232, 240, 255))
        return image

    def show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()

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

    def open_settings(self) -> None:
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.focus()
            self.settings_window.lift()
            return

        self.settings_window = ctk.CTkToplevel(self.root)
        self.settings_window.title("站点设置")
        self.settings_window.geometry("460x410")
        self.settings_window.attributes("-topmost", True)
        self.settings_window.configure(fg_color="#020617")

        container = ctk.CTkFrame(self.settings_window, corner_radius=16, fg_color="#0b1220", border_width=1, border_color="#334155")
        container.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(container, text="当前站点", font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w", padx=14, pady=(14, 6))

        option_values = [site.name for site in self.config.sites]
        option_menu = ctk.CTkOptionMenu(container, variable=self.site_var, values=option_values)
        option_menu.pack(fill="x", padx=14, pady=(0, 8))

        ctk.CTkButton(container, text="设为当前", command=lambda: self._set_site_from_name(self.site_var.get())).pack(fill="x", padx=14, pady=(0, 14))

        ctk.CTkLabel(container, text="新增站点", font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w", padx=14, pady=(0, 6))

        name_entry = ctk.CTkEntry(container, placeholder_text="站点名称")
        name_entry.pack(fill="x", padx=14, pady=4)

        lat_entry = ctk.CTkEntry(container, placeholder_text="纬度 (例如 38.6068)")
        lat_entry.pack(fill="x", padx=14, pady=4)

        lon_entry = ctk.CTkEntry(container, placeholder_text="经度 (例如 93.8961)")
        lon_entry.pack(fill="x", padx=14, pady=4)

        elev_entry = ctk.CTkEntry(container, placeholder_text="海拔米数 (可选)")
        elev_entry.pack(fill="x", padx=14, pady=4)

        result_label = ctk.CTkLabel(container, text="", font=("Microsoft YaHei UI", 12))
        result_label.pack(anchor="w", padx=14, pady=(8, 4))

        ctk.CTkButton(
            container,
            text="保存新站点",
            command=lambda: self._save_site(name_entry, lat_entry, lon_entry, elev_entry, result_label, option_menu),
        ).pack(fill="x", padx=14, pady=6)

        ctk.CTkLabel(
            container,
            text="提示: 内置 Rubin 与 WFST 站点会自动保留。",
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
            result_label.configure(text="请输入站点名称", text_color="#f87171")
            return

        try:
            lat = float(lat_entry.get().strip())
            lon = float(lon_entry.get().strip())
            elevation_m = float(elev_entry.get().strip()) if elev_entry.get().strip() else 0.0
        except ValueError:
            result_label.configure(text="经纬度/海拔格式错误", text_color="#f87171")
            return

        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            result_label.configure(text="纬度需在 [-90, 90] 且经度需在 [-180, 180]", text_color="#f87171")
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

        result_label.configure(text="站点保存成功", text_color="#4ade80")
        self._refresh_tray_menu()

    def run(self) -> None:
        try:
            self.root.mainloop()
        finally:
            if self._icon is not None:
                self._icon.stop()
                self._icon = None


__all__ = ["RubinClockApp"]



