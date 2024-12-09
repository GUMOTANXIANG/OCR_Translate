import sys
import threading
import time

from PyQt5 import QtCore, QtGui, QtWidgets
from googletrans import Translator
import mss
from PIL import Image
import pytesseract


class DraggableResizableBox:
    """
    一个可拖动和可调整大小的方框类
    """
    def __init__(self, parent, initial_rect, color, is_translation_box=False):
        self.parent = parent
        self.rect = initial_rect  # QRect
        self.color = QtGui.QColor(*color)  # 将 RGB 元组转换为 QColor 对象
        self.is_translation_box = is_translation_box

        # 交互状态
        self.dragging = False
        self.resizing = False
        self.resize_margin = 10
        self.drag_start = QtCore.QPoint()

        # 设置字体样式
        if self.is_translation_box:
            self.font = QtGui.QFont("Arial", 20)  # 增大字号
        else:
            self.font = QtGui.QFont()

    def paint(self, painter):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        pen = QtGui.QPen(self.color, 2, QtCore.Qt.DashLine)
        painter.setPen(pen)
        if self.is_translation_box:
            # 翻译框背景黑色
            brush = QtGui.QBrush(QtGui.QColor(0, 0, 0))  # 黑色背景，透明度150
        else:
            # 选择框背景绿色
            brush = QtGui.QBrush(QtGui.QColor(self.color.red(), self.color.green(), self.color.blue(), 50))
        painter.setBrush(brush)
        painter.drawRect(self.rect)

        if self.is_translation_box and self.parent.translated_text:
            painter.setFont(self.font)
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255)))  # 白色文字
            text_rect = self.rect.adjusted(10, 10, -10, -10)  # 增加内边距
            painter.drawText(text_rect, QtCore.Qt.TextWordWrap, self.parent.translated_text)

    def mouse_press_event(self, event):
        if self.rect.contains(event.pos()):
            # 检查是否在调整大小区域
            if (abs(event.x() - self.rect.right()) < self.resize_margin and
                abs(event.y() - self.rect.bottom()) < self.resize_margin):
                self.resizing = True
            else:
                self.dragging = True
            self.drag_start = event.pos()
            # 阻止事件进一步传播
            event.accept()
        else:
            event.ignore()

    def mouse_move_event(self, event):
        if self.dragging:
            delta = event.pos() - self.drag_start
            new_x = self.rect.x() + delta.x()
            new_y = self.rect.y() + delta.y()

            # 确保方框不会移出屏幕
            new_x = max(0, min(new_x, self.parent.screen_width - self.rect.width()))
            new_y = max(0, min(new_y, self.parent.screen_height - self.rect.height()))

            self.rect.moveTo(new_x, new_y)
            self.drag_start = event.pos()
            return True
        elif self.resizing:
            delta = event.pos() - self.drag_start
            new_width = max(self.rect.width() + delta.x(), 100)
            new_height = max(self.rect.height() + delta.y(), 50)

            # 确保方框不会超出屏幕范围
            new_width = min(new_width, self.parent.screen_width - self.rect.x())
            new_height = min(new_height, self.parent.screen_height - self.rect.y())

            self.rect.setWidth(new_width)
            self.rect.setHeight(new_height)
            self.drag_start = event.pos()
            return True
        return False

    def mouse_release_event(self, event):
        self.dragging = False
        self.resizing = False

    def contains_point(self, pos):
        return self.rect.contains(pos)


