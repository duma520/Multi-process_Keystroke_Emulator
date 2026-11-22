import os
import sys
import sqlite3
import win32api
import win32con
import win32gui
import win32process
import pypinyin
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QListWidget, QPushButton, QLabel, QMessageBox, QMenu, QInputDialog,
                             QListWidgetItem
                             )
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import QIcon
import ctypes
from ctypes import (windll, Structure, c_ulong, c_ushort, c_short, POINTER, pointer, Union, c_int, c_long, sizeof, wintypes)


# 先定义结构体类
class KeyBdInput(Structure):
    _fields_ = [
        ("wVk", c_ushort),
        ("wScan", c_ushort),
        ("dwFlags", c_ulong),
        ("time", c_ulong),
        ("dwExtraInfo", POINTER(c_ulong))
    ]
    
class HardwareInput(Structure):
    _fields_ = [
        ("uMsg", c_ulong),
        ("wParamL", c_ushort),
        ("wParamH", c_ushort)
    ]
    
class MouseInput(Structure):
    _fields_ = [
        ("dx", c_long),
        ("dy", c_long),
        ("mouseData", c_ulong),
        ("dwFlags", c_ulong),
        ("time", c_ulong),
        ("dwExtraInfo", POINTER(c_ulong))
    ]
    
# 然后定义 Union 类
class InputUnion(Union):
    _fields_ = [
        ("ki", KeyBdInput),
        ("mi", MouseInput), 
        ("hi", HardwareInput) 
    ]
    
# 最后定义 Input 结构体
class Input(Structure):
    _fields_ = [
        ("type", c_ulong),
        ("union", InputUnion)
    ]


