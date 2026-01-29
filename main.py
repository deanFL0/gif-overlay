from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QVBoxLayout,
    QWidget,
    QLabel,
    QScrollArea,
    QPushButton,
    QFrame,
    QFileDialog,
    QMessageBox,
)
from PySide6.QtGui import QPixmap, QMovie, QPainter, QColor, QBrush, QCursor
from PySide6.QtCore import Qt, Signal, QTimer, QSize, QRect
import os
import sys
import json

class GifWorker(QtCore.QThread):
    """Worker thread to handle GIF playback."""
    frameReady = Signal(QPixmap)
    error = Signal(str)
    
    def __init__(self, gif_path: str):
        super().__init__()
        self.gif_path = gif_path
        self._stopped = False
        self.movie = None
        
    def run(self):
        """Start decoding the GIF"""
        self.movie = QMovie(self.gif_path)
        self.movie.setCacheMode(QMovie.CacheAll)
        if not self.movie.isValid():
            self.error.emit("Invalid or unsupported GIF file.")
            return
        
        self.movie.frameChanged.connect(self._on_frame_changed)
        self.movie.start()
        
        # Event loop to keep the thread alive
        self.loop = QtCore.QEventLoop()
        self.movie.finished.connect(self.loop.quit)
        self.loop.exec()
        
    def _on_frame_changed(self, frame_number):
        if self._stopped:
            self.movie.stop()
            QtCore.QMetaObject.invokeMethod(
                self.loop, "quit", Qt.QueuedConnection
            )
            return

        pix = self.movie.currentPixmap()
        self.frameReady.emit(pix)
        
    def stop(self):
        """Stop the worker thread."""
        self._stopped = True
        self.quit()
        self.wait()

