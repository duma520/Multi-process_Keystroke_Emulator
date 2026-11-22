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
                             QListWidgetItem, QComboBox
                             )
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import QIcon
import ctypes
from ctypes import (windll, Structure, c_ulong, c_ushort, c_short, POINTER, pointer, Union, c_int, c_long, sizeof, wintypes)
import ctypes.wintypes
from ctypes import wintypes as w
import struct
import time
import vgamepad as vg  # 虚拟游戏手柄库
import usb.core  # USB设备控制
import usb.util  # USB工具
from pynput import keyboard  # 键盘监听
import re  # 正则表达式


PROCESS_ALL_ACCESS = (0x000F0000 | 0x00100000 | 0xFFF)
VIRTUAL_MEM = (0x1000 | 0x2000)
PAGE_READWRITE = 0x04

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

class VirtualGamepad:
    def __init__(self):
        self.gamepad = vg.VX360Gamepad()
        
    def press_button(self, button):
        """模拟按下游戏手柄按钮"""
        if button == 'A':
            self.gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
        elif button == 'B':
            self.gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
        # 可以添加更多按钮映射
        self.gamepad.update()
        
    def release_button(self, button):
        """模拟释放游戏手柄按钮"""
        if button == 'A':
            self.gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
        elif button == 'B':
            self.gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
        self.gamepad.update()

class USBDeviceEmulator:
    def __init__(self, vendor_id, product_id):
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.device = None
        
    def connect(self):
        """连接到USB设备"""
        self.device = usb.core.find(idVendor=self.vendor_id, idProduct=self.product_id)
        if self.device is None:
            raise ValueError('Device not found')
            
    def send_key(self, key):
        """通过USB设备发送按键"""
        # 这里需要根据具体设备协议实现
        pass

class InputAnalyzer:
    def __init__(self):
        self.signatures = {
            'directinput': [b'dinput8.dll', b'dinput.dll'],
            'rawinput': [b'user32.dll!GetRawInputData'],
            'gamepad': [b'xinput1_3.dll', b'xinput1_4.dll']
        }
        
    def analyze(self, pid):
        """分析目标进程使用的输入API"""
        try:
            h_process = win32api.OpenProcess(
                win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
                False, pid)
                
            modules = win32process.EnumProcessModules(h_process)
            
            for module in modules:
                module_name = win32process.GetModuleFileNameEx(h_process, module)
                with open(module_name, 'rb') as f:
                    content = f.read(1024)  # 读取文件开头部分
                    
                for input_type, sigs in self.signatures.items():
                    for sig in sigs:
                        if sig in content:
                            return input_type
                            
            return 'default'
            
        except Exception as e:
            print(f"分析进程 {pid} 失败: {e}")
            return 'default'

class HardwareEmulator:
    def __init__(self):
        self.arduino_connected = False
        
    def connect_arduino(self, port='COM3'):
        """连接Arduino模拟器"""
        try:
            import serial
            self.serial = serial.Serial(port, 115200, timeout=1)
            self.arduino_connected = True
            return True
        except Exception as e:
            print(f"无法连接Arduino: {e}")
            return False
            
    def send_key_via_arduino(self, key):
        """通过Arduino发送按键"""
        if not self.arduino_connected:
            return False
            
        try:
            # 发送按键命令到Arduino
            self.serial.write(f"PRESS {key}\n".encode())
            time.sleep(0.05)
            self.serial.write(f"RELEASE {key}\n".encode())
            return True
        except Exception as e:
            print(f"Arduino通信失败: {e}")
            return False


