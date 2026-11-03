"""Cyber-Moe dialog animation helper for KikuMoe.

Provides smooth 60 FPS drop-in entrance and fade-out exit animations for frameless QDialogs.
"""

from __future__ import annotations

import os
from typing import Any, Callable

from PyQt6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
)
from PyQt6.QtGui import QCloseEvent, QShowEvent
from PyQt6.QtWidgets import QDialog


class CyberMoeDialogAnimationMixin:
    """Mixin for frameless QDialog instances providing fluid entrance/exit animations."""

    _entrance_animated: bool = False
    _is_closing: bool = False
    _anim_group: QParallelAnimationGroup | None = None

    def _stop_dialog_animations(self) -> None:
        if self._anim_group is not None:
            try:
                if self._anim_group.state() == QParallelAnimationGroup.State.Running:
                    self._anim_group.stop()
            except RuntimeError:
                pass
            self._anim_group = None

    def _animate_dialog_entrance(self) -> None:
        if getattr(self, "_entrance_animated", False):
            return
        self._entrance_animated = True

        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            if isinstance(self, QDialog):
                self.setWindowOpacity(1.0)
            return

        if not isinstance(self, QDialog):
            return

        target_pos = self.pos()
        start_pos = QPoint(target_pos.x(), target_pos.y() - 10)

        self._stop_dialog_animations()
        self.setWindowOpacity(0.0)
        self.move(start_pos)

        group = QParallelAnimationGroup(self)

        anim_pos = QPropertyAnimation(self, b"pos", group)
        anim_pos.setDuration(190)
        anim_pos.setStartValue(start_pos)
        anim_pos.setEndValue(target_pos)
        anim_pos.setEasingCurve(QEasingCurve.Type.OutCubic)

        anim_op = QPropertyAnimation(self, b"windowOpacity", group)
        anim_op.setDuration(180)
        anim_op.setStartValue(0.0)
        anim_op.setEndValue(1.0)
        anim_op.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _on_finish() -> None:
            if isinstance(self, QDialog):
                self.setWindowOpacity(1.0)
                self.move(target_pos)

        group.finished.connect(_on_finish)
        self._anim_group = group
        group.start()

    def _animate_dialog_exit(self, callback: Callable[[], Any]) -> None:
        if getattr(self, "_is_closing", False):
            return
        self._is_closing = True

        self._stop_dialog_animations()

        if (
            not isinstance(self, QDialog)
            or not self.isVisible()
            or os.environ.get("QT_QPA_PLATFORM") == "offscreen"
        ):
            self._entrance_animated = False
            self._is_closing = False
            if isinstance(self, QDialog):
                self.setWindowOpacity(1.0)
                self.hide()
            callback()
            return

        group = QParallelAnimationGroup(self)

        anim_pos = QPropertyAnimation(self, b"pos", group)
        anim_pos.setDuration(120)
        anim_pos.setStartValue(self.pos())
        anim_pos.setEndValue(QPoint(self.x(), self.y() - 8))
        anim_pos.setEasingCurve(QEasingCurve.Type.InCubic)

        anim_op = QPropertyAnimation(self, b"windowOpacity", group)
        anim_op.setDuration(120)
        anim_op.setStartValue(self.windowOpacity())
        anim_op.setEndValue(0.0)
        anim_op.setEasingCurve(QEasingCurve.Type.InCubic)

        def _finish() -> None:
            self._entrance_animated = False
            self._is_closing = False
            if isinstance(self, QDialog):
                self.setWindowOpacity(1.0)
                self.hide()
            callback()

        group.finished.connect(_finish)
        self._anim_group = group
        group.start()

    def showEvent(self, a0: QShowEvent | None) -> None:
        super().showEvent(a0)  # type: ignore[misc]
        self._stop_dialog_animations()
        self._is_closing = False
        self._entrance_animated = False
        self._animate_dialog_entrance()

    def closeEvent(self, a0: QCloseEvent | None) -> None:
        if (
            getattr(self, "_is_closing", False)
            or os.environ.get("QT_QPA_PLATFORM") == "offscreen"
            or not (isinstance(self, QDialog) and self.isVisible())
        ):
            self._stop_dialog_animations()
            if a0:
                a0.accept()
            super().closeEvent(a0)  # type: ignore[misc]
            return
        if a0:
            a0.ignore()
        self._animate_dialog_exit(super().reject)  # type: ignore[misc]

    def accept(self) -> None:
        self._animate_dialog_exit(super().accept)  # type: ignore[misc]

    def reject(self) -> None:
        self._animate_dialog_exit(super().reject)  # type: ignore[misc]