class GifWindow(QWidget):
    """A window that displays GIF frames received from a background thread."""
    
    def __init__(self, gif_path: str):
        super().__init__()
        self.setWindowTitle("GIF Preview")
        self.setGeometry(200, 200, 400, 400)
        self.gif_path = gif_path
        self.drag_position = None
        self.is_resizing = False
        self.resize_start_pos = None
        self.resize_start_size = None
        self.is_focused = False
        
        # Fixed size - prevent auto-resizing
        self._current_size = QSize(400, 400)
        self._min_size = QSize(100, 100)
        self._max_size = QSize(2000, 2000)  # Set a reasonable maximum
        
        # make window transparent
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        
        # Create a central widget that will contain everything
        self.central_widget = QWidget(self)
        self.central_widget.setObjectName("central_widget")
        
        # Use a layout for the central widget
        layout = QVBoxLayout(self.central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.label = QLabel("Loading...")
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setStyleSheet("""
            QLabel {
                background-color: transparent;
                border: none;
            }
        """)
        layout.addWidget(self.label)
        
        # Set central widget to fill the window
        self.central_widget.setGeometry(0, 0, 400, 400)
        
        # Resize handle area
        self.resize_handle_size = 20
        
        # start the worker thread
        self.worker = GifWorker(gif_path)
        self.worker.frameReady.connect(self.update_frame)
        self.worker.error.connect(self.show_error)
        self.worker.start()
        
        # Update timer for smooth resizing
        self.update_timer = QTimer()
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self.update_gif_size)
        
    def update_frame(self, pixmap: QPixmap):
        """Display new frame from the worker thread."""
        # Store the original pixmap for scaling
        self.current_pixmap = pixmap
        self.update_gif_size()
    
    def show_error(self, msg: str):
        """Display error message."""
        self.label.setText(msg)
    
    def _update_border(self):
        """Update border based on focus state."""
        if self.is_focused:
            # Set a fixed border without causing layout changes
            self.central_widget.setStyleSheet("""
                QWidget#central_widget {
                    background-color: transparent;
                    border: 2px solid #0078d4;
                    border-radius: 2px;
                }
            """)
        else:
            self.central_widget.setStyleSheet("""
                QWidget#central_widget {
                    background-color: transparent;
                    border: none;
                }
            """)
    
    def focusInEvent(self, event):
        """Handle focus in event."""
        self.is_focused = True
        self._update_border()
        super().focusInEvent(event)
    
    def focusOutEvent(self, event):
        """Handle focus out event."""
        self.is_focused = False
        self._update_border()
        super().focusOutEvent(event)
        
    def closeEvent(self, event):
        """Stop thread cleanly on window close."""
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.stop()
        super().closeEvent(event)
        
    def mousePressEvent(self, event):
        """Handle mouse press for dragging or resizing."""
        self.setFocus()
        
        pos = event.position().toPoint()
        window_rect = self.rect()
        
        # Check if clicking in resize handle (bottom-right corner)
        resize_rect = QRect(
            window_rect.width() - self.resize_handle_size,
            window_rect.height() - self.resize_handle_size,
            self.resize_handle_size,
            self.resize_handle_size
        )
        
        if resize_rect.contains(pos):
            self.is_resizing = True
            self.resize_start_pos = event.globalPosition().toPoint()
            self.resize_start_size = self.size()
            self.drag_position = None  # Clear drag position when resizing
            self.setCursor(Qt.SizeFDiagCursor)
        elif event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setCursor(Qt.ArrowCursor)
        
    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging or resizing."""
        pos = event.position().toPoint()
        window_rect = self.rect()
        
        # Check if in resize area
        resize_rect = QRect(
            window_rect.width() - self.resize_handle_size,
            window_rect.height() - self.resize_handle_size,
            self.resize_handle_size,
            self.resize_handle_size
        )
        
        # Update cursor when hovering over resize handle
        if resize_rect.contains(pos):
            self.setCursor(Qt.SizeFDiagCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        
        # Handle resizing
        if self.is_resizing and event.buttons() == Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self.resize_start_pos
            new_width = min(
                self._max_size.width(), 
                max(self._min_size.width(), self.resize_start_size.width() + delta.x())
            )
            new_height = min(
                self._max_size.height(), 
                max(self._min_size.height(), self.resize_start_size.height() + delta.y())
            )
            
            # Update size
            self._current_size = QSize(new_width, new_height)
            self.resize(self._current_size)
            
            # Update central widget to fill the window
            self.central_widget.setGeometry(0, 0, new_width, new_height)
            
            # Trigger delayed update of GIF size
            if not self.update_timer.isActive():
                self.update_timer.start(50)
            
        # Handle dragging
        elif event.buttons() == Qt.LeftButton and self.drag_position is not None:
            self.move(event.globalPosition().toPoint() - self.drag_position)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release."""
        self.is_resizing = False
        self.drag_position = None
    
    def resizeEvent(self, event):
        """Handle resize event."""
        new_size = event.size()
        self._current_size = new_size
        
        # Update central widget to fill the entire window
        self.central_widget.setGeometry(0, 0, new_size.width(), new_size.height())
        
        # Update GIF size if we have a pixmap
        if hasattr(self, 'current_pixmap'):
            self.update_gif_size()
        
        super().resizeEvent(event)
    
    def update_gif_size(self):
        """Update GIF size based on current window size."""
        if hasattr(self, 'current_pixmap') and hasattr(self, 'label'):
            # Get the available size (accounting for border if focused)
            available_size = self.central_widget.size()
            if self.is_focused:
                available_size -= QSize(4, 4)  # Account for border width
            
            scaled_pix = self.current_pixmap.scaled(
                available_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.label.setPixmap(scaled_pix)
    
    def paintEvent(self, event):
        """Paint resize handle indicator."""
        super().paintEvent(event)
        
        if self.is_focused:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # Draw resize handle indicator only when focused
            painter.setBrush(QBrush(QColor(0, 120, 212, 150)))
            painter.setPen(Qt.NoPen)
            
            # Draw triangle in bottom-right corner
            size = self.size()
            points = [
                QtCore.QPoint(size.width(), size.height() - self.resize_handle_size),
                QtCore.QPoint(size.width() - self.resize_handle_size, size.height()),
                QtCore.QPoint(size.width(), size.height())
            ]
            painter.drawPolygon(points)
            
            painter.end()

class MainWindow(QtWidgets.QMainWindow):
    CONFIG_FILE = "gif_overlay_config.json"

    def __init__(self):
        super().__init__()

        # set window size and title
        self.setWindowTitle("Gif Overlay")
        self.setGeometry(100, 100, 400, 600)

        # main widget
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        # window layout
        window_layout = QVBoxLayout(main_widget)

        # scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        # widget for gif rows inside scroll area
        self.content_widget = QWidget()
        self.main_layout = QVBoxLayout(self.content_widget)
        self.main_layout.addStretch()

        # button to add more rows
        add_row_button = QPushButton("Add GIF")
        add_row_button.clicked.connect(self.add_row)

        scroll_area.setWidget(self.content_widget)
        window_layout.addWidget(scroll_area)
        window_layout.addWidget(add_row_button)

        self.gif_windows = {}
        self.gif_paths = []
        
        # initial row
        self.load_gif_config()

    def add_row(self):
        """Add more GIF management row."""
        row_frame = QFrame()
        row_frame.setFrameShape(QFrame.Box)
        row_frame.setFrameShadow(QFrame.Plain)
        row_frame.setLineWidth(1)
        row_frame.setFixedHeight(150)

        # layout
        row_layout = QGridLayout(row_frame)

        # image preview
        image_preview = QLabel()
        image_preview.setFixedSize(120, 120)
        self.set_scaled_pixmap(image_preview, QPixmap())
        image_preview.setAlignment(QtCore.Qt.AlignCenter)
        image_preview.setStyleSheet(
            "border: 2px solid gray; background-color: transparent; border-radius: 5px;"
        )

        # buttons
        select_gif_button = QPushButton("Select GIF")
        select_gif_button.clicked.connect(lambda: self.gif_browser(image_preview))

        show_hide_gif_button = QPushButton("Show GIF")
        show_hide_gif_button.clicked.connect(lambda: self.toggle_gif_window(image_preview, show_hide_gif_button))

        remove_gif_button = QPushButton("Remove GIF")
        remove_gif_button.clicked.connect(lambda: self.remove_row(row_frame, image_preview))

        # layout
        # image on the right all button on the left
        row_layout.addWidget(select_gif_button, 0, 0)
        row_layout.addWidget(show_hide_gif_button, 1, 0)
        row_layout.addWidget(remove_gif_button, 2, 0)
        row_layout.addWidget(image_preview, 0, 1, 3, 1)

        self.main_layout.insertWidget(self.main_layout.count() - 1, row_frame)

        return row_layout

    def remove_row(self, row_frame, image_preview):
        """Remove a GIF management row."""
        # close gif window if open
        if image_preview in self.gif_windows:
            self.gif_windows[image_preview].close()
            del self.gif_windows[image_preview]

        path = getattr(image_preview, "file_path", None)
        if path and path in self.gif_paths:
            self.gif_paths.remove(path)
            self.save_gif_config()
        self.main_layout.removeWidget(row_frame)
        row_frame.deleteLater()

    def gif_browser(self, image_preview):
        """Open file dialog to select a GIF file."""
        file_dialog = QFileDialog(self)
        file_dialog.setNameFilter("GIF Files (*.gif)")
        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                path = selected_files[0]
                pixmap = QPixmap(path)
                self.set_scaled_pixmap(image_preview, pixmap)
                image_preview.file_path = path
                image_preview.setToolTip(path)

                #save path to config
                self.gif_paths.append(path)
                self.save_gif_config()

    def set_scaled_pixmap(self, label, pixmap):
        """Scale pixmap to fit label while maintaining aspect ratio."""
        if not pixmap.isNull():
            scaled_pixmap = pixmap.scaled(
                label.width(),
                label.height(),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
            label.setPixmap(scaled_pixmap)
        else:
            label.clear()
            label.setText("No Image")
            label.setAlignment(QtCore.Qt.AlignCenter)
            label.setStyleSheet(
                "border: 2px solid gray; background-color: transparent; border-radius: 5px;"
            )

    def toggle_gif_window(self, image_preview, button):
        """Toggle GIF window open/close."""
        path = getattr(image_preview, "file_path", None)
        if not path:
            QtWidgets.QMessageBox.warning(self, "No GIF Selected", "Please select a GIF first.")
            return
        
        if image_preview in self.gif_windows:
            self.gif_windows[image_preview].close()
            del self.gif_windows[image_preview]
            button.setText("Show GIF")
        else:
            gif_win = GifWindow(path)
            gif_win.show()
            self.gif_windows[image_preview] = gif_win
            button.setText("Close GIF")
        
    def save_gif_config(self):
        """Save GIF data to config file."""
        try:
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"gif_paths": self.gif_paths}, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

    def load_gif_config(self):
        """Load GIF config from a config file."""

        if not os.path.exists(self.CONFIG_FILE):
            self.add_row()
            return
        
        try:
            with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.gif_paths = data.get("gif_paths", [])
            
            #Add rows for each saved gif path
            for gif_path in self.gif_paths:
                #Only add row if file exists
                if os.path.exists(gif_path):
                    self.add_row()
                    labels = self.content_widget.findChildren(QLabel)
                    if labels:
                        last_label = labels[-1]
                        pixmap = QPixmap(gif_path)
                        self.set_scaled_pixmap(last_label, pixmap)
                        last_label.file_path = gif_path
                        last_label.setToolTip(gif_path)
        except Exception as e:
            print(f"Error loading config: {e}")
            self.add_row() #Fallback
        
if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    sys.exit(app.exec())