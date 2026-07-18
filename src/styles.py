"""
UI 样式定义
"""

# 主题颜色
COLORS = {
    "primary": "#0066FF",  # 主色调蓝色
    "primary_hover": "#0052CC",
    "primary_light": "#E6F0FF",
    "background": "#F5F7FA",
    "card_bg": "#FFFFFF",
    "sidebar_bg": "#FAFBFC",
    "text_primary": "#1F2937",
    "text_secondary": "#6B7280",
    "border": "#E5E7EB",
    "success": "#10B981",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "info": "#3B82F6",
}

# 全局样式表
GLOBAL_STYLE = f"""
QMainWindow {{
    background-color: {COLORS['background']};
}}

/* 侧边栏样式 */
QListWidget#sidebar {{
    background-color: {COLORS['sidebar_bg']};
    border: none;
    border-right: 1px solid {COLORS['border']};
    padding: 8px;
    font-size: 14px;
}}

QListWidget#sidebar::item {{
    padding: 12px 16px;
    margin: 4px 0;
    border-radius: 8px;
    border-left: 3px solid transparent;
    color: {COLORS['text_primary']};
}}

QListWidget#sidebar::item:hover {{
    background-color: {COLORS['primary_light']};
}}

QListWidget#sidebar::item:selected {{
    background-color: {COLORS['primary']};
    color: white;
    font-weight: 500;
    border-left: 3px solid {COLORS['primary']};
}}

/* 卡片样式 */
QWidget#card {{
    background-color: {COLORS['card_bg']};
    border: 1px solid {COLORS['border']};
    border-radius: 12px;
    padding: 20px;
}}

/* 按钮样式 */
QPushButton {{
    background-color: {COLORS['card_bg']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 13px;
    font-weight: 500;
    color: {COLORS['text_primary']};
    min-height: 28px;
    text-decoration: none;
    outline: none;
}}

QPushButton:hover {{
    background-color: {COLORS['primary_light']};
    border-color: {COLORS['primary']};
    color: {COLORS['primary']};
}}

QPushButton:pressed {{
    background-color: {COLORS['primary']};
    color: white;
}}

QPushButton:focus {{
    outline: none;
    border: 1px solid {COLORS['border']};
}}

QPushButton#primary {{
    background-color: {COLORS['primary']};
    color: white;
    border: none;
    font-weight: 500;
}}

QPushButton#primary:hover {{
    background-color: {COLORS['primary_hover']};
}}

QPushButton#primary:focus {{
    outline: none;
}}

QPushButton#danger {{
    background-color: white;
    color: {COLORS['danger']};
    border: 1px solid {COLORS['danger']};
}}

QPushButton#danger:hover {{
    background-color: {COLORS['danger']};
    color: white;
}}

QPushButton#danger:focus {{
    outline: none;
}}

/* 表格样式 */
QTableWidget {{
    background-color: {COLORS['card_bg']};
    alternate-background-color: {COLORS['sidebar_bg']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    gridline-color: {COLORS['border']};
    font-size: 13px;
    outline: none;
}}

QTableWidget::item {{
    padding: 4px 8px;
    border-bottom: 1px solid {COLORS['border']};
    outline: none;
}}

QTableWidget::item:selected {{
    background-color: {COLORS['primary_light']};
    color: {COLORS['text_primary']};
    outline: none;
}}

QTableWidget::item:focus {{
    outline: none;
    border: none;
}}

QHeaderView::section {{
    background-color: {COLORS['sidebar_bg']};
    padding: 10px;
    border: none;
    border-bottom: 2px solid {COLORS['border']};
    font-weight: 600;
    color: {COLORS['text_secondary']};
    font-size: 12px;
    text-transform: uppercase;
}}

QTableCornerButton::section {{
    background-color: {COLORS['sidebar_bg']};
    border: none;
    border-bottom: 2px solid {COLORS['border']};
    border-right: 1px solid {COLORS['border']};
}}

/* 输入框样式 */
QLineEdit {{
    background-color: {COLORS['card_bg']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
    color: {COLORS['text_primary']};
    min-height: 24px;
}}

QLineEdit:focus {{
    border: 2px solid {COLORS['primary']};
    padding: 5px 9px;
}}

QComboBox {{
    background-color: {COLORS['card_bg']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
    color: {COLORS['text_primary']};
    min-height: 24px;
}}

QComboBox:hover {{
    border-color: {COLORS['primary']};
}}

QComboBox:focus {{
    border-color: {COLORS['primary']};
}}

QComboBox::drop-down {{
    border: none;
    padding-right: 8px;
}}

QComboBox QAbstractItemView {{
    background-color: {COLORS['card_bg']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    selection-background-color: {COLORS['primary_light']};
    selection-color: {COLORS['text_primary']};
    padding: 4px;
    outline: none;
}}

QComboBox QAbstractItemView::item {{
    background-color: {COLORS['card_bg']};
}}

QComboBox QAbstractItemView::item {{
    min-height: 24px;
    padding: 4px 8px;
    color: {COLORS['text_primary']};
    border: none;
}}

QComboBox QAbstractItemView::item:selected {{
    background-color: {COLORS['primary_light']};
    color: {COLORS['text_primary']};
}}

QComboBox QAbstractItemView::item:hover {{
    background-color: {COLORS['primary_light']};
}}

/* 标签样式 */
QLabel {{
    color: {COLORS['text_primary']};
    font-size: 13px;
}}

QLabel#title {{
    font-size: 20px;
    font-weight: bold;
    color: {COLORS['text_primary']};
    margin-bottom: 4px;
    padding: 4px 0;
}}

QLabel#subtitle {{
    font-size: 14px;
    color: {COLORS['text_secondary']};
    margin-bottom: 16px;
}}

QLabel#section_title {{
    font-size: 14px;
    font-weight: 600;
    color: {COLORS['text_primary']};
    margin-top: 16px;
    margin-bottom: 8px;
    padding-left: 8px;
    border-left: 3px solid {COLORS['primary']};
}}

/* 列表样式 */
QListWidget {{
    background-color: {COLORS['card_bg']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 4px;
    font-size: 13px;
}}

QListWidget::item {{
    padding: 8px;
    border-radius: 4px;
    margin: 2px;
}}

QListWidget::item:hover {{
    background-color: {COLORS['primary_light']};
}}

QListWidget::item:selected {{
    background-color: {COLORS['primary']};
    color: white;
}}

/* 状态栏样式 */
QStatusBar {{
    background-color: {COLORS['sidebar_bg']};
    color: {COLORS['text_secondary']};
    border-top: 1px solid {COLORS['border']};
    font-size: 12px;
}}

/* 对话框样式 */
QDialog {{
    background-color: {COLORS['background']};
}}

/* 滚动条样式 */
QScrollBar:vertical {{
    background-color: {COLORS['background']};
    width: 12px;
    border: none;
    border-radius: 6px;
}}

QScrollBar::handle:vertical {{
    background-color: {COLORS['border']};
    border-radius: 6px;
    min-height: 20px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {COLORS['text_secondary']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background-color: {COLORS['background']};
    height: 12px;
    border: none;
    border-radius: 6px;
}}

QScrollBar::handle:horizontal {{
    background-color: {COLORS['border']};
    border-radius: 6px;
    min-width: 20px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {COLORS['text_secondary']};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* 菜单栏样式 */
QMenuBar {{
    background-color: {COLORS['card_bg']};
    border-bottom: 1px solid {COLORS['border']};
    padding: 4px;
}}

QMenuBar::item {{
    padding: 6px 12px;
    border-radius: 4px;
}}

QMenuBar::item:selected {{
    background-color: {COLORS['primary_light']};
}}

QMenu {{
    background-color: {COLORS['card_bg']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 4px;
}}

QMenu::item {{
    padding: 8px 24px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background-color: {COLORS['primary_light']};
}}

/* 软件包管理面板样式 */
QWidget#packagePanel {{
    background-color: {COLORS['background']};
    border-top: 2px solid {COLORS['border']};
}}

QWidget#packageContainer {{
    background-color: {COLORS['background']};
}}

QWidget#packagePanel QWidget {{
    background-color: transparent;
}}

/* 分隔线样式 */
QFrame[frameShape="4"] {{
    background-color: {COLORS['border']};
    max-height: 1px;
}}
"""

# 暗色主题颜色
DARK_COLORS = {
    "primary": "#0066FF",
    "primary_hover": "#0052CC",
    "primary_light": "#37373D",
    "background": "#1E1E1E",
    "card_bg": "#252526",
    "sidebar_bg": "#252526",
    "text_primary": "#E0E0E0",
    "text_secondary": "#AAAAAA",
    "border": "#3E3E42",
    "success": "#10B981",
    "warning": "#F59E0B",
    "danger": "#DC3545",
    "danger_hover": "#C82333",
    "info": "#3B82F6",
    "input_bg": "#3E3E42",
    "input_border": "#555555",
    "hover_bg": "#2A2D2E",
    "selected_bg": "#37373D",
    "header_bg": "#2D2D30",
    "scrollbar_handle": "#555555",
    "scrollbar_handle_hover": "#666666",
    "btn_bg": "#3E3E42",
    "btn_hover_bg": "#505050",
    "subtitle_color": "#AAAAAA",
    "sidebar_text": "#CCCCCC",
}

# 暗色全局样式表
DARK_GLOBAL_STYLE = f"""
QMainWindow {{
    background-color: {DARK_COLORS['background']};
    color: {DARK_COLORS['text_primary']};
}}

QListWidget#sidebar {{
    background-color: {DARK_COLORS['sidebar_bg']};
    border: none;
    border-right: 1px solid {DARK_COLORS['border']};
    padding: 8px;
    font-size: 14px;
}}

QListWidget#sidebar::item {{
    padding: 12px 16px;
    margin: 4px 0;
    border-radius: 8px;
    border-left: 3px solid transparent;
    color: {DARK_COLORS['sidebar_text']};
}}

QListWidget#sidebar::item:hover {{
    background-color: {DARK_COLORS['hover_bg']};
}}

QListWidget#sidebar::item:selected {{
    background-color: {DARK_COLORS['primary']};
    color: #FFFFFF;
    font-weight: 500;
    border-left: 3px solid {DARK_COLORS['primary']};
}}

QWidget#card {{
    background-color: {DARK_COLORS['card_bg']};
    border: 1px solid {DARK_COLORS['border']};
    border-radius: 12px;
    padding: 20px;
}}

QPushButton {{
    background-color: {DARK_COLORS['btn_bg']};
    color: {DARK_COLORS['text_primary']};
    border: 1px solid {DARK_COLORS['input_border']};
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 13px;
    font-weight: 500;
    min-height: 28px;
    outline: none;
}}

QPushButton:hover {{
    background-color: {DARK_COLORS['btn_hover_bg']};
    border-color: {DARK_COLORS['primary']};
    color: {DARK_COLORS['primary']};
}}

QPushButton:pressed {{
    background-color: {DARK_COLORS['primary']};
    color: white;
}}

QPushButton:focus {{
    outline: none;
    border: 1px solid {DARK_COLORS['input_border']};
}}

QPushButton#primary {{
    background-color: {DARK_COLORS['primary']};
    color: white;
    border: none;
    font-weight: 500;
}}

QPushButton#primary:hover {{
    background-color: {DARK_COLORS['primary_hover']};
    color: white;
}}

QPushButton#primary:focus {{
    outline: none;
}}

QPushButton#danger {{
    background-color: {DARK_COLORS['danger']};
    color: white;
    border: none;
}}

QPushButton#danger:hover {{
    background-color: {DARK_COLORS['danger_hover']};
    color: white;
}}

QPushButton#danger:focus {{
    outline: none;
}}

QTableWidget {{
    background-color: {DARK_COLORS['card_bg']};
    alternate-background-color: {DARK_COLORS['header_bg']};
    color: {DARK_COLORS['text_primary']};
    gridline-color: {DARK_COLORS['border']};
    border: 1px solid {DARK_COLORS['border']};
    border-radius: 8px;
    font-size: 13px;
    outline: none;
}}

QTableWidget::item {{
    background-color: {DARK_COLORS['card_bg']};
    color: {DARK_COLORS['text_primary']};
    padding: 4px 8px;
    border-bottom: 1px solid {DARK_COLORS['border']};
    outline: none;
}}

QTableWidget::item:alternate {{
    background-color: {DARK_COLORS['header_bg']};
}}

QTableWidget::item:selected {{
    background-color: {DARK_COLORS['selected_bg']};
    color: #FFFFFF;
    outline: none;
}}

QTableWidget::item:hover {{
    background-color: {DARK_COLORS['hover_bg']};
}}

QTableWidget::item:focus {{
    outline: none;
    border: none;
}}

QHeaderView::section {{
    background-color: {DARK_COLORS['header_bg']};
    color: {DARK_COLORS['text_primary']};
    border: none;
    border-bottom: 2px solid {DARK_COLORS['border']};
    padding: 10px;
    font-weight: 600;
    font-size: 12px;
}}

QTableCornerButton::section {{
    background-color: {DARK_COLORS['header_bg']};
    border: none;
    border-bottom: 2px solid {DARK_COLORS['border']};
    border-right: 1px solid {DARK_COLORS['border']};
}}

QLineEdit {{
    background-color: {DARK_COLORS['input_bg']};
    color: {DARK_COLORS['text_primary']};
    border: 1px solid {DARK_COLORS['input_border']};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
    min-height: 24px;
}}

QLineEdit:focus {{
    border: 2px solid {DARK_COLORS['primary']};
    padding: 5px 9px;
}}

QComboBox {{
    background-color: {DARK_COLORS['input_bg']};
    color: {DARK_COLORS['text_primary']};
    border: 1px solid {DARK_COLORS['input_border']};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
    min-height: 24px;
}}

QComboBox:hover {{
    border-color: {DARK_COLORS['primary']};
}}

QComboBox:focus {{
    border-color: {DARK_COLORS['primary']};
}}

QComboBox::drop-down {{
    border: none;
    padding-right: 8px;
}}

QComboBox QAbstractItemView {{
    background-color: {DARK_COLORS['card_bg']};
    color: {DARK_COLORS['text_primary']};
    selection-background-color: {DARK_COLORS['selected_bg']};
    selection-color: #FFFFFF;
    border: 1px solid {DARK_COLORS['border']};
    border-radius: 6px;
    padding: 4px;
    outline: none;
}}

QComboBox QAbstractItemView::item {{
    background-color: {DARK_COLORS['card_bg']};
    min-height: 24px;
    padding: 4px 8px;
    color: {DARK_COLORS['text_primary']};
    border: none;
}}

QComboBox QAbstractItemView::item:selected {{
    background-color: {DARK_COLORS['selected_bg']};
    color: #FFFFFF;
}}

QComboBox QAbstractItemView::item:hover {{
    background-color: {DARK_COLORS['hover_bg']};
}}

QLabel {{
    color: {DARK_COLORS['text_primary']};
    background-color: transparent;
    font-size: 13px;
}}

QLabel#title {{
    font-size: 20px;
    font-weight: bold;
    color: {DARK_COLORS['text_primary']};
    margin-bottom: 4px;
    padding: 4px 0;
}}

QLabel#subtitle {{
    font-size: 14px;
    color: {DARK_COLORS['subtitle_color']};
    margin-bottom: 16px;
}}

QLabel#section_title {{
    font-size: 14px;
    font-weight: 600;
    color: {DARK_COLORS['text_primary']};
    margin-top: 16px;
    margin-bottom: 8px;
    padding-left: 8px;
    border-left: 3px solid {DARK_COLORS['primary']};
}}

QDialog {{
    background-color: {DARK_COLORS['background']};
    color: {DARK_COLORS['text_primary']};
}}

QScrollArea {{
    background-color: {DARK_COLORS['background']};
    border: none;
}}

QScrollBar:vertical {{
    background-color: {DARK_COLORS['background']};
    width: 12px;
    border: none;
    border-radius: 6px;
}}

QScrollBar::handle:vertical {{
    background-color: {DARK_COLORS['scrollbar_handle']};
    border-radius: 6px;
    min-height: 20px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {DARK_COLORS['scrollbar_handle_hover']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background-color: {DARK_COLORS['background']};
    height: 12px;
    border: none;
    border-radius: 6px;
}}

QScrollBar::handle:horizontal {{
    background-color: {DARK_COLORS['scrollbar_handle']};
    border-radius: 6px;
    min-width: 20px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {DARK_COLORS['scrollbar_handle_hover']};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

QSplitter::handle {{
    background-color: {DARK_COLORS['border']};
}}

QSplitter::handle:hover {{
    background-color: {DARK_COLORS['primary']};
}}

QFrame {{
    background-color: {DARK_COLORS['background']};
    color: {DARK_COLORS['text_primary']};
}}

QMenuBar {{
    background-color: {DARK_COLORS['header_bg']};
    color: {DARK_COLORS['text_primary']};
    border-bottom: 1px solid {DARK_COLORS['border']};
    padding: 4px;
}}

QMenuBar::item {{
    background-color: transparent;
    padding: 6px 12px;
    border-radius: 4px;
}}

QMenuBar::item:selected {{
    background-color: {DARK_COLORS['selected_bg']};
}}

QMenu {{
    background-color: {DARK_COLORS['card_bg']};
    color: {DARK_COLORS['text_primary']};
    border: 1px solid {DARK_COLORS['border']};
    border-radius: 8px;
    padding: 4px;
}}

QMenu::item {{
    padding: 8px 24px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background-color: {DARK_COLORS['selected_bg']};
}}

QStatusBar {{
    background-color: {DARK_COLORS['header_bg']};
    color: {DARK_COLORS['subtitle_color']};
    border-top: 1px solid {DARK_COLORS['border']};
    font-size: 12px;
}}

QWidget#packagePanel {{
    background-color: {DARK_COLORS['background']};
    border-top: 2px solid {DARK_COLORS['border']};
}}

QWidget#packageContainer {{
    background-color: {DARK_COLORS['background']};
}}

QWidget#packagePanel QWidget {{
    background-color: transparent;
}}

QWidget#packagePanel QLineEdit {{
    background-color: {DARK_COLORS['input_bg']};
    color: {DARK_COLORS['text_primary']};
    border: 1px solid {DARK_COLORS['input_border']};
}}

QWidget#packagePanel QComboBox {{
    background-color: {DARK_COLORS['input_bg']};
    color: {DARK_COLORS['text_primary']};
    border: 1px solid {DARK_COLORS['input_border']};
}}

QWidget#packagePanel QComboBox QAbstractItemView {{
    background-color: {DARK_COLORS['card_bg']};
    color: {DARK_COLORS['text_primary']};
    border: 1px solid {DARK_COLORS['border']};
    border-radius: 6px;
    outline: none;
}}

QWidget#packagePanel QComboBox QAbstractItemView::item {{
    background-color: {DARK_COLORS['card_bg']};
    color: {DARK_COLORS['text_primary']};
    min-height: 24px;
    padding: 4px 8px;
    border: none;
}}

QWidget#packagePanel QComboBox QAbstractItemView::item:selected {{
    background-color: {DARK_COLORS['selected_bg']};
    color: #FFFFFF;
}}

QWidget#packagePanel QComboBox QAbstractItemView::item:hover {{
    background-color: {DARK_COLORS['hover_bg']};
}}

QWidget#packagePanel QPushButton {{
    background-color: {DARK_COLORS['btn_bg']};
    color: {DARK_COLORS['text_primary']};
    border: 1px solid {DARK_COLORS['input_border']};
}}

QWidget#packagePanel QLabel {{
    background-color: transparent;
    color: {DARK_COLORS['text_primary']};
}}

QFrame[frameShape="4"] {{
    background-color: {DARK_COLORS['border']};
    max-height: 1px;
}}

QTabWidget::pane {{
    border: 1px solid {DARK_COLORS['border']};
    border-radius: 8px;
    background: {DARK_COLORS['card_bg']};
    padding: 16px;
}}

QTabBar::tab {{
    background: {DARK_COLORS['header_bg']};
    border: 1px solid {DARK_COLORS['border']};
    padding: 8px 20px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-size: 13px;
    color: {DARK_COLORS['text_secondary']};
}}

QTabBar::tab:selected {{
    background: {DARK_COLORS['primary']};
    color: white;
    font-weight: 500;
}}

QTabBar::tab:hover {{
    background: {DARK_COLORS['selected_bg']};
    color: {DARK_COLORS['text_primary']};
}}

QProgressBar {{
    background-color: {DARK_COLORS['header_bg']};
    border: 1px solid {DARK_COLORS['border']};
    border-radius: 4px;
    text-align: center;
    color: {DARK_COLORS['text_primary']};
    min-height: 18px;
}}

QProgressBar::chunk {{
    background-color: {DARK_COLORS['primary']};
    border-radius: 3px;
}}

QGroupBox {{
    background-color: {DARK_COLORS['card_bg']};
    border: 1px solid {DARK_COLORS['border']};
    border-radius: 8px;
    margin-top: 12px;
    padding: 16px 12px 12px 12px;
    font-weight: 500;
    color: {DARK_COLORS['text_primary']};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {DARK_COLORS['text_primary']};
}}

QCheckBox {{
    color: {DARK_COLORS['text_primary']};
    spacing: 6px;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {DARK_COLORS['input_border']};
    border-radius: 3px;
    background-color: {DARK_COLORS['input_bg']};
}}

QCheckBox::indicator:checked {{
    background-color: {DARK_COLORS['primary']};
    border-color: {DARK_COLORS['primary']};
}}

QCheckBox::indicator:hover {{
    border-color: {DARK_COLORS['primary']};
}}

QToolTip {{
    background-color: {DARK_COLORS['card_bg']};
    color: {DARK_COLORS['text_primary']};
    border: 1px solid {DARK_COLORS['border']};
    padding: 4px;
}}
"""


