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

STATE_COLORS = {
    SkyState.DAY: "#f97316",
    SkyState.CIVIL_TWILIGHT: "#fb7185",
    SkyState.NAUTICAL_TWILIGHT: "#38bdf8",
    SkyState.ASTRONOMICAL_TWILIGHT: "#a78bfa",
    SkyState.ASTRONOMICAL_NIGHT: "#22c55e",
}


class RubinClockApp:
    def __init__(self) -> None:
        ctk.set_appearance_mode("system")
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
        self.root.geometry("420x250+120+120")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.93)
        self.root.configure(fg_color="#0f172a")

        self.root.bind("<ButtonPress-1>", self._on_drag_start)
        self.root.bind("<B1-Motion>", self._on_drag_move)

    def _build_widgets(self) -> None:
        container = ctk.CTkFrame(self.root, corner_radius=18, fg_color="#111827")
        container.pack(fill="both", expand=True, padx=10, pady=10)

        top = ctk.CTkFrame(container, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(8, 2))

        top.bind("<ButtonPress-1>", self._on_drag_start)
        top.bind("<B1-Motion>", self._on_drag_move)

        self.site_label = ctk.CTkLabel(top, text=f"站点: {self.current_site.name}", font=("Microsoft YaHei UI", 14, "bold"))
        self.site_label.pack(side="left")

        ctk.CTkButton(top, text="设置", width=52, command=self.open_settings).pack(side="right", padx=(6, 0))
        ctk.CTkButton(top, text="隐藏", width=52, command=self.hide_window).pack(side="right", padx=(6, 0))
        ctk.CTkButton(top, text="退出", width=52, command=self.exit_app, fg_color="#b91c1c", hover_color="#991b1b").pack(side="right")

        self.time_label = ctk.CTkLabel(
            container,
            text="--:--:--",
            font=("Consolas", 56, "bold"),
            text_color="#f8fafc",
        )
        self.time_label.pack(pady=(6, 4))

        self.state_label = ctk.CTkLabel(container, text="状态: --", font=("Microsoft YaHei UI", 15, "bold"))
        self.state_label.pack(pady=(0, 4))

        self.alt_label = ctk.CTkLabel(container, text="太阳高度角: --", font=("Microsoft YaHei UI", 13))
        self.alt_label.pack(pady=(0, 2))

        self.next_label = ctk.CTkLabel(container, text="下一节点: --", font=("Microsoft YaHei UI", 13))
        self.next_label.pack(pady=(0, 8))

        hint = ctk.CTkLabel(
            container,
            text="拖动任意空白区域可移动窗口",
            font=("Microsoft YaHei UI", 11),
            text_color="#9ca3af",
        )
        hint.pack(pady=(0, 8))

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
        self.site_label.configure(text=f"站点: {self.current_site.name}")
        self.time_label.configure(text=solar_time.strftime("%H:%M:%S"))

        is_observable = state == SkyState.ASTRONOMICAL_NIGHT
        suitability = "适合观测" if is_observable else "不适合观测"
        state_text = STATE_LABELS[state]
        self.state_label.configure(text=f"状态: {state_text} | {suitability}", text_color=STATE_COLORS[state])

        self.alt_label.configure(text=f"太阳高度角: {altitude:+06.2f}°")

        if self.transition_cache and self.transition_cache.found:
            remaining = max(0, int((self.transition_cache.at_utc - now_utc).total_seconds()))
            next_state = STATE_LABELS[self.transition_cache.to_state]
            self.next_label.configure(text=f"下一节点: {next_state} ({self._format_seconds(remaining)})")
        else:
            self.next_label.configure(text="下一节点: 48 小时内无状态切换")

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
        image = Image.new("RGBA", (64, 64), (15, 23, 42, 255))
        draw = ImageDraw.Draw(image)
        draw.ellipse((8, 8, 56, 56), outline=(56, 189, 248, 255), width=4)
        draw.line((32, 32, 32, 16), fill=(248, 250, 252, 255), width=4)
        draw.line((32, 32, 44, 38), fill=(248, 250, 252, 255), width=4)
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
        self.settings_window.geometry("420x360")
        self.settings_window.attributes("-topmost", True)

        container = ctk.CTkFrame(self.settings_window)
        container.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(container, text="当前站点", font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w", pady=(6, 4))

        option_values = [site.name for site in self.config.sites]
        option_menu = ctk.CTkOptionMenu(container, variable=self.site_var, values=option_values)
        option_menu.pack(fill="x", pady=(0, 8))

        ctk.CTkButton(container, text="设为当前", command=lambda: self._set_site_from_name(self.site_var.get())).pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(container, text="新增站点", font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w", pady=(2, 4))

        name_entry = ctk.CTkEntry(container, placeholder_text="站点名称")
        name_entry.pack(fill="x", pady=4)

        lat_entry = ctk.CTkEntry(container, placeholder_text="纬度 (例如 -30.2446)")
        lat_entry.pack(fill="x", pady=4)

        lon_entry = ctk.CTkEntry(container, placeholder_text="经度 (例如 -70.7494)")
        lon_entry.pack(fill="x", pady=4)

        elev_entry = ctk.CTkEntry(container, placeholder_text="海拔米数 (可选)")
        elev_entry.pack(fill="x", pady=4)

        result_label = ctk.CTkLabel(container, text="", font=("Microsoft YaHei UI", 12))
        result_label.pack(anchor="w", pady=(6, 4))

        ctk.CTkButton(
            container,
            text="保存新站点",
            command=lambda: self._save_site(name_entry, lat_entry, lon_entry, elev_entry, result_label, option_menu),
        ).pack(fill="x", pady=6)

        ctk.CTkLabel(
            container,
            text="提示: Rubin 默认台址会始终保留。",
            font=("Microsoft YaHei UI", 11),
            text_color="#9ca3af",
        ).pack(anchor="w", pady=(8, 0))

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
            result_label.configure(text="请输入站点名称", text_color="#ef4444")
            return

        try:
            lat = float(lat_entry.get().strip())
            lon = float(lon_entry.get().strip())
            elevation_m = float(elev_entry.get().strip()) if elev_entry.get().strip() else 0.0
        except ValueError:
            result_label.configure(text="经纬度/海拔格式错误", text_color="#ef4444")
            return

        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            result_label.configure(text="纬度需在 [-90, 90] 且经度需在 [-180, 180]", text_color="#ef4444")
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

        result_label.configure(text="站点保存成功", text_color="#22c55e")
        self._refresh_tray_menu()

    def run(self) -> None:
        try:
            self.root.mainloop()
        finally:
            if self._icon is not None:
                self._icon.stop()
                self._icon = None


__all__ = ["RubinClockApp"]


