from PySide6.QtCore import QThread, Signal


class Worker(QThread):
    result = Signal(object)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        # Use QThread's built-in finished signal for lifecycle cleanup.
        self.finished.connect(self.deleteLater)

    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
            self.result.emit(result)
        except Exception as e:
            self.error.emit(str(e))