def get_dark_tab_style():
    return (
        f"QTabWidget::pane {{ border: 1px solid {DARK_COLORS['border']}; border-radius: 8px; background: {DARK_COLORS['card_bg']}; padding: 16px; }}"
        f"QTabBar::tab {{ background: {DARK_COLORS['header_bg']}; border: 1px solid {DARK_COLORS['border']}; "
        f"padding: 8px 20px; margin-right: 2px; border-top-left-radius: 6px; border-top-right-radius: 6px; "
        f"font-size: 13px; color: {DARK_COLORS['text_secondary']}; }}"
        f"QTabBar::tab:selected {{ background: {DARK_COLORS['primary']}; color: white; font-weight: 500; }}"
        f"QTabBar::tab:hover {{ background: {DARK_COLORS['selected_bg']}; color: {DARK_COLORS['text_primary']}; }}"
    )


def get_light_tab_style():
    return (
        f"QTabWidget::pane {{ border: 1px solid {COLORS['border']}; border-radius: 8px; background: {COLORS['card_bg']}; padding: 16px; }}"
        f"QTabBar::tab {{ background: {COLORS['sidebar_bg']}; border: 1px solid {COLORS['border']}; "
        f"padding: 8px 20px; margin-right: 2px; border-top-left-radius: 6px; border-top-right-radius: 6px; "
        f"font-size: 13px; color: {COLORS['text_secondary']}; }}"
        f"QTabBar::tab:selected {{ background: {COLORS['primary']}; color: white; font-weight: 500; }}"
        f"QTabBar::tab:hover {{ background: {COLORS['primary_light']}; color: {COLORS['primary']}; }}"
    )