class Overlay(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.translated_text = ""
        self.init_ui()
        self.init_translator()
        self.start_capture_thread()

    def init_ui(self):
        # 获取屏幕分辨率
        screen = QtWidgets.QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        self.screen_width = screen_geometry.width()
        self.screen_height = screen_geometry.height()

        self.setWindowTitle('实时翻译器')
        self.setWindowFlags(
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.FramelessWindowHint
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setWindowOpacity(0.3)
        self.setGeometry(0, 0, self.screen_width, self.screen_height)

        # 使用QSettings存储和读取方框位置和大小
        self.settings = QtCore.QSettings("MyCompany", "MyTranslatorApp")

        # 默认方框位置
        default_selection_rect = QtCore.QRect(100, 100, 300, 200)
        default_translation_rect = QtCore.QRect(420, 100, 300, 200)

        # 尝试从QSettings中读取方框信息
        selection_data = self.settings.value("selection_box_geometry", None)
        if selection_data is not None:
            # QSettings返回的是QVariant，如果存储的是列表或字符串，需要解析
            # 假设之前保存为字符串 "left,top,width,height"
            left, top, width, height = map(int, selection_data.split(","))
            selection_rect = QtCore.QRect(left, top, width, height)
        else:
            selection_rect = default_selection_rect

        translation_data = self.settings.value("translation_box_geometry", None)
        if translation_data is not None:
            left, top, width, height = map(int, translation_data.split(","))
            translation_rect = QtCore.QRect(left, top, width, height)
        else:
            translation_rect = default_translation_rect

        # 创建方框
        self.selection_box = DraggableResizableBox(self, selection_rect, (0, 255, 0), is_translation_box=False)
        self.translation_box = DraggableResizableBox(self, translation_rect, (0, 0, 0), is_translation_box=True)

        # 快捷键：Ctrl+T 显示/隐藏窗口
        shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+T"), self)
        shortcut.activated.connect(self.toggle_visibility)

        # 确保窗口可以接受鼠标事件
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)

    def init_translator(self):
        self.translator = Translator()
        self.running = True

        # 如果需要手动指定Tesseract路径，请在此处解除注释并修改路径
        # pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

    def toggle_visibility(self):
        self.setVisible(not self.isVisible())

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        self.selection_box.paint(painter)
        self.translation_box.paint(painter)

    def mousePressEvent(self, event):
        pos = event.pos()
        if self.translation_box.contains_point(pos):
            self.translation_box.mouse_press_event(event)
        elif self.selection_box.contains_point(pos):
            self.selection_box.mouse_press_event(event)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.translation_box.dragging or self.translation_box.resizing:
            if self.translation_box.mouse_move_event(event):
                self.update()
                return
        if self.selection_box.dragging or self.selection_box.resizing:
            if self.selection_box.mouse_move_event(event):
                self.update()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.selection_box.mouse_release_event(event)
        self.translation_box.mouse_release_event(event)
        super().mouseReleaseEvent(event)

    def capture_and_translate(self):
        # 捕获选择框区域的屏幕内容，进行OCR识别和翻译
        with mss.mss() as sct:
            while self.running:
                monitor = {
                    "top": self.selection_box.rect.top(),
                    "left": self.selection_box.rect.left(),
                    "width": self.selection_box.rect.width(),
                    "height": self.selection_box.rect.height()
                }
                try:
                    sct_img = sct.grab(monitor)
                    img = Image.frombytes('RGB', sct_img.size, sct_img.rgb)
                    text = pytesseract.image_to_string(img, lang='eng')  # 使用英文识别
                    print(f"OCR识别文本: {text}")
                    if text.strip():
                        # 将英文翻译为中文
                        translated = self.translator.translate(text, src='en', dest='zh-cn').text
                        print(f"翻译结果: {translated}")
                        # 在主线程中更新翻译框
                        QtCore.QMetaObject.invokeMethod(
                            self,
                            "update_translation",
                            QtCore.Qt.QueuedConnection,
                            QtCore.Q_ARG(str, translated)
                        )
                except Exception as e:
                    print(f"捕获或翻译错误: {e}")
                time.sleep(0.2)  # 调整翻译频率

    @QtCore.pyqtSlot(str)
    def update_translation(self, translated_text):
        self.translated_text = translated_text
        self.translation_box.parent.translated_text = translated_text
        self.update()

    def start_capture_thread(self):
        self.capture_thread = threading.Thread(target=self.capture_and_translate, daemon=True)
        self.capture_thread.start()

    def closeEvent(self, event):
        # 在关闭窗口时保存当前方框的位置和大小
        selection_box_geo = f"{self.selection_box.rect.left()},{self.selection_box.rect.top()},{self.selection_box.rect.width()},{self.selection_box.rect.height()}"
        translation_box_geo = f"{self.translation_box.rect.left()},{self.translation_box.rect.top()},{self.translation_box.rect.width()},{self.translation_box.rect.height()}"

        self.settings.setValue("selection_box_geometry", selection_box_geo)
        self.settings.setValue("translation_box_geometry", translation_box_geo)

        self.running = False
        self.capture_thread.join()
        super().closeEvent(event)


def main():
    app = QtWidgets.QApplication(sys.argv)
    overlay = Overlay()
    overlay.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
