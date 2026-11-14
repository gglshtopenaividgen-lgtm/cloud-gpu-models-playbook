#!/usr/bin/env python3
"""dashboard_gui.py - Dark Glassmorphic Multi-Profile Account Switcher & Quota Hub.

Built with PySide6.
Visualizes the user's authentic Google One AI Premium profiles, live WebSocket connections,
and quota status with 1-click launchers for AI Studio (Argon), Gemini Pro, and Google Flow.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

sys.path.insert(0, str(Path(__file__).parent))
import profile_manager

BRIDGE_STATUS_URL = "http://127.0.0.1:9229/status"
EXTENSION_DIR = Path(__file__).parent / "extension"


class ProfileCard(QFrame):
    """Dark Glassmorphic card for a single Google Chrome Profile."""

    def __init__(self, profile_data: dict, parent=None):
        super().__init__(parent)
        self.profile_data = profile_data
        self.dir_name = profile_data.get("dir_name", "")
        self.is_premium = profile_data.get("is_ai_premium", False)
        self.setup_ui()

    def setup_ui(self):
        self.setObjectName("profileCard")
        border_color = "rgba(56, 189, 248, 0.45)" if self.is_premium else "rgba(255, 255, 255, 0.08)"
        bg_color = "rgba(18, 24, 38, 0.85)" if self.is_premium else "rgba(15, 18, 28, 0.65)"

        self.setStyleSheet(f"""
            QFrame#profileCard {{
                background: {bg_color};
                border: 1px solid {border_color};
                border-radius: 12px;
                padding: 14px;
            }}
            QFrame#profileCard:hover {{
                border-color: rgba(56, 189, 248, 0.7);
                background: rgba(22, 30, 48, 0.95);
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(14)

        # 1. Circular Avatar
        avatar_label = QLabel()
        avatar_label.setFixedSize(48, 48)
        pix = self.get_avatar_pixmap(self.profile_data.get("avatar_path"))
        avatar_label.setPixmap(pix)
        layout.addWidget(avatar_label)

        # 2. Profile Details
        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)

        title_layout = QHBoxLayout()
        name_lbl = QLabel(self.profile_data.get("name", self.dir_name))
        name_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #f8fafc;")
        title_layout.addWidget(name_lbl)

        if self.is_premium:
            tier_badge = QLabel(" AI PRO ⭐️ ")
            tier_badge.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #06b6d4);
                color: #ffffff;
                font-size: 10px;
                font-weight: 800;
                border-radius: 4px;
                padding: 2px 6px;
            """)
            title_layout.addWidget(tier_badge)

        conn_status = self.profile_data.get("is_connected", False)
        conn_badge = QLabel(" ONLINE " if conn_status else " STANDBY ")
        conn_badge.setStyleSheet(f"""
            background: {"rgba(16, 185, 129, 0.2)" if conn_status else "rgba(148, 163, 184, 0.15)"};
            color: {"#34d399" if conn_status else "#94a3b8"};
            border: 1px solid {"rgba(16, 185, 129, 0.4)" if conn_status else "rgba(148, 163, 184, 0.25)"};
            font-size: 9px;
            font-weight: 700;
            border-radius: 4px;
            padding: 2px 5px;
        """)
        title_layout.addWidget(conn_badge)
        title_layout.addStretch()
        info_layout.addLayout(title_layout)

        email_lbl = QLabel(self.profile_data.get("email") or "No Google Email bound")
        email_lbl.setStyleSheet("font-size: 11px; color: #94a3b8; font-family: monospace;")
        info_layout.addWidget(email_lbl)

        status_str = f"Dir: {self.dir_name}"
        cooldown_until = self.profile_data.get("cooldown_until", 0.0)
        now = time.time()
        if cooldown_until > now:
            rem = int(cooldown_until - now)
            status_str += f" · ⏳ Cooldown: {rem}s"
        else:
            status_str += f" · Ready (Reqs: {self.profile_data.get('requests_completed', 0)})"

        status_lbl = QLabel(status_str)
        status_lbl.setStyleSheet("font-size: 11px; color: #64748b;")
        info_layout.addWidget(status_lbl)

        layout.addLayout(info_layout, stretch=1)

        # 3. Quick Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        btn_ai_studio = QPushButton("AI Studio (Argon)")
        btn_ai_studio.setStyleSheet("""
            QPushButton {
                background: rgba(56, 189, 248, 0.15);
                border: 1px solid rgba(56, 189, 248, 0.4);
                color: #7dd3fc;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(56, 189, 248, 0.28);
                color: #bae6fd;
            }
        """)
        btn_ai_studio.clicked.connect(lambda: profile_manager.launch_profile_window(self.dir_name, "https://aistudio.google.com/prompts/new_chat"))
        btn_layout.addWidget(btn_ai_studio)

        btn_gemini = QPushButton("Gemini Deep Res")
        btn_gemini.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.15);
                color: #e2e8f0;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.12);
            }
        """)
        btn_gemini.clicked.connect(lambda: profile_manager.launch_profile_window(self.dir_name, "https://gemini.google.com/app"))
        btn_layout.addWidget(btn_gemini)

        layout.addLayout(btn_layout)

    def get_avatar_pixmap(self, path: str | None) -> QPixmap:
        """Loads and crops avatar into a smooth circular pixmap."""
        size = 48
        if path and os.path.exists(path):
            src = QPixmap(path)
        else:
            # Generate generic fallback circle
            src = QPixmap(size, size)
            src.fill(QColor("#0369a1" if self.is_premium else "#334155"))

        scaled = src.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        out = QPixmap(size, size)
        out.fill(Qt.transparent)

        painter = QPainter(out)
        painter.setRenderHint(QPainter.Antialiasing)
        path_clip = QPainterPath()
        path_clip.addEllipse(0, 0, size, size)
        painter.setClipPath(path_clip)
        painter.drawPixmap(0, 0, scaled)
        painter.end()
        return out


class AccountSwitcherGUI(QMainWindow):
    """Master Multi-Profile Dashboard."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Antigravity Multi-Account Hub · Gemini 4 Argon Brain")
        self.resize(760, 560)
        self.setup_ui()

        # Refresh Timer (every 2.5s)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_profiles)
        self.timer.start(2500)

    def setup_ui(self):
        self.setStyleSheet("""
            QMainWindow {
                background: #090c15;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Header Section
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: rgba(18, 24, 38, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 12px 16px;
            }
        """)
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(0, 0, 0, 0)

        title_vbox = QVBoxLayout()
        title_lbl = QLabel("Google AI Premium Accounts & Quota Router")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 800; color: #f8fafc;")
        sub_lbl = QLabel("Zero-Guest Mode · Active Chrome Profiles · 1M Token Context via Gemini 4 Argon")
        sub_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
        title_vbox.addWidget(title_lbl)
        title_vbox.addWidget(sub_lbl)
        h_layout.addLayout(title_vbox, stretch=1)

        # Extension copy button
        btn_ext = QPushButton("Copy Extension Path")
        btn_ext.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.15);
                color: #e2e8f0;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.12); }
        """)
        btn_ext.clicked.connect(self.copy_extension_path)
        h_layout.addWidget(btn_ext)

        main_layout.addWidget(header_frame)

        # Scroll Area for Profiles
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setSpacing(10)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll.setWidget(self.cards_container)
        main_layout.addWidget(self.scroll, stretch=1)

        # Initial populate
        self.refresh_profiles()

    def copy_extension_path(self):
        ext_path = str(EXTENSION_DIR.resolve())
        clipboard = QApplication.clipboard()
        clipboard.setText(ext_path)
        print(f"[GUI] Copied extension path to clipboard: {ext_path}")

    def refresh_profiles(self):
        # Fetch status from local bridge or fallback to profile_manager
        enriched_profiles = []
        try:
            req = urllib.request.Request(BRIDGE_STATUS_URL)
            with urllib.request.urlopen(req, timeout=1.0) as res:
                data = json.loads(res.read().decode("utf-8"))
                enriched_profiles = data.get("profiles", [])
        except Exception:
            # Server might not be started yet; load directly from Local State
            all_p = profile_manager.get_all_profiles()
            enriched_profiles = [profile_manager.asdict(p) for p in all_p]

        # Re-render cards
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        for p in enriched_profiles:
            card = ProfileCard(p)
            self.cards_layout.addWidget(card)

        self.cards_layout.addStretch()


def run_gui():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    gui = AccountSwitcherGUI()
    gui.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_gui()
