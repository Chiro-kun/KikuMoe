"""Cyber-Moe OTA Update Dialog for KikuMoe.

Displays available updates, release notes / changelog with Markdown formatting,
release channel badge (Stable / Beta), and in-place download progress.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core.constants import (
    APP_SETTINGS,
    APP_VERSION,
    KEY_UPDATE_IGNORED_VERSION,
    ORG_NAME,
)
from core.i18n import I18n
from core.updater import AssetDownloadWorker, ReleaseAsset, ReleaseInfo
from ui.custom_titlebar import CustomTitleBar, install_size_grip
from ui.dialog_animations import CyberMoeDialogAnimationMixin
from ui.themes.cyber_moe import PALETTE, get_cyber_moe_stylesheet
from ui.vector_icons import (
    get_download_icon,
    get_update_pixmap,
    get_window_icon,
)
from ui.windows_titlebar import apply_windows_titlebar_dark_mode

_IS_WIN32 = sys.platform == "win32"


class UpdateDialog(CyberMoeDialogAnimationMixin, QDialog):
    """Frameless Cyber-Glass modal dialog presenting an available update."""

    def __init__(
        self,
        release: ReleaseInfo,
        parent: QWidget | None = None,
        i18n: I18n | None = None,
    ) -> None:
        super().__init__(parent)
        self.release = release
        self.settings = QSettings(ORG_NAME, APP_SETTINGS)
        self.i18n = i18n or I18n("it")
        self._download_worker: AssetDownloadWorker | None = None
        self._downloaded_file_path: str | None = None
        self._target_asset: ReleaseAsset | None = release.get_platform_asset()

        self.setObjectName("updateDialogRoot")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(480, 480)
        self.resize(520, 560)

        app_icon = getattr(parent, "_icon_app", None) if parent is not None else None
        self._title_bar = CustomTitleBar(self, icon=app_icon)
        self._title_bar._btn_min.setVisible(False)
        self._title_bar._btn_max.setVisible(False)
        self._title_bar._ver_badge.setText(self.i18n.t("updates_title").upper())

        self._init_ui()
        install_size_grip(self)
        apply_windows_titlebar_dark_mode(self, True)

    def _init_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.addWidget(self._title_bar)

        # Main glass frame
        self._content_frame = QFrame(self)
        self._content_frame.setObjectName("updateContentFrame")
        accent = PALETTE.get("accent", "#EC186C")
        bg_card = PALETTE.get("bg_surface_card", "#151726")
        border = PALETTE.get("border_card", "rgba(255, 255, 255, 0.08)")
        text_primary = PALETTE.get("text_primary", "#FFFFFF")
        text_sec = PALETTE.get("text_secondary", "#94A3B8")

        self.setStyleSheet(
            f"{get_cyber_moe_stylesheet()}\n"
            f"QFrame#updateContentFrame {{"
            f"  background: {PALETTE.get('bg_surface_elevated', '#121420')};"
            f"  border: 1px solid {border};"
            f"  border-top: none;"
            f"  border-bottom-left-radius: 12px;"
            f"  border-bottom-right-radius: 12px;"
            f"}}"
            f"QTextBrowser#changelogBrowser {{"
            f"  background: {bg_card};"
            f"  color: {text_primary};"
            f"  border: 1px solid {border};"
            f"  border-radius: 8px;"
            f"  padding: 12px;"
            f"  font-family: 'Segoe UI', 'Cascadia Code', sans-serif;"
            f"  font-size: 12px;"
            f"  line-height: 1.5;"
            f"}}"
            f"QProgressBar#downloadProgress {{"
            f"  border: 1px solid {border};"
            f"  border-radius: 5px;"
            f"  text-align: center;"
            f"  background: rgba(0, 0, 0, 0.3);"
            f"  color: #FFFFFF;"
            f"  font-weight: 600;"
            f"  font-size: 11px;"
            f"  height: 10px;"
            f"}}"
            f"QProgressBar#downloadProgress::chunk {{"
            f"  background: {accent};"
            f"  border-radius: 4px;"
            f"}}"
        )

        content_layout = QVBoxLayout(self._content_frame)
        content_layout.setContentsMargins(20, 16, 20, 18)
        content_layout.setSpacing(12)

        # Header card: Version & Channel Badge
        header_card = QFrame()
        header_card.setStyleSheet(
            f"background: {bg_card}; border: 1px solid {border}; "
            "border-radius: 10px; padding: 10px;"
        )
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(10, 6, 10, 6)
        h_layout.setSpacing(12)

        # Rocket / Update icon badge
        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_update_pixmap(28, accent))
        h_layout.addWidget(icon_lbl)

        # Version details
        v_box = QVBoxLayout()
        v_box.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        ver_lbl = QLabel(f"KikuMoe {self.release.tag_name}")
        ver_lbl.setStyleSheet(f"color: {text_primary}; font-size: 16px; font-weight: 700;")
        title_row.addWidget(ver_lbl)

        # Channel Badge (BETA / STABLE)
        badge_lbl = QLabel()
        if self.release.is_prerelease:
            badge_text = self.i18n.t("updates_badge_beta")
            badge_lbl.setText(badge_text)
            badge_lbl.setStyleSheet(
                "background: rgba(245, 158, 11, 0.18); color: #F59E0B; "
                "border: 1px solid rgba(245, 158, 11, 0.4); border-radius: 4px; "
                "font-size: 10px; font-weight: 800; padding: 2px 7px;"
            )
        else:
            badge_text = self.i18n.t("updates_badge_stable")
            badge_lbl.setText(badge_text)
            badge_lbl.setStyleSheet(
                "background: rgba(16, 185, 129, 0.18); color: #10B981; "
                "border: 1px solid rgba(16, 185, 129, 0.4); border-radius: 4px; "
                "font-size: 10px; font-weight: 800; padding: 2px 7px;"
            )
        title_row.addWidget(badge_lbl)
        title_row.addStretch(1)
        v_box.addLayout(title_row)

        sub_msg = (
            f"{self.i18n.t('updates_current_version', version=APP_VERSION)}"
            f" ➔ {self.release.tag_name}"
        )
        sub_lbl = QLabel(sub_msg)
        sub_lbl.setStyleSheet(f"color: {text_sec}; font-size: 11px;")
        v_box.addWidget(sub_lbl)
        h_layout.addLayout(v_box, 1)

        content_layout.addWidget(header_card)

        # Changelog / Release notes text browser (Markdown)
        notes_label = QLabel("Note di rilascio:")
        notes_label.setStyleSheet(
            f"color: {text_sec}; font-size: 11px; font-weight: 600; text-transform: uppercase;"
        )
        content_layout.addWidget(notes_label)

        self.changelog_browser = QTextBrowser()
        self.changelog_browser.setObjectName("changelogBrowser")
        self.changelog_browser.setOpenExternalLinks(True)
        # Set markdown text
        body_text = (
            self.release.body.strip()
            if self.release.body
            else "Nessuna nota di rilascio dettagliata disponibile."
        )
        self.changelog_browser.setMarkdown(body_text)
        content_layout.addWidget(self.changelog_browser, 1)

        # Asset info & Download progress row
        self.asset_info_lbl = QLabel()
        if self._target_asset:
            self.asset_info_lbl.setText(
                f"Pacchetto: {self._target_asset.name} ({self._target_asset.size_mb} MB)"
            )
        else:
            self.asset_info_lbl.setText("Disponibile su GitHub Releases")
        self.asset_info_lbl.setStyleSheet(f"color: {text_sec}; font-size: 11px;")
        content_layout.addWidget(self.asset_info_lbl)

        # Progress bar (initially hidden)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("downloadProgress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        content_layout.addWidget(self.progress_bar)

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet(f"color: {accent}; font-size: 11px; font-weight: 600;")
        self.status_lbl.setVisible(False)
        content_layout.addWidget(self.status_lbl)

        # Checkbox ignore version
        self.cb_ignore = QCheckBox(self.i18n.t("updates_ignore_version"))
        self.cb_ignore.setStyleSheet(f"color: {text_sec}; font-size: 11px;")
        content_layout.addWidget(self.cb_ignore)

        # Bottom Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_github = QPushButton(self.i18n.t("updates_view_github"))
        self.btn_github.setIcon(get_window_icon(14))
        self.btn_github.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_github.setStyleSheet(
            f"QPushButton {{ background: {bg_card}; color: {text_primary}; "
            f"border: 1px solid {border}; border-radius: 6px; padding: 7px 14px; "
            "font-size: 12px; }"
            f"QPushButton:hover {{ border-color: {accent}; }}"
        )
        self.btn_github.clicked.connect(self._open_github_release)
        btn_layout.addWidget(self.btn_github)

        btn_layout.addStretch(1)

        self.btn_later = QPushButton(self.i18n.t("updates_remind_later"))
        self.btn_later.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_later.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {text_sec}; "
            f"border: 1px solid transparent; border-radius: 6px; padding: 7px 14px; "
            "font-size: 12px; }}"
            f"QPushButton:hover {{ color: {text_primary}; }}"
        )
        self.btn_later.clicked.connect(self.close)
        btn_layout.addWidget(self.btn_later)

        self.btn_action = QPushButton(self.i18n.t("updates_download"))
        self.btn_action.setIcon(get_download_icon(14, "#FFFFFF"))
        self.btn_action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_action.setStyleSheet(
            f"QPushButton {{ background: {accent}; color: #FFFFFF; font-weight: 700; "
            f"border: none; border-radius: 6px; padding: 7px 18px; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {PALETTE.get('accent_hover', '#FF2A7A')}; }}"
        )
        self.btn_action.clicked.connect(self._on_action_clicked)
        btn_layout.addWidget(self.btn_action)

        content_layout.addLayout(btn_layout)
        outer_layout.addWidget(self._content_frame)

    def _open_github_release(self) -> None:
        """Open release URL in user's default web browser."""
        url = (
            self.release.html_url
            or f"https://github.com/Chiro-kun/KikuMoe/releases/tag/{self.release.tag_name}"
        )
        QDesktopServices.openUrl(QUrl(url))

    def _on_action_clicked(self) -> None:
        """Handle download or post-download action."""
        if self._downloaded_file_path:
            # If already downloaded, open folder or launch
            path = Path(self._downloaded_file_path)
            if _IS_WIN32 and path.suffix.lower() == ".exe":
                try:
                    startfile = getattr(os, "startfile", None)
                    if callable(startfile):
                        startfile(str(path))
                        self.close()
                        return
                except Exception:
                    pass
            # Open containing directory
            if _IS_WIN32:
                subprocess.Popen(["explorer", "/select,", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path.parent)])
            self.close()
            return

        if not self._target_asset:
            self._open_github_release()
            return

        # Start in-app download
        self.progress_bar.setVisible(True)
        self.status_lbl.setVisible(True)
        self.btn_action.setEnabled(False)
        self.btn_action.setText(self.i18n.t("updates_downloading", pct=0))

        self._download_worker = AssetDownloadWorker(self._target_asset, parent=self)
        self._download_worker.progress.connect(self._on_download_progress)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.error.connect(self._on_download_error)
        self._download_worker.start()

    def _on_download_progress(self, downloaded: int, total: int) -> None:
        if total > 0:
            pct = int((downloaded / total) * 100)
            self.progress_bar.setValue(pct)
            dl_mb = round(downloaded / (1024 * 1024), 1)
            tot_mb = round(total / (1024 * 1024), 1)
            self.status_lbl.setText(f"{dl_mb} MB / {tot_mb} MB ({pct}%)")
            self.btn_action.setText(self.i18n.t("updates_downloading", pct=pct))

    def _on_download_finished(self, saved_path: str) -> None:
        self._downloaded_file_path = saved_path
        self.progress_bar.setValue(100)
        self.status_lbl.setText(self.i18n.t("updates_download_complete"))
        self.status_lbl.setStyleSheet("color: #10B981; font-size: 11px; font-weight: 700;")
        self.btn_action.setEnabled(True)
        if _IS_WIN32 and saved_path.lower().endswith(".exe"):
            self.btn_action.setText("Avvia Installer")
        else:
            self.btn_action.setText(self.i18n.t("updates_open_folder"))

    def _on_download_error(self, err_msg: str) -> None:
        self.progress_bar.setVisible(False)
        self.status_lbl.setText(f"Errore download: {err_msg}")
        self.status_lbl.setStyleSheet("color: #EF4444; font-size: 11px; font-weight: 600;")
        self.btn_action.setEnabled(True)
        self.btn_action.setText(self.i18n.t("updates_download"))

    def closeEvent(self, event) -> None:
        if (
            getattr(self, "_is_closing", False)
            or os.environ.get("QT_QPA_PLATFORM") == "offscreen"
            or not self.isVisible()
        ):
            self._stop_dialog_animations()
            if self._download_worker and self._download_worker.isRunning():
                self._download_worker.cancel()
            if hasattr(self, "cb_ignore") and self.cb_ignore.isChecked():
                self.settings.setValue(KEY_UPDATE_IGNORED_VERSION, self.release.tag_name)
            if event:
                event.accept()
            super().closeEvent(event)
            return
        if event:
            event.ignore()
        self._animate_dialog_exit(super().close)