class ProcessManager(QMainWindow):
    # 在类内部引用这些结构体
    KeyBdInput = KeyBdInput
    HardwareInput = HardwareInput
    MouseInput = MouseInput
    InputUnion = InputUnion
    Input = Input

    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    WM_CHAR = 0x0102
    MAPVK_VK_TO_VSC = 0
    MAPVK_VSC_TO_VK = 1
    MAPVK_VK_TO_CHAR = 2
    MAPVK_VSC_TO_VK_EX = 3
    MAPVK_VK_TO_VSC_EX = 4

    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008
    KEYEVENTF_UNICODE = 0x0004

    def __init__(self):
        super().__init__()
        self.current_user = None
        self.db_conn = None
        self.init_ui()
        self.load_settings()
        self.init_db()
        self.show_processes()
        self.virtual_gamepad = VirtualGamepad()
        self.usb_emulator = USBDeviceEmulator(vendor_id=0x1234, product_id=0x5678)  # 示例ID
        self.input_analyzer = InputAnalyzer()
        self.hardware_emulator = HardwareEmulator()

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

        # 添加输入方法选择
        self.input_method_label = QLabel('输入方法:')
        self.input_method_combo = QComboBox()
        self.input_method_combo.addItems([
            '自动检测',
            'DirectInput',
            'RawInput',
            '游戏手柄',
            '硬件模拟'
        ])
        
        # 添加到用户管理区域
        user_layout.addWidget(self.input_method_label)
        user_layout.addWidget(self.input_method_combo)
    
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
                name = item.text().split(' (PID: ')[0]
                
                print(f"尝试发送A键到进程 {name} (PID: {pid})...")
                
                # 尝试最多3次
                for attempt in range(1, 4):
                    if self.send_key_to_process(pid, 'A'):
                        left_success += 1
                        print(f"第{attempt}次尝试: 成功发送A键到进程 {name} (PID: {pid})")
                        break
                    elif attempt == 3:  # 最后一次尝试失败
                        left_failed += 1
                        print(f"第{attempt}次尝试: 无法发送A键到进程 {name} (PID: {pid})")
        
        # 右侧列表 - 模拟按D键
        right_success = 0
        right_failed = 0
        for i in range(self.right_list.count()):
            item = self.right_list.item(i)
            if item.checkState() == Qt.Checked:
                pid = int(item.text().split('(PID: ')[1].rstrip(')'))
                name = item.text().split(' (PID: ')[0]
                
                print(f"尝试发送D键到进程 {name} (PID: {pid})...")
                
                # 尝试最多3次
                for attempt in range(1, 4):
                    if self.send_key_to_process(pid, 'D'):
                        right_success += 1
                        print(f"第{attempt}次尝试: 成功发送D键到进程 {name} (PID: {pid})")
                        break
                    elif attempt == 3:  # 最后一次尝试失败
                        right_failed += 1
                        print(f"第{attempt}次尝试: 无法发送D键到进程 {name} (PID: {pid})")
        
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
        """
        向指定进程发送按键信号，使用多种技术尝试确保成功
        
        参数:
            pid: 目标进程ID
            key: 要发送的按键(A/D等)
            
        返回:
            bool: 是否成功发送
        """
        try:
            vk_code = ord(key.upper())
            scan_code = self.get_scan_code(vk_code)
            
            # 方法1: 使用内存注入 (最底层)
            if self._send_via_memory_injection(pid, key):
                print(f"通过内存注入成功发送 {key} 到进程 {pid}")
                return True
                
            # 方法2: 使用DirectInput (游戏专用)
            if self._send_via_directinput(pid, key):
                print(f"通过DirectInput成功发送 {key} 到进程 {pid}")
                return True
                
            # 方法3: 使用RawInput (绕过某些限制)
            if self._send_via_rawinput(pid, key):
                print(f"通过RawInput成功发送 {key} 到进程 {pid}")
                return True
                
            # 方法4: 使用虚拟游戏手柄
            if self._send_via_virtual_gamepad(key):
                print(f"通过虚拟游戏手柄成功发送 {key} 到进程 {pid}")
                return True
                
            # 方法5: 使用硬件模拟 (如Arduino)
            if self._send_via_hardware_emulation(key):
                print(f"通过硬件模拟成功发送 {key} 到进程 {pid}")
                return True
                
            # 方法6: 使用线程注入
            if self._send_via_thread_injection(pid, key):
                print(f"通过线程注入成功发送 {key} 到进程 {pid}")
                return True
                
            # 方法7: 使用PostMessage (最后手段)
            if self._send_via_postmessage(pid, key):
                print(f"通过PostMessage成功发送 {key} 到进程 {pid}")
                return True
                
            print(f"所有方法都无法发送 {key} 到进程 {pid}")
            return False
            
        except Exception as e:
            print(f"发送按键到进程 {pid} 失败: {str(e)}")
            return False

    def _send_via_memory_injection(self, pid, key):
        """通过内存注入方式发送按键"""
        try:
            # 获取目标进程句柄
            h_process = win32api.OpenProcess(
                win32con.PROCESS_VM_OPERATION | win32con.PROCESS_VM_WRITE | win32con.PROCESS_VM_READ,
                False, pid)
            if not h_process:
                return False
                
            # 查找目标窗口
            target_hwnd = None
            def enum_windows_callback(hwnd, pid_list):
                _, process_id = win32process.GetWindowThreadProcessId(hwnd)
                if process_id == pid_list[0] and win32gui.IsWindowVisible(hwnd):
                    pid_list[1] = hwnd
            
            target_hwnd = None
            win32gui.EnumWindows(enum_windows_callback, [pid, target_hwnd])
            
            if not target_hwnd:
                return False
                
            # 获取窗口线程ID
            thread_id, _ = win32process.GetWindowThreadProcessId(target_hwnd)
            
            # 准备按键消息参数
            vk_code = ord(key.upper())
            scan_code = self.get_scan_code(vk_code)
            lparam_down = 0x00000001 | (scan_code << 16)
            lparam_up = 0xC0000001 | (scan_code << 16)
            
            # 发送按键消息
            windll.user32.PostMessageW(target_hwnd, self.WM_KEYDOWN, vk_code, lparam_down)
            time.sleep(0.01)
            windll.user32.PostMessageW(target_hwnd, self.WM_KEYUP, vk_code, lparam_up)
            
            return True
            
        except Exception:
            return False
    def _send_via_directinput(self, pid, key):
        """使用DirectInput方式发送按键"""
        try:
            import pydirectinput
            
            # 查找目标窗口
            target_hwnd = None
            def enum_windows_callback(hwnd, pid_list):
                _, process_id = win32process.GetWindowThreadProcessId(hwnd)
                if process_id == pid_list[0] and win32gui.IsWindowVisible(hwnd):
                    pid_list[1] = hwnd
            
            target_hwnd = None
            win32gui.EnumWindows(enum_windows_callback, [pid, target_hwnd])
            
            if target_hwnd:
                # 获取窗口位置并点击确保焦点
                rect = win32gui.GetWindowRect(target_hwnd)
                center_x = (rect[0] + rect[2]) // 2
                center_y = (rect[1] + rect[3]) // 2
                pydirectinput.moveTo(center_x, center_y)
                pydirectinput.click()
                
            # 发送按键
            pydirectinput.keyDown(key.lower())
            pydirectinput.keyUp(key.lower())
            return True
            
        except ImportError:
            print("未安装pydirectinput库，请运行: pip install pydirectinput")
            return False
        except Exception:
            return False
    def _send_via_rawinput(self, pid, key):
        """使用RawInput方式发送按键"""
        try:
            # 定义RAWINPUT结构
            class RAWINPUT(ctypes.Structure):
                _fields_ = [
                    ('header', RAWINPUTHEADER),
                    ('data', RAWKEYBOARD)
                ]
                
            # 发送RawInput
            vk_code = ord(key.upper())
            scan_code = self.get_scan_code(vk_code)
            
            # 按下按键
            keyboard = RAWKEYBOARD(
                MakeCode=scan_code,
                Flags=0,
                Reserved=0,
                VKey=vk_code,
                Message=self.WM_KEYDOWN,
                ExtraInformation=0
            )
            raw_input = RAWINPUT(
                header=RAWINPUTHEADER(
                    dwType=RIM_TYPEKEYBOARD,
                    dwSize=ctypes.sizeof(RAWINPUT)
                ),
                data=keyboard
            )
            windll.user32.SendInput(1, ctypes.byref(raw_input), ctypes.sizeof(raw_input))
            
            # 释放按键
            keyboard.Flags = RI_KEY_BREAK
            keyboard.Message = self.WM_KEYUP
            windll.user32.SendInput(1, ctypes.byref(raw_input), ctypes.sizeof(raw_input))
            
            return True
            
        except Exception:
            return False
    def _send_via_virtual_gamepad(self, key):
        """使用虚拟游戏手柄发送按键"""
        try:
            # 映射键盘按键到游戏手柄按钮
            button_map = {
                'A': vg.XUSB_BUTTON.XUSB_GAMEPAD_A,
                'D': vg.XUSB_BUTTON.XUSB_GAMEPAD_B
            }
            
            if key.upper() in button_map:
                self.virtual_gamepad.press_button(button_map[key.upper()])
                time.sleep(0.05)
                self.virtual_gamepad.release_button(button_map[key.upper()])
                return True
            return False
            
        except Exception:
            return False
    def _send_via_hardware_emulation(self, key):
        """通过硬件设备模拟按键"""
        try:
            if not hasattr(self, 'hardware_emulator'):
                return False
                
            return self.hardware_emulator.send_key_via_arduino(key)
            
        except Exception:
            return False
    def _send_via_thread_injection(self, pid, key):
        """使用线程注入方式发送按键"""
        try:
            return self.inject_key_event(pid, key, True) and self.inject_key_event(pid, key, False)
        except Exception:
            return False
    def _send_via_postmessage(self, pid, key):
        """使用PostMessage发送按键"""
        try:
            vk_code = ord(key.upper())
            scan_code = self.get_scan_code(vk_code)
            
            # 查找目标窗口
            target_hwnds = []
            def enum_windows_callback(hwnd, pid_list):
                _, process_id = win32process.GetWindowThreadProcessId(hwnd)
                if process_id == pid_list[0] and win32gui.IsWindowVisible(hwnd):
                    pid_list[1].append(hwnd)
            
            win32gui.EnumWindows(enum_windows_callback, [pid, target_hwnds])
            
            if target_hwnds:
                for hwnd in target_hwnds:
                    try:
                        # 发送按键消息
                        lparam_down = 0x00000001 | (scan_code << 16)
                        lparam_up = 0xC0000001 | (scan_code << 16)
                        
                        win32api.PostMessage(hwnd, self.WM_KEYDOWN, vk_code, lparam_down)
                        win32api.PostMessage(hwnd, self.WM_KEYUP, vk_code, lparam_up)
                        return True
                    except:
                        continue
            return False
        except Exception:
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

    def get_scan_code(self, vk_code):
        """获取虚拟键码对应的扫描码"""
        return windll.user32.MapVirtualKeyA(vk_code, self.MAPVK_VK_TO_VSC)

    def get_foreground_window_thread_id(self):
        """获取前台窗口的线程ID"""
        hwnd = windll.user32.GetForegroundWindow()
        if hwnd:
            return win32process.GetWindowThreadProcessId(hwnd)[0]
        return 0
    def set_foreground_window(self, hwnd):
        """尝试将窗口设为前台"""
        try:
            if windll.user32.IsIconic(hwnd):
                windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            windll.user32.SetForegroundWindow(hwnd)
            return True
        except:
            return False

    def inject_dll(self, pid, dll_path):
        """向目标进程注入DLL"""
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        
        # 打开目标进程
        h_process = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        if not h_process:
            print(f"无法打开进程 {pid}, 错误: {ctypes.get_last_error()}")
            return False
            
        try:
            # 在目标进程中分配内存
            dll_path_encoded = dll_path.encode('utf-8')
            size = len(dll_path_encoded) + 1
            remote_mem = kernel32.VirtualAllocEx(h_process, None, size, VIRTUAL_MEM, PAGE_READWRITE)
            if not remote_mem:
                print(f"无法在进程 {pid} 中分配内存, 错误: {ctypes.get_last_error()}")
                return False
                
            # 写入DLL路径到目标进程
            written = w.DWORD(0)
            if not kernel32.WriteProcessMemory(h_process, remote_mem, dll_path_encoded, size, ctypes.byref(written)):
                print(f"无法写入进程 {pid} 内存, 错误: {ctypes.get_last_error()}")
                return False
                
            # 获取LoadLibraryA地址
            load_lib = kernel32.GetProcAddress(kernel32.GetModuleHandleA(b"kernel32.dll"), b"LoadLibraryA")
            if not load_lib:
                print("无法获取LoadLibraryA地址")
                return False
                
            # 创建远程线程执行LoadLibrary
            thread_id = w.DWORD(0)
            h_thread = kernel32.CreateRemoteThread(
                h_process, None, 0, load_lib, remote_mem, 0, ctypes.byref(thread_id))
                
            if not h_thread:
                print(f"无法创建远程线程, 错误: {ctypes.get_last_error()}")
                return False
                
            # 等待线程完成
            kernel32.WaitForSingleObject(h_thread, 5000)
            
            # 清理
            kernel32.VirtualFreeEx(h_process, remote_mem, 0, 0x8000)  # MEM_RELEASE
            
            return True
            
        finally:
            kernel32.CloseHandle(h_process)

    def send_key_via_memory(self, pid, key):
        """通过直接内存写入模拟按键"""
        try:
            # 获取目标进程句柄
            h_process = win32api.OpenProcess(
                win32con.PROCESS_VM_OPERATION | win32con.PROCESS_VM_WRITE | win32con.PROCESS_VM_READ,
                False, pid)
            if not h_process:
                print(f"无法打开进程 {pid}")
                return False
                
            # 查找目标窗口
            target_hwnd = None
            def enum_windows_callback(hwnd, pid_list):
                _, process_id = win32process.GetWindowThreadProcessId(hwnd)
                if process_id == pid_list[0] and win32gui.IsWindowVisible(hwnd):
                    pid_list[1] = hwnd
            
            target_hwnd = None
            win32gui.EnumWindows(enum_windows_callback, [pid, target_hwnd])
            
            if not target_hwnd:
                print(f"未找到进程 {pid} 的窗口")
                return False
                
            # 获取窗口线程ID
            thread_id, _ = win32process.GetWindowThreadProcessId(target_hwnd)
            
            # 获取输入上下文
            hkl = windll.user32.GetKeyboardLayout(thread_id)
            
            # 准备按键消息参数
            vk_code = ord(key.upper())
            scan_code = self.get_scan_code(vk_code)
            lparam_down = 0x00000001 | (scan_code << 16)
            lparam_up = 0xC0000001 | (scan_code << 16)
            
            # 发送按键消息
            windll.user32.PostMessageW(target_hwnd, self.WM_KEYDOWN, vk_code, lparam_down)
            time.sleep(0.01)  # 短暂延迟
            windll.user32.PostMessageW(target_hwnd, self.WM_KEYUP, vk_code, lparam_up)
            
            return True
            
        except Exception as e:
            print(f"内存写入方法失败: {e}")
            return False

    def analyze_target_process(self, pid):
        """分析目标程序的输入处理机制"""
        return self.input_analyzer.analyze(pid)
        


    def send_via_directinput(self, pid, key):
        """使用DirectInput方式发送按键"""
        try:
            import pydirectinput
            pydirectinput.keyDown(key.lower())
            pydirectinput.keyUp(key.lower())
            return True
        except Exception as e:
            print(f"DirectInput方法失败: {e}")
            return False
            
    def send_via_rawinput(self, pid, key):
        """使用RawInput方式发送按键"""
        try:
            # 获取扫描码
            vk_code = ord(key.upper())
            scan_code = self.get_scan_code(vk_code)
            
            # 准备RawInput数据结构
            raw_input = RAWINPUT()
            raw_input.header.dwType = RIM_TYPEKEYBOARD
            raw_input.data.keyboard.MakeCode = scan_code
            raw_input.data.keyboard.Flags = 0  # 按下
            raw_input.data.keyboard.Reserved = 0
            raw_input.data.keyboard.ExtraInformation = 0
            raw_input.data.keyboard.Message = WM_KEYDOWN
            raw_input.data.keyboard.VKey = vk_code
            
            # 发送RawInput
            result = windll.user32.SendInput(1, ctypes.byref(raw_input), ctypes.sizeof(raw_input))
            return result > 0
            
        except Exception as e:
            print(f"RawInput方法失败: {e}")
            return False
            
    def send_via_gamepad(self, key):
        """使用虚拟游戏手柄发送按键"""
        try:
            self.virtual_gamepad.press_button(key)
            time.sleep(0.05)  # 短暂延迟
            self.virtual_gamepad.release_button(key)
            return True
        except Exception as e:
            print(f"游戏手柄模拟失败: {e}")
            return False
            
    def send_via_default(self, pid, key):
        """使用默认方法发送按键"""
        # 这里可以保留原来的send_key_to_process的实现
        pass


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


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if __name__ == '__main__':
    if not is_admin():
        # 重新以管理员权限运行
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit()
        
    # 初始化系统
    initialize_system()
    
    app = QApplication(sys.argv)
    manager = ProcessManager()
    manager.show()
    sys.exit(app.exec_())