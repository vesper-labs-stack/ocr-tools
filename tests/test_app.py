"""Exercise actual Qt input, background inference, clipboard, and shutdown."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication
from app import MainWindow, image_bytes


class AppIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from generate_sample import generate
        generate()
        generate('qa-output/second-sample.png', second=True)

    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def wait_for_ocr(self, start, expect_error=False):
        loop = QEventLoop()
        errors = []
        def finished(error):
            errors.append(error)
            loop.quit()
        self.window.recognition_finished.connect(finished)
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        timeout.start(30000)
        start()
        if not errors:
            loop.exec()
        timeout.stop()
        self.window.recognition_finished.disconnect(finished)
        self.assertTrue(errors, 'OCR did not finish within 30 seconds')
        self.assertEqual(bool(errors[-1]), expect_error)

    def test_clipboard_image_ocr_and_edit_copy(self):
        sample = QImage('qa-output/screenshot-sample.png')
        self.assertFalse(sample.isNull())
        self.app.clipboard().setImage(sample)
        self.wait_for_ocr(self.window.paste_image)
        text = self.window.editor.toPlainText()
        for expected in ('本地截图文字识别', 'Hello', '12345', '2026', '128.50'):
            self.assertIn(expected, text)
        self.assertFalse(self.window.busy)
        self.assertTrue(self.window.copy_button.isEnabled())
        self.window.editor.setPlainText(text + '\n人工校正')
        self.window.copy_text()
        self.assertTrue(self.app.clipboard().text().endswith('人工校正'))

    def test_blank_image_returns_empty_and_keeps_copy_disabled(self):
        image = QImage(500, 300, QImage.Format.Format_RGB32)
        image.fill(QColor('white'))
        self.wait_for_ocr(lambda: self.window.load_image(image))
        self.assertEqual(self.window.editor.toPlainText(), '')
        self.assertIn('未检测到文字', self.window.status.text())
        self.assertFalse(self.window.copy_button.isEnabled())

    def test_text_clipboard_does_not_clear_existing_result(self):
        self.window.editor.setPlainText('已有结果')
        self.app.clipboard().setText('普通文本')
        self.window.paste_image()
        self.assertEqual(self.window.editor.toPlainText(), '已有结果')
        self.assertIn('没有图片', self.window.status.text())

    def test_invalid_file_is_recoverable(self):
        self.wait_for_ocr(lambda: self.window.load_file('qa-output/missing.png'), expect_error=True)
        self.assertEqual(self.window.entries[0].state, '打开失败')
        self.assertFalse(self.window.busy)
        self.assertFalse(self.window.copy_button.isEnabled())
        self.assertIn('1 张失败', self.window.status.text())

    def test_multi_file_picker_switch_edit_and_copy_all(self):
        # The first result remains editable while the second image is processing.
        edited = []
        edit_timer = QTimer()
        def edit_first_while_second_runs():
            if self.window.active_index == 1:
                self.window.image_list.setCurrentRow(0)
                self.window.editor.setPlainText('第一张已校正 ABC')
                self.assertTrue(self.window.copy_button.isEnabled())
                self.assertFalse(self.window.copy_all_button.isEnabled())
                edited.append(True)
                edit_timer.stop()
        edit_timer.timeout.connect(edit_first_while_second_runs)
        edit_timer.start(1)
        paths = ['qa-output/screenshot-sample.png', 'qa-output/second-sample.png']
        with patch('app.QFileDialog.getOpenFileNames', return_value=(paths, '')) as picker:
            self.wait_for_ocr(self.window.open_image)
            picker.assert_called_once()
        edit_timer.stop()
        self.assertTrue(edited)
        self.assertEqual(self.window.image_list.count(), 2)
        self.assertEqual(self.window.editor.toPlainText(), '第一张已校正 ABC')
        self.window.copy_text()
        self.assertEqual(self.app.clipboard().text(), '第一张已校正 ABC')
        self.window.image_list.setCurrentRow(1)
        second = self.window.editor.toPlainText()
        self.assertIn('67890', second)
        self.window.copy_text()
        self.assertEqual(self.app.clipboard().text(), second)
        self.window.image_list.setCurrentRow(0)
        self.assertEqual(self.window.editor.toPlainText(), '第一张已校正 ABC')
        self.window.copy_all_text()
        self.assertEqual(self.app.clipboard().text(), '第一张已校正 ABC\n\n' + second)

    def test_mixed_batch_keeps_valid_results_and_skips_empty_copy(self):
        blank = QImage(300, 200, QImage.Format.Format_RGB32)
        blank.fill(QColor('white'))
        blank.save('qa-output/blank.png')
        self.wait_for_ocr(lambda: self.window.load_files(['qa-output/missing.png', 'qa-output/blank.png', 'qa-output/screenshot-sample.png']), expect_error=True)
        self.assertEqual([entry.state for entry in self.window.entries], ['打开失败', '未检测到文字', '已完成'])
        self.assertFalse(self.window.copy_button.isEnabled())
        self.assertTrue(self.window.copy_all_button.isEnabled())
        self.window.copy_all_text()
        self.assertEqual(self.app.clipboard().text(), self.window.entries[2].text)

    def test_paste_appends_then_clear_resets_everything(self):
        self.wait_for_ocr(lambda: self.window.load_file('qa-output/screenshot-sample.png'))
        original = self.window.entries[0].text
        self.app.clipboard().setImage(QImage('qa-output/second-sample.png'))
        self.wait_for_ocr(self.window.paste_image)
        self.assertEqual(len(self.window.entries), 2)
        self.assertEqual(self.window.entries[0].text, original)
        self.assertIn('67890', self.window.entries[1].text)
        self.window.editor.setPlainText('')
        self.window.copy_all_text()
        self.assertEqual(self.app.clipboard().text(), original)
        self.window.clear_entries()
        self.assertEqual(self.window.entries, [])
        self.assertEqual(self.window.image_list.count(), 0)
        self.assertEqual(self.window.editor.toPlainText(), '')
        self.assertFalse(self.window.copy_button.isEnabled())
        self.assertFalse(self.window.copy_all_button.isEnabled())
        self.assertFalse(self.window.clear_button.isEnabled())

    def test_transparent_background_is_white(self):
        image = QImage(50, 50, QImage.Format.Format_ARGB32)
        image.fill(QColor(0, 0, 0, 0))
        result = QImage.fromData(image_bytes(image))
        self.assertEqual(result.pixelColor(20, 20), QColor('white'))

    def test_busy_window_cannot_destroy_running_worker(self):
        self.window.set_busy(True)
        self.window.show()
        self.assertFalse(self.window.close())
        self.assertTrue(self.window.thread.isRunning())
        self.assertFalse(self.window.open_button.isEnabled())
        self.window.set_busy(False)


if __name__ == '__main__':
    unittest.main()