def get_dark_step_style():
    return {
        "completed": f"background-color: {DARK_COLORS['success']}; color: white; border-radius: 4px; padding: 4px 8px; font-size: 12px;",
        "current": f"background-color: {DARK_COLORS['primary']}; color: white; border-radius: 4px; padding: 4px 8px; font-weight: bold; font-size: 12px;",
        "pending": f"background-color: {DARK_COLORS['header_bg']}; color: {DARK_COLORS['text_secondary']}; border: 1px solid {DARK_COLORS['border']}; border-radius: 4px; padding: 4px 8px; font-size: 12px;",
    }


def get_light_step_style():
    return {
        "completed": f"background-color: {COLORS['success']}; color: white; border-radius: 4px; padding: 4px 8px; font-size: 12px;",
        "current": f"background-color: {COLORS['primary']}; color: white; border-radius: 4px; padding: 4px 8px; font-weight: bold; font-size: 12px;",
        "pending": f"background-color: {COLORS['sidebar_bg']}; color: {COLORS['text_secondary']}; border: 1px solid {COLORS['border']}; border-radius: 4px; padding: 4px 8px; font-size: 12px;",
    }


def get_dark_log_style():
    return (
        f"background-color: #1a1a1a; color: {DARK_COLORS['text_primary']}; "
        f"border: 1px solid {DARK_COLORS['border']}; border-radius: 6px; "
        f"font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; padding: 8px;"
    )


def get_light_log_style():
    return (
        f"background-color: #1a1a1a; color: {COLORS['text_primary']}; "
        f"border: 1px solid {COLORS['border']}; border-radius: 6px; "
        f"font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; padding: 8px;"
    )


# 信息卡片样式
INFO_CARD_STYLE = f"""
QWidget#info_card {{
    background-color: {COLORS['card_bg']};
    border: 1px solid {COLORS['border']};
    border-radius: 12px;
    padding: 16px;
}}
"""

DARK_INFO_CARD_STYLE = f"""
QWidget#info_card {{
    background-color: {DARK_COLORS['card_bg']};
    border: 1px solid {DARK_COLORS['border']};
    border-radius: 12px;
    padding: 16px;
}}
"""

# 统计卡片样式
STAT_CARD_STYLE = f"""
QWidget#stat_card {{
    background-color: {COLORS['card_bg']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 12px;
}}
"""

DARK_STAT_CARD_STYLE = f"""
QWidget#stat_card {{
    background-color: {DARK_COLORS['card_bg']};
    border: 1px solid {DARK_COLORS['border']};
    border-radius: 8px;
    padding: 12px;
}}
"""


def get_dark_delete_btn_style():
    return (
        f"QPushButton {{ color: {DARK_COLORS['danger']}; border: none; font-size: 14px; }} "
        f"QPushButton:hover {{ background-color: {DARK_COLORS['danger']}; color: white; border-radius: 4px; }}"
    )


def get_light_delete_btn_style():
    return (
        f"QPushButton {{ color: {COLORS['danger']}; border: none; font-size: 14px; }} "
        f"QPushButton:hover {{ background-color: {COLORS['danger']}; color: white; border-radius: 4px; }}"
    )
