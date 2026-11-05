"""Offline screenshot OCR. No screenshots or recognition text are persisted."""
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
import json
import sys
import time
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QObject, QRectF, Qt, QThread, QTimer, QSize, Signal, Slot
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QImage, QImageReader, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QListWidget, QListWidgetItem, QPlainTextEdit, QProgressBar, QPushButton, QSizePolicy, QSplitter, QVBoxLayout, QWidget

APP_NAME = "截图识字"


@dataclass
class ImageEntry:
    image: QImage
    name: str
    text: str = ""
    state: str = "等待识别"
    error: str = ""
    elapsed: float = 0.0



def image_bytes(image: QImage) -> bytes:
    # Composite transparent pixels over white before passing to the OCR engine.
    opaque = QImage(image.size(), QImage.Format.Format_RGB32)
    opaque.fill(Qt.GlobalColor.white)
    painter = QPainter(opaque)
    painter.drawImage(0, 0, image)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not opaque.save(buffer, "PNG"):
        raise ValueError("无法读取图片内容")
    return bytes(data)


class OcrWorker(QObject):
    completed = Signal(str, float, str)

    def __init__(self):
        super().__init__()
        self.engine = None

    @Slot(bytes)
    def recognize(self, png: bytes):
        started = time.perf_counter()
        try:
            if self.engine is None:
                from rapidocr_onnxruntime import RapidOCR
                self.engine = RapidOCR(intra_op_num_threads=4, inter_op_num_threads=1)
            result, _ = self.engine(png)
            text = "\n".join(item[1] for item in (result or []))
            self.completed.emit(text, time.perf_counter() - started, "")
        except Exception as exc:
            self.completed.emit("", time.perf_counter() - started, f"{type(exc).__name__}: {exc}")


class ImagePreview(QWidget):
    def __init__(self):
        super().__init__()
        self.image = QImage()
        self.setMinimumSize(220, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#f3f5f8"))
        if self.image.isNull():
            painter.setPen(QColor("#8b96a8"))
            font = painter.font()
            font.setPointSize(12)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "在这里预览截图\n\n粘贴截图，或选择一张图片")
            return
        area = self.rect().adjusted(16, 16, -16, -16)
        fitted = self.image.size().scaled(area.size(), Qt.AspectRatioMode.KeepAspectRatio)
        target = QRectF(area.center().x() - fitted.width() / 2, area.center().y() - fitted.height() / 2, fitted.width(), fitted.height())
        painter.drawImage(target, self.image)