class ProcessManager(QMainWindow):
    # 在类内部引用这些结构体
    KeyBdInput = KeyBdInput
    HardwareInput = HardwareInput
    MouseInput = MouseInput
    InputUnion = InputUnion
    Input = Input

    def __init__(self):
        super().__init__()
        self.current_user = None
        self.db_conn = None
        self.init_ui()
        self.load_settings()
        self.init_db()
        self.show_processes()

    def init_ui(self):
        # 主窗口设置
        self.setWindowTitle('进程管理工具')
        self.resize(1000, 600)
        
        # 尝试设置图标
        if os.path.exists('icon.ico'):
            self.setWindowIcon(QIcon('icon.ico'))
        
        # 主控件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # 主布局
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)
        
        # 用户管理区域
        user_layout = QHBoxLayout()
        self.user_label = QLabel('当前用户: 未登录')
        self.user_combo = QListWidget()
        self.user_combo.setMaximumHeight(100)
        self.add_user_btn = QPushButton('添加用户')
        self.delete_user_btn = QPushButton('删除用户')
        
        user_layout.addWidget(self.user_label)
        user_layout.addWidget(self.user_combo)
        user_layout.addWidget(self.add_user_btn)
        user_layout.addWidget(self.delete_user_btn)
        main_layout.addLayout(user_layout)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        self.to_left_btn = QPushButton('全部移动到左侧')
        self.to_center_btn = QPushButton('全部移动到中间')
        self.to_right_btn = QPushButton('全部移动到右侧')
        
        button_layout.addWidget(self.to_left_btn)
        button_layout.addWidget(self.to_center_btn)
        button_layout.addWidget(self.to_right_btn)
        main_layout.addLayout(button_layout)
        
        # 进程列表区域
        process_layout = QHBoxLayout()
        self.left_list = QListWidget()
        self.center_list = QListWidget()
        self.right_list = QListWidget()
        
        # 设置选择模式为复选框
        self.left_list.setSelectionMode(QListWidget.NoSelection)
        self.center_list.setSelectionMode(QListWidget.NoSelection)
        self.right_list.setSelectionMode(QListWidget.NoSelection)
        self.left_list.setStyleSheet("QListWidget::item { padding: 5px; }")
        self.center_list.setStyleSheet("QListWidget::item { padding: 5px; }")
        self.right_list.setStyleSheet("QListWidget::item { padding: 5px; }")
        
        # 添加标签
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel('左侧列表 (按A键)'))
        left_layout.addWidget(self.left_list)
        
        center_layout = QVBoxLayout()
        center_layout.addWidget(QLabel('中间列表 (无操作)'))
        center_layout.addWidget(self.center_list)
        
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel('右侧列表 (按D键)'))
        right_layout.addWidget(self.right_list)
        
        process_layout.addLayout(left_layout)
        process_layout.addLayout(center_layout)
        process_layout.addLayout(right_layout)
        main_layout.addLayout(process_layout)
        
        # 连接信号槽
        self.add_user_btn.clicked.connect(self.add_user)
        self.delete_user_btn.clicked.connect(self.delete_user)
        self.user_combo.itemClicked.connect(self.switch_user)
        
        self.to_left_btn.clicked.connect(lambda: self.move_all_processes('left'))
        self.to_center_btn.clicked.connect(lambda: self.move_all_processes('center'))
        self.to_right_btn.clicked.connect(lambda: self.move_all_processes('right'))
        
        self.left_list.itemDoubleClicked.connect(lambda: self.move_selected_processes(self.left_list, 'right'))
        self.right_list.itemDoubleClicked.connect(lambda: self.move_selected_processes(self.right_list, 'left'))
        
        # 设置右键菜单
        self.left_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.center_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.right_list.setContextMenuPolicy(Qt.CustomContextMenu)
        
        self.left_list.customContextMenuRequested.connect(lambda pos: self.show_context_menu(pos, self.left_list))
        self.center_list.customContextMenuRequested.connect(lambda pos: self.show_context_menu(pos, self.center_list))
        self.right_list.customContextMenuRequested.connect(lambda pos: self.show_context_menu(pos, self.right_list))
        
        # 定时器模拟按键
        self.timer = self.startTimer(1000)  # 1秒检查一次
    
    def load_settings(self):
        self.settings = QSettings('ProcessManager', 'UserSettings')
        last_user = self.settings.value('last_user', '')
        
        # 加载用户列表
        users = []
        if os.path.exists('users.db'):
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            cursor.execute('SELECT name FROM users')
            users = [row[0] for row in cursor.fetchall()]
            conn.close()
        
        # 更新用户下拉框
        self.user_combo.clear()
        self.user_combo.addItems(users)
        
        # 如果有上次登录的用户，尝试切换到该用户
        if last_user and last_user in users:
            self.switch_user_by_name(last_user)
    
    def init_db(self):
        if not self.current_user:
            return
            
        db_file = f'user_{self.current_user}.db'
        self.db_conn = sqlite3.connect(db_file)
        cursor = self.db_conn.cursor()
        
        # 创建进程表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS processes (
            pid INTEGER PRIMARY KEY,
            name TEXT,
            position TEXT CHECK(position IN ('left', 'center', 'right'))
        )
        ''')
        
        self.db_conn.commit()
    
    def show_processes(self):
        if not self.current_user:
            return
            
        # 清空列表
        self.left_list.clear()
        self.center_list.clear()
        self.right_list.clear()
        
        # 从数据库加载进程
        cursor = self.db_conn.cursor()
        cursor.execute('SELECT pid, name, position FROM processes')
        processes = cursor.fetchall()
        
        for pid, name, position in processes:
            item_text = f"{name} (PID: {pid})"
            item = QListWidgetItem(item_text)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)  # 默认未选中
            if position == 'left':
                self.left_list.addItem(item)
            elif position == 'center':
                self.center_list.addItem(item)
            elif position == 'right':
                self.right_list.addItem(item)
        
        # 自动查找 zhengtu.dat 进程并添加到中间列表
        self.find_zhengtu_process()
    
    def find_zhengtu_process(self):
        # 获取所有进程
        processes = self.get_all_processes()
        
        # 查找 zhengtu.dat 进程
        zhengtu_processes = [p for p in processes if 'zhengtu.dat' in p[1].lower()]
        
        # 添加到中间列表
        for pid, name in zhengtu_processes:
            item_text = f"{name} (PID: {pid})"
            
            # 检查是否已经在任何列表中
            exists = False
            for list_widget in [self.left_list, self.center_list, self.right_list]:
                items = [list_widget.item(i).text() for i in range(list_widget.count())]
                if item_text in items:
                    exists = True
                    break
            
            if not exists:
                item = QListWidgetItem(item_text)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                self.center_list.addItem(item)
                # 添加到数据库
                cursor = self.db_conn.cursor()
                cursor.execute('INSERT OR IGNORE INTO processes (pid, name, position) VALUES (?, ?, ?)', 
                              (pid, name, 'center'))
                self.db_conn.commit()
    
    def get_all_processes(self):
        processes = []
        try:
            # 使用工具帮助函数获取进程列表
            def window_enum_callback(hwnd, extra):
                pid = win32process.GetWindowThreadProcessId(hwnd)[1]
                try:
                    name = win32process.GetModuleFileNameEx(win32api.OpenProcess(
                        win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
                        False, pid), 0)
                    processes.append((pid, os.path.basename(name)))
                except:
                    pass

            win32gui.EnumWindows(window_enum_callback, None)
        except Exception as e:
            print(f"获取进程列表出错: {e}")
        
        return processes
    
    def add_user(self):
        text, ok = QInputDialog.getText(self, '添加用户', '请输入用户名:')
        if ok and text:
            # 检查用户名是否已存在
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            cursor.execute('SELECT name FROM users WHERE name = ?', (text,))
            if cursor.fetchone():
                QMessageBox.warning(self, '错误', '用户名已存在!')
                conn.close()
                return
            
            # 添加到用户数据库
            cursor.execute('INSERT INTO users (name) VALUES (?)', (text,))
            conn.commit()
            conn.close()
            
            # 创建用户数据库文件
            db_file = f'user_{text}.db'
            if not os.path.exists(db_file):
                conn = sqlite3.connect(db_file)
                conn.close()
            
            # 更新用户列表
            self.load_settings()
            
            # 切换到新用户
            self.switch_user_by_name(text)
    
    def delete_user(self):
        current_item = self.user_combo.currentItem()
        if not current_item:
            QMessageBox.warning(self, '错误', '请先选择要删除的用户!')
            return
            
        user_name = current_item.text()
        if user_name == self.current_user:
            QMessageBox.warning(self, '错误', '不能删除当前登录的用户!')
            return
            
        reply = QMessageBox.question(self, '确认', f'确定要删除用户 {user_name} 吗?', 
                                   QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            # 从用户数据库删除
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            cursor.execute('DELETE FROM users WHERE name = ?', (user_name,))
            conn.commit()
            conn.close()
            
            # 删除用户数据库文件
            db_file = f'user_{user_name}.db'
            if os.path.exists(db_file):
                try:
                    os.remove(db_file)
                except Exception as e:
                    QMessageBox.warning(self, '错误', f'删除用户数据库失败: {e}')
            
            # 更新用户列表
            self.load_settings()
    
    def switch_user(self, item):
        user_name = item.text()
        self.switch_user_by_name(user_name)
    
    def switch_user_by_name(self, user_name):
        # 保存当前用户设置
        if self.current_user and self.db_conn:
            self.db_conn.close()
        
        # 切换到新用户
        self.current_user = user_name
        self.user_label.setText(f'当前用户: {self.current_user}')
        self.settings.setValue('last_user', self.current_user)
        
        # 初始化新用户的数据库
        self.init_db()
        self.show_processes()
    
    def move_all_processes(self, position):
        if not self.current_user:
            QMessageBox.warning(self, '错误', '请先选择用户!')
            return
            
        # 确定源列表和目标列表
        if position == 'left':
            source_lists = [self.center_list, self.right_list]
            target_list = self.left_list
        elif position == 'center':
            source_lists = [self.left_list, self.right_list]
            target_list = self.center_list
        elif position == 'right':
            source_lists = [self.left_list, self.center_list]
            target_list = self.right_list
        
        # 移动所有进程
        for source_list in source_lists:
            while source_list.count() > 0:
                item = source_list.takeItem(0)
                target_list.addItem(item)
                
                # 更新数据库
                pid = int(item.text().split('(PID: ')[1].rstrip(')'))
                cursor = self.db_conn.cursor()
                cursor.execute('UPDATE processes SET position = ? WHERE pid = ?', (position, pid))
                self.db_conn.commit()
    
    def move_selected_processes(self, source_list, position):
        if not self.current_user:
            QMessageBox.warning(self, '错误', '请先选择用户!')
            return
            
        selected_items = source_list.selectedItems()
        if not selected_items:
            return
            
        # 确定目标列表
        if position == 'left':
            target_list = self.left_list
        elif position == 'center':
            target_list = self.center_list
        elif position == 'right':
            target_list = self.right_list
        
        for item in selected_items:
            # 克隆项目
            new_item = source_list.takeItem(source_list.row(item))
            target_list.addItem(new_item)
            
            # 更新数据库
            pid = int(new_item.text().split('(PID: ')[1].rstrip(')'))
            cursor = self.db_conn.cursor()
            cursor.execute('UPDATE processes SET position = ? WHERE pid = ?', (position, pid))
            self.db_conn.commit()
    
    def show_context_menu(self, pos, list_widget):
        selected_items = list_widget.selectedItems()
        if not selected_items:
            return
            
        menu = QMenu()
        
        left_action = menu.addAction("移动到左侧")
        center_action = menu.addAction("移动到中间")
        right_action = menu.addAction("移动到右侧")
        
        action = menu.exec_(list_widget.mapToGlobal(pos))
        
        if action == left_action:
            self.move_selected_processes(list_widget, 'left')
        elif action == center_action:
            self.move_selected_processes(list_widget, 'center')
        elif action == right_action:
            self.move_selected_processes(list_widget, 'right')
    
    def timerEvent(self, event):
        try:
            # 模拟按键
            self.simulate_keys()
        except Exception as e:
            print(f"定时器事件出错: {e}")

    
    def simulate_keys(self):
        # 左侧列表 - 模拟按A键
        left_success = 0
        left_failed = 0
        for i in range(self.left_list.count()):
            item = self.left_list.item(i)
            if item.checkState() == Qt.Checked:
                pid = int(item.text().split('(PID: ')[1].rstrip(')'))
                if self.send_key_to_process(pid, 'A'):
                    left_success += 1
                else:
                    left_failed += 1
        
        # 右侧列表 - 模拟按D键
        right_success = 0
        right_failed = 0
        for i in range(self.right_list.count()):
            item = self.right_list.item(i)
            if item.checkState() == Qt.Checked:
                pid = int(item.text().split('(PID: ')[1].rstrip(')'))
                if self.send_key_to_process(pid, 'D'):
                    right_success += 1
                else:
                    right_failed += 1
        
        # 调试输出
        if left_success or left_failed or right_success or right_failed:
            print(f"按键模拟结果: 左A键(成功{left_success}/失败{left_failed}) 右D键(成功{right_success}/失败{right_failed})")


    def get_process_thread_id(self, pid):
        """获取进程的主线程ID"""
        try:
            # 获取进程句柄
            h_process = win32api.OpenProcess(
                win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
                False, pid)
            
            # 枚举进程的线程
            threads = win32process.EnumProcessThreads(h_process)
            if threads:
                return threads[0][0]  # 返回第一个线程ID
        except:
            pass
        return 0

    def inject_key_event(self, pid, key, is_press=True):
        """使用线程级输入注入"""
        try:
            vk_code = ord(key.upper())
            thread_id = self.get_process_thread_id(pid)
            if not thread_id:
                return False
                
            # 准备输入结构
            keyboard_input = self.KeyBdInput(
                wVk=vk_code,
                wScan=0,
                dwFlags=0 if is_press else 2,  # 0=按下, 2=释放
                time=0,
                dwExtraInfo=None
            )
            
            # 创建输入事件
            input_event = self.Input(
                type=1,  # INPUT_KEYBOARD
                union=self.InputUnion(ki=keyboard_input)
            )
            
            # 附加到目标线程
            prev_thread = windll.kernel32.GetCurrentThreadId()
            windll.user32.AttachThreadInput(prev_thread, thread_id, True)
            
            # 发送输入
            result = self.send_input([input_event])
            
            # 恢复线程状态
            windll.user32.AttachThreadInput(prev_thread, thread_id, False)
            
            return bool(result)
        except Exception as e:
            print(f"注入按键事件失败: {e}")
            return False

    
    def send_key_to_process(self, pid, key):
        try:
            # 方法0: 使用线程注入 (最可靠)
            if self.inject_key_event(pid, key, True) and self.inject_key_event(pid, key, False):
                return True

            # 使用 ord() 获取字符的 ASCII 码作为虚拟键码
            vk_code = ord(key.upper())
            
            # 方法1: 使用 SendInput (最可靠)
            try:
                inputs = [
                    self.Input(1, self.InputUnion(ki=self.KeyBdInput(wVk=vk_code, wScan=0, dwFlags=0, time=0, dwExtraInfo=None))),
                    self.Input(1, self.InputUnion(ki=self.KeyBdInput(wVk=vk_code, wScan=0, dwFlags=2, time=0, dwExtraInfo=None)))
                ]
                self.send_input(inputs)
                return True
            except Exception as e:
                print(f"SendInput 失败: {e}")
            
            # 方法2: 使用 keybd_event (备用方案)
            try:
                win32api.keybd_event(vk_code, 0, 0, 0)  # 按下
                win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)  # 释放
                return True
            except Exception as e:
                print(f"keybd_event 失败: {e}")
            
            # 方法3: 尝试找到窗口并发送消息 (最后手段)
            windows = []
            def enum_windows_callback(hwnd, extra):
                _, process_id = win32process.GetWindowThreadProcessId(hwnd)
                if process_id == pid:
                    windows.append(hwnd)
            
            win32gui.EnumWindows(enum_windows_callback, None)
            
            if windows:
                for hwnd in windows:
                    try:
                        win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, vk_code, 0)
                        win32gui.PostMessage(hwnd, win32con.WM_KEYUP, vk_code, 0)
                        return True
                    except:
                        continue
            
            return False
        except Exception as e:
            print(f"发送按键到进程 {pid} 失败: {e}")
            return False




    
    def closeEvent(self, event):
        # 保存设置并关闭数据库
        if self.db_conn:
            self.db_conn.close()
        event.accept()



    def send_input(self, inputs):
        n_inputs = len(inputs)
        lp_input = (self.Input * n_inputs)(*inputs)
        cb_size = c_int(sizeof(self.Input))
        return windll.user32.SendInput(n_inputs, lp_input, cb_size)



def initialize_system():
    # 初始化用户数据库
    if not os.path.exists('users.db'):
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
        
        # 添加默认用户
        cursor.execute('INSERT INTO users (name) VALUES (?)', ('默认用户',))
        conn.commit()
        conn.close()
        
        # 创建默认用户数据库
        db_file = 'user_默认用户.db'
        if not os.path.exists(db_file):
            conn = sqlite3.connect(db_file)
            conn.close()



if __name__ == '__main__':
    # 初始化系统
    initialize_system()
    
    app = QApplication(sys.argv)
    manager = ProcessManager()
    manager.show()
    sys.exit(app.exec_())