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
            self.font = QtGui.QFont("Arial", 14)  # 增大字号
        else:
            self.font = QtGui.QFont()


    def paint(self, painter):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        pen = QtGui.QPen(self.color, 2, QtCore.Qt.DashLine)
        painter.setPen(pen)
        if self.is_translation_box:
            # 翻译框背景黑色
            brush = QtGui.QBrush(QtGui.QColor(0, 0, 0, 150))  # 黑色背景，透明度150
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
        self.init_ui()
        self.init_translator()
        self.translated_text = ""
        self.start_capture_thread()

    def init_ui(self):
        # 获取屏幕分辨率
        screen = QtWidgets.QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        self.screen_width = screen_geometry.width()
        self.screen_height = screen_geometry.height()

        # 设置窗口属性为全屏
        self.setWindowTitle('实时翻译器')
        self.setWindowFlags(
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.FramelessWindowHint
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setWindowOpacity(0.3)  # 设置透明度，可根据需要调整
        self.setGeometry(0, 0, self.screen_width, self.screen_height)  # 设置为全屏

        # 创建两个独立的方框
        # 选择框：绿色
        selection_rect = QtCore.QRect(100, 100, 300, 200)
        self.selection_box = DraggableResizableBox(self, selection_rect, (0, 255, 0), is_translation_box=False)

        # 翻译结果框：黑色
        translation_rect = QtCore.QRect(420, 100, 300, 200)
        self.translation_box = DraggableResizableBox(self, translation_rect, (0, 0, 0), is_translation_box=True)

        # 快捷键：Ctrl+T 显示/隐藏窗口
        shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+T"), self)
        shortcut.activated.connect(self.toggle_visibility)

        # 确保窗口可以接受鼠标事件
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)

    def init_translator(self):
        # 初始化翻译器
        self.translator = Translator()
        self.running = True  # 控制捕获线程

        # 如果Tesseract未添加到系统环境变量中，请手动指定路径
        # pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

    def toggle_visibility(self):
        # 切换窗口的可见性
        self.setVisible(not self.isVisible())

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        self.selection_box.paint(painter)
        self.translation_box.paint(painter)

    def mousePressEvent(self, event):
        pos = event.pos()
        # 先检查翻译框
        if self.translation_box.contains_point(pos):
            self.translation_box.mouse_press_event(event)
        # 再检查选择框
        elif self.selection_box.contains_point(pos):
            self.selection_box.mouse_press_event(event)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # 优先处理翻译框的移动
        if self.translation_box.dragging or self.translation_box.resizing:
            if self.translation_box.mouse_move_event(event):
                self.update()
                return
        # 其次处理选择框的移动
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
                    text = pytesseract.image_to_string(img, lang='eng')  # 使用english识别
                    print(f"OCR识别文本: {text}")  # 调试用
                    if text.strip():
                        # 自动检测源语言，并翻译为英文
                        translated = self.translator.translate(text, src='en', dest='zh-cn').text  # dest根据需要修改
                        print(f"翻译结果: {translated}")  # 调试用
                        # 在主线程中更新翻译框
                        QtCore.QMetaObject.invokeMethod(
                            self,
                            "update_translation",
                            QtCore.Qt.QueuedConnection,
                            QtCore.Q_ARG(str, translated)
                        )
                except Exception as e:
                    print(f"捕获或翻译错误: {e}")
                time.sleep(0.5)  # 每秒更新一次，可根据需要调整

    @QtCore.pyqtSlot(str)
    def update_translation(self, translated_text):
        # 更新翻译结果框的文本
        self.translated_text = translated_text
        self.translation_box.parent.translated_text = translated_text
        self.update()

    def start_capture_thread(self):
        # 启动捕获和翻译的线程
        self.capture_thread = threading.Thread(target=self.capture_and_translate, daemon=True)
        self.capture_thread.start()

    def closeEvent(self, event):
        # 关闭窗口时停止线程
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