class MainWindow(QMainWindow):
    requested = Signal(bytes)
    recognition_finished = Signal(str)

    def __init__(self):
        super().__init__()
        self.busy = False
        self.entries: list[ImageEntry] = []
        self.pending = deque()
        self.active_index = None
        self.setWindowTitle(APP_NAME)
        self.resize(1260, 740)
        self.setMinimumSize(1000, 540)
        icon_path = Path(__file__).resolve().parent / "assets" / "app.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.thread = QThread(self)
        self.worker = OcrWorker()
        self.worker.moveToThread(self.thread)
        self.requested.connect(self.worker.recognize)
        self.worker.completed.connect(self.on_result)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.start()

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 18)
        layout.setSpacing(18)
        header = QHBoxLayout()
        branding = QVBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        branding.addWidget(title)
        subtitle = QLabel("把截图里的文字，变成可复制的内容。")
        subtitle.setObjectName("muted")
        branding.addWidget(subtitle)
        header.addLayout(branding)
        header.addStretch()
        badge = QLabel("●  本地离线")
        badge.setObjectName("badge")
        badge.setFixedHeight(30)
        header.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(header)

        toolbar = QHBoxLayout()
        self.paste_button = QPushButton("粘贴截图  Ctrl+V")
        self.paste_button.setObjectName("primary")
        self.paste_button.clicked.connect(self.paste_image)
        self.open_button = QPushButton("添加图片（可多选）…")
        self.open_button.clicked.connect(self.open_image)
        toolbar.addWidget(self.paste_button)
        toolbar.addWidget(self.open_button)
        toolbar.addStretch()
        self.copy_button = QPushButton("复制当前图片")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self.copy_text)
        toolbar.addWidget(self.copy_button)
        self.copy_all_button = QPushButton("复制全部文字")
        self.copy_all_button.setEnabled(False)
        self.copy_all_button.clicked.connect(self.copy_all_text)
        toolbar.addWidget(self.copy_all_button)
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(16)
        self.image_list = QListWidget()
        self.image_list.setIconSize(QSize(56, 46))
        self.image_list.setSpacing(4)
        self.image_list.setMinimumWidth(180)
        self.image_list.currentRowChanged.connect(self.select_entry)
        list_panel = QFrame()
        list_panel.setObjectName("panel")
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_title = QLabel("图片列表 · 0 张")
        self.list_title.setObjectName("panelTitle")
        list_layout.addWidget(self.list_title)
        list_layout.addWidget(self.image_list, 1)
        self.clear_button = QPushButton("清空列表")
        self.clear_button.setEnabled(False)
        self.clear_button.clicked.connect(self.clear_entries)
        list_layout.addWidget(self.clear_button)
        splitter.addWidget(list_panel)
        self.preview = ImagePreview()
        self.source_label = QLabel("图片预览")
        self.source_label.setObjectName("panelTitle")
        self.source_label.setToolTip("原始图片尺寸；预览会自动缩放")
        left = QFrame()
        left.setObjectName("panel")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(self.source_label)
        left_layout.addWidget(self.preview, 1)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("识别结果会出现在这里。\n\n点击左侧图片切换结果，可单独复制或复制全部。")
        self.editor.textChanged.connect(self.save_current_text)
        self.editor.setFrameShape(QFrame.Shape.NoFrame)
        right = QFrame()
        right.setObjectName("panel")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        result_label = QLabel("识别结果 · 可编辑")
        result_label.setObjectName("panelTitle")
        right_layout.addWidget(result_label)
        right_layout.addWidget(self.editor, 1)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([230, 460, 460])
        layout.addWidget(splitter, 1)

        footer = QHBoxLayout()
        self.status = QLabel("就绪 · 使用 Win+Shift+S 截图，再点击「粘贴截图」")
        self.status.setObjectName("muted")
        footer.addWidget(self.status, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedSize(100, 5)
        self.progress.hide()
        footer.addWidget(self.progress)
        layout.addLayout(footer)

        action = QAction(self)
        action.setShortcut(QKeySequence("Ctrl+V"))
        action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        action.triggered.connect(self.paste_shortcut)
        self.addAction(action)
        self.setStyleSheet("""
            QMainWindow { background: #f8fafc; }
            QWidget { color: #263449; font-family: 'Microsoft YaHei UI'; font-size: 13px; }
            QLabel#title { font-size: 27px; font-weight: 700; color: #152439; }
            QLabel#muted { color: #748196; font-size: 12px; }
            QLabel#badge { color: #218268; background: #e8f5ef; border-radius: 12px; padding: 6px 11px; font-size: 12px; }
            QPushButton { background: white; border: 1px solid #dce3ec; border-radius: 7px; padding: 10px 17px; font-weight: 600; }
            QPushButton:hover { background: #edf2f9; border-color: #b9c7da; }
            QPushButton:pressed { background: #e0e9f5; }
            QPushButton:disabled { color: #a2aab8; background: #f1f4f8; }
            QPushButton#primary { background: #3267dc; border-color: #3267dc; color: white; }
            QPushButton#primary:hover { background: #2859c5; }
            QPushButton#primary:disabled { background: #91ace5; border-color: #91ace5; }
            QFrame#panel { background: white; border: 1px solid #dfe5ed; border-radius: 8px; }
            QLabel#panelTitle { padding: 13px 15px; font-weight: 600; border-bottom: 1px solid #e9edf3; }
            QPlainTextEdit { background: white; padding: 13px; font-size: 15px; selection-background-color: #c9ddff; }
            QListWidget { background: white; border: none; padding: 6px; outline: none; }
            QListWidget::item { padding: 8px 5px; border-radius: 5px; }
            QListWidget::item:selected { background: #e6efff; color: #214fa8; }
            QListWidget::item:hover:!selected { background: #f3f6fa; }
            QSplitter::handle { background: transparent; width: 18px; }
            QProgressBar { border: none; background: #e5edfa; border-radius: 2px; }
            QProgressBar::chunk { background: #3267dc; }
        """)

    def paste_shortcut(self):
        # In the text editor, keep ordinary text paste; image paste always starts OCR.
        mime = QApplication.clipboard().mimeData()
        if mime.hasImage() or not self.editor.hasFocus():
            self.paste_image()
        elif not self.editor.isReadOnly():
            self.editor.paste()

    def paste_image(self):
        if self.busy:
            return
        image = QApplication.clipboard().image()
        if image.isNull():
            self.status.setText("剪贴板里没有图片 · 请先截图，或点击「选择图片」")
            return
        self.load_image(image)

    def open_image(self):
        if self.busy:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "选择要识别的图片（可多选）", "", "图片 (*.png *.jpg *.jpeg *.bmp *.webp);;所有文件 (*)")
        if paths:
            self.load_files(paths)

    def load_file(self, path: str):
        self.load_files([path])

    def load_files(self, paths):
        if self.busy:
            return
        first_new = len(self.entries)
        for path in paths:
            reader = QImageReader(str(path))
            reader.setAutoTransform(True)
            image = reader.read()
            if image.isNull():
                # Keep failed inputs visible while allowing other images to finish.
                self.append_entry(ImageEntry(QImage(), Path(path).name, state="打开失败", error=reader.errorString()))
            else:
                self.append_entry(ImageEntry(image, Path(path).name))
        if len(self.entries) == first_new:
            return
        self.image_list.setCurrentRow(first_new)
        self.start_next()

    def load_image(self, image: QImage):
        if self.busy or image.isNull():
            return
        index = len(self.entries)
        self.append_entry(ImageEntry(image.copy(), f"粘贴截图 {index + 1}"))
        self.image_list.setCurrentRow(index)
        self.start_next()

    def append_entry(self, entry):
        index = len(self.entries)
        self.entries.append(entry)
        item = QListWidgetItem()
        if not entry.image.isNull():
            item.setIcon(QIcon(QPixmap.fromImage(entry.image).scaled(80, 60, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)))
        self.image_list.addItem(item)
        self.refresh_item(index)
        if not entry.error:
            self.pending.append(index)
        self.list_title.setText(f"图片列表 · {len(self.entries)} 张")

    def refresh_item(self, index):
        entry = self.entries[index]
        item = self.image_list.item(index)
        item.setText(f"{index + 1}. {entry.name}\n{entry.state}")
        item.setToolTip(f"{entry.name}\n{entry.error or entry.state}")
        item.setSizeHint(QSize(180, 66))

    def select_entry(self, index):
        self.editor.blockSignals(True)
        if 0 <= index < len(self.entries):
            entry = self.entries[index]
            self.preview.image = entry.image
            self.editor.setPlainText(entry.text)
            self.editor.setReadOnly(entry.state != "已完成")
            self.source_label.setText(f"图片预览 · 第 {index + 1} 张 · {entry.image.width()} × {entry.image.height()}")
            if entry.error:
                self.editor.setPlaceholderText(f"这张图片未能完成识别。\n\n{entry.error}")
            elif entry.state == "未检测到文字":
                self.editor.setPlaceholderText("这张图片未检测到文字，请尝试更清晰的截图。")
            else:
                self.editor.setPlaceholderText("等待识别结果…" if entry.state != "已完成" else "可在这里修改当前图片的识别文字。")
        else:
            self.preview.image = QImage()
            self.source_label.setText("图片预览")
            self.editor.clear()
            self.editor.setReadOnly(True)
            self.editor.setPlaceholderText("添加多张图片后，点击左侧列表查看每张的结果。")
        self.editor.blockSignals(False)
        self.preview.update()
        self.update_actions()

    def save_current_text(self):
        index = self.image_list.currentRow()
        if 0 <= index < len(self.entries) and self.entries[index].state == "已完成":
            self.entries[index].text = self.editor.toPlainText()
        self.update_actions()

    def update_actions(self):
        index = self.image_list.currentRow()
        self.copy_button.setEnabled(0 <= index < len(self.entries) and bool(self.entries[index].text.strip()))
        self.copy_all_button.setEnabled(not self.busy and any(entry.text.strip() for entry in self.entries))
        self.copy_all_button.setToolTip("等待所有图片识别完成" if self.busy else "按列表顺序复制，以空行分隔每张图片的文字")
        self.clear_button.setEnabled(not self.busy and bool(self.entries))

    def start_next(self):
        if self.pending:
            self.set_busy(True)
            self.active_index = self.pending.popleft()
            entry = self.entries[self.active_index]
            entry.state = "正在识别…"
            self.refresh_item(self.active_index)
            self.status.setText(f"正在识别第 {self.active_index + 1}/{len(self.entries)} 张 · 可切换查看已完成结果")
            try:
                png = image_bytes(entry.image)
            except Exception as exc:
                QTimer.singleShot(0, lambda message=str(exc): self.on_result("", 0, message))
                return
            self.requested.emit(png)
        else:
            self.active_index = None
            self.set_busy(False)
            failed = sum(bool(entry.error) for entry in self.entries)
            empty = sum(entry.state == "未检测到文字" for entry in self.entries)
            self.status.setText(f"识别完成 · 共 {len(self.entries)} 张 · {failed} 张失败 · {empty} 张未检测到文字")
            self.recognition_finished.emit("; ".join(entry.error for entry in self.entries if entry.error))

    def set_busy(self, busy: bool):
        self.busy = busy
        self.paste_button.setEnabled(not busy)
        self.open_button.setEnabled(not busy)
        self.progress.setVisible(busy)
        self.update_actions()

    @Slot(str, float, str)
    def on_result(self, text: str, elapsed: float, error: str):
        if self.active_index is None:
            return
        index = self.active_index
        entry = self.entries[index]
        entry.text, entry.error, entry.elapsed = text, error, elapsed
        entry.state = "识别失败" if error else ("已完成" if text else "未检测到文字")
        self.refresh_item(index)
        if self.image_list.currentRow() == index:
            self.select_entry(index)
        self.active_index = None
        self.start_next()

    def all_text(self):
        return "\n\n".join(entry.text for entry in self.entries if entry.text.strip())

    def copy_text(self):
        index = self.image_list.currentRow()
        if 0 <= index < len(self.entries) and self.entries[index].text.strip():
            QApplication.clipboard().setText(self.entries[index].text)
            self.status.setText(f"已复制第 {index + 1} 张图片的文字")

    def copy_all_text(self):
        text = self.all_text()
        if not self.busy and text.strip():
            QApplication.clipboard().setText(text)
            count = sum(bool(entry.text.strip()) for entry in self.entries)
            self.status.setText(f"已复制全部文字 · {count} 张图片 · 按列表顺序以空行分隔")

    def clear_entries(self):
        if self.busy:
            return
        self.entries.clear()
        self.pending.clear()
        self.image_list.clear()
        self.list_title.setText("图片列表 · 0 张")
        self.select_entry(-1)
        self.status.setText("列表已清空 · 可以添加新的图片")

    def closeEvent(self, event):
        # Never destroy a running inference thread. Close once the current job finishes.
        if self.busy:
            self.status.setText("正在完成识别，请稍候再关闭")
            event.ignore()
            return
        self.thread.quit()
        self.thread.wait()
        event.accept()


def main() -> int:
    parser = argparse.ArgumentParser(description="离线截图文字识别")
    parser.add_argument("images", nargs="*", help="启动时识别的一张或多张图片")
    parser.add_argument("--diagnostic-output", help=argparse.SUPPRESS)
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    window = MainWindow()
    window.show()
    if args.diagnostic_output:
        # Used to verify the frozen executable with its actual bundled models and UI.
        def finished(error):
            output = Path(args.diagnostic_output)
            text = window.editor.toPlainText()
            window.copy_text()
            current_matches = QApplication.clipboard().text() == text
            window.copy_all_text()
            output.write_text(json.dumps({"text": text, "error": error, "items": [{"name": entry.name, "text": entry.text, "state": entry.state, "error": entry.error} for entry in window.entries], "all_text": window.all_text(), "current_clipboard_matches": current_matches, "clipboard_matches": QApplication.clipboard().text() == window.all_text(), "status": window.status.text()}, ensure_ascii=False, indent=2), encoding="utf-8")
            window.grab().save(str(output.with_suffix(".png")))
            window.close()
            app.quit()
        window.recognition_finished.connect(finished)
    if args.images:
        QTimer.singleShot(0, lambda: window.load_files(args.images))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
