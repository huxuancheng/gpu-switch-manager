#!/usr/bin/env python3
# GPU 直通控制面板 - 完整版（含托盘、配置修复、日志导出、VM启动等功能）

import os
import gi
gi.require_version('Gtk', '3.0')
try:
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import AppIndicator3
    HAS_INDICATOR = True
except:
    HAS_INDICATOR = False
from gi.repository import Gtk, GLib, Gdk
import subprocess
import threading
import sys
import json
from pathlib import Path
from datetime import datetime

# 检测系统 DPI 和缩放设置，自适应 UI 大小
def detect_scale_factor():
    """检测系统缩放因子"""
    gdk_scale = os.environ.get('GDK_SCALE', '1.0')
    try:
        scale = float(gdk_scale)
    except ValueError:
        scale = 1.0
    
    try:
        result = subprocess.run(
            ['gsettings', 'get', 'org.gnome.desktop.interface', 'text-scaling-factor'],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            gsettings_scale = float(result.stdout.strip())
            if gsettings_scale > 0:
                scale = gsettings_scale
    except:
        pass
    
    scale = max(0.8, min(2.5, scale))
    return scale

SCALE_FACTOR = detect_scale_factor()

# 配置文件路径
CONFIG_FILE = Path.home() / ".gpu-switcher" / "config.json"
HISTORY_FILE = Path.home() / ".gpu-switcher" / "history.json"
LOG_FILE = Path.home() / ".gpu-switcher" / "operation.log"

class GPUSwitcher(Gtk.Window):
    def __init__(self):
        super().__init__(title="GPU 直通控制面板")
        self.set_icon_name("video-display")
        
        # 窗口大小
        min_width = int(900 * SCALE_FACTOR)
        min_height = int(600 * SCALE_FACTOR)
        default_width = int(1100 * SCALE_FACTOR)
        default_height = int(750 * SCALE_FACTOR)
        
        self.set_size_request(min_width, min_height)
        self.set_default_size(default_width, default_height)
        self.set_border_width(int(15 * SCALE_FACTOR))
        self.set_resizable(True)
        self.set_position(Gtk.WindowPosition.CENTER)

        # 配置路径
        self.script_dir = Path(__file__).parent
        self.switch_script = self.script_dir / "gpu-switch-v3"
        for script_name in ["gpu-switch-v3", "gpu-switch", "gpu-switch-v2"]:
            if self.switch_script.exists():
                break
            self.switch_script = self.script_dir / script_name

        # 线程锁和状态
        self.log_lock = threading.Lock()
        self.operation_in_progress = False
        self.current_mode = "unknown"

        # NVIDIA 设备 ID
        self.nvidia_devices = {
            'vga': '10de:2206',
            'audio': '10de:1aef'
        }

        # 加载配置
        self.load_config()
        self.load_history()

        # 创建系统托盘
        self.indicator = None
        if HAS_INDICATOR:
            self.create_indicator()

        # 初始化UI
        self.setup_ui()
        
        # 设置快捷键（UI创建后）
        self.setup_shortcuts()
        
        self.update_status()
        self.update_gpu_info()

        # 定时刷新
        GLib.timeout_add(30000, self.auto_refresh_status)

    def load_config(self):
        """加载配置"""
        self.config = {
            'vm_command': '',
            'vm_close_command': '',
            'auto_start_vm': False,
            'auto_switch_back': False,
            'show_in_tray': True,
            'minimize_to_tray': False
        }
        
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.config.update(json.load(f))
            except:
                pass

    def save_config(self):
        """保存配置"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except:
            self.log("保存配置失败")

    def load_history(self):
        """加载历史记录"""
        self.history = []
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
            except:
                pass

    def save_history(self):
        """保存历史记录"""
        try:
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except:
            pass

    def add_history(self, action, success, details=""):
        """添加历史记录"""
        record = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'action': action,
            'success': success,
            'details': details
        }
        self.history.append(record)
        # 只保留最近100条
        if len(self.history) > 100:
            self.history = self.history[-100:]
        self.save_history()
        self.update_history_display()

    def create_indicator(self):
        """创建系统托盘图标"""
        try:
            self.indicator = AppIndicator3.Indicator.new(
                "gpu-switcher",
                "video-display",
                AppIndicator3.IndicatorCategory.APPLICATION_STATUS
            )
            self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            self.update_indicator_icon()
            
            # 创建菜单
            menu = Gtk.Menu()
            
            # 状态项
            self.indicator_status = Gtk.MenuItem("状态: 检测中...")
            self.indicator_status.set_sensitive(False)
            menu.append(self.indicator_status)
            
            # 分隔线
            menu.append(Gtk.SeparatorMenuItem())
            
            # 切换到正常模式
            item_normal = Gtk.MenuItem("切换到正常模式")
            item_normal.connect("activate", self.on_switch_from_tray, "normal")
            menu.append(item_normal)
            
            # 切换到直通模式
            item_pt = Gtk.MenuItem("切换到直通模式")
            item_pt.connect("activate", self.on_switch_from_tray, "passthrough")
            menu.append(item_pt)
            
            # 分隔线
            menu.append(Gtk.SeparatorMenuItem())
            
            # 显示主窗口
            item_show = Gtk.MenuItem("显示主窗口")
            item_show.connect("activate", self.on_show_window)
            menu.append(item_show)
            
            # 分隔线
            menu.append(Gtk.SeparatorMenuItem())
            
            # 退出
            item_quit = Gtk.MenuItem("退出")
            item_quit.connect("activate", self.on_quit)
            menu.append(item_quit)
            
            menu.show_all()
            self.indicator.set_menu(menu)
        except Exception as e:
            self.log(f"创建托盘失败: {e}")

    def update_indicator_icon(self):
        """更新托盘图标"""
        if not self.indicator:
            return
        
        if self.current_mode == "normal":
            # 绿色图标
            self.indicator.set_icon("video-display")
        elif self.current_mode == "passthrough":
            # 橙色图标
            self.indicator.set_icon("video-display")
        else:
            self.indicator.set_icon("video-display")

    def on_switch_from_tray(self, item, mode):
        """从托盘切换模式"""
        self.on_show_window(None)
        if mode == "normal":
            self.on_switch_normal(None)
        else:
            self.on_switch_passthrough(None)

    def on_show_window(self, item):
        """显示主窗口"""
        self.show_all()
        self.present()

    def on_quit(self, item):
        """退出程序"""
        if self.config.get('minimize_to_tray', False) and not item:
            self.hide()
        else:
            Gtk.main_quit()

    def setup_shortcuts(self):
        """设置快捷键"""
        # 刷新状态: F5
        if hasattr(self, 'refresh_btn'):
            accel_group = Gtk.AccelGroup()
            self.add_accel_group(accel_group)
            refresh_key, refresh_mod = Gtk.accelerator_parse("F5")
            self.refresh_btn.add_accelerator("clicked", accel_group, refresh_key, refresh_mod, Gtk.AccelFlags.VISIBLE)

    def setup_ui(self):
        """设置UI"""
        self.apply_css()
        
        # 主窗口 - 使用Notebook分页
        notebook = Gtk.Notebook()
        notebook.set_vexpand(True)
        notebook.set_hexpand(True)
        self.add(notebook)
        
        # 创建各个页面
        self.create_main_page(notebook)
        self.create_config_page(notebook)
        self.create_info_page(notebook)
        self.create_history_page(notebook)
        self.create_settings_page(notebook)

    def create_main_page(self, notebook):
        """创建主页面"""
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=int(15 * SCALE_FACTOR))
        main_box.set_margin_start(int(10 * SCALE_FACTOR))
        main_box.set_margin_end(int(10 * SCALE_FACTOR))
        main_box.set_margin_top(int(10 * SCALE_FACTOR))
        main_box.set_margin_bottom(int(10 * SCALE_FACTOR))
        
        label = Gtk.Label(label="🖥️ 主控台")
        notebook.append_page(main_box, label)
        
        # 左侧面板
        left_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=int(10 * SCALE_FACTOR))
        left_panel.set_hexpand(True)
        left_panel.set_vexpand(True)
        main_box.pack_start(left_panel, True, True, 0)
        
        # 标题
        title = Gtk.Label(label="")
        title.set_markup("<big><b>🖥️ GPU 直通控制面板</b></big>")
        left_panel.pack_start(title, False, False, 0)
        
        # 状态卡片
        self.status_frame = Gtk.Frame(label="当前状态")
        self.status_frame.get_style_context().add_class("status-card")
        left_panel.pack_start(self.status_frame, False, False, 0)
        
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=int(8 * SCALE_FACTOR))
        status_box.set_margin_top(int(10 * SCALE_FACTOR))
        status_box.set_margin_start(int(15 * SCALE_FACTOR))
        status_box.set_margin_end(int(15 * SCALE_FACTOR))
        status_box.set_margin_bottom(int(10 * SCALE_FACTOR))
        self.status_frame.add(status_box)
        
        self.mode_label = Gtk.Label(label="模式: 检测中...")
        self.mode_label.set_halign(Gtk.Align.START)
        status_box.pack_start(self.mode_label, False, False, 0)
        
        self.driver_label = Gtk.Label(label="驱动: 检测中...")
        self.driver_label.set_halign(Gtk.Align.START)
        status_box.pack_start(self.driver_label, False, False, 0)
        
        self.iommu_label = Gtk.Label(label="IOMMU: 检测中...")
        self.iommu_label.set_halign(Gtk.Align.START)
        status_box.pack_start(self.iommu_label, False, False, 0)
        
        self.config_label = Gtk.Label(label="配置: 检测中...")
        self.config_label.set_halign(Gtk.Align.START)
        status_box.pack_start(self.config_label, False, False, 0)
        
        # 刷新按钮
        self.refresh_btn = Gtk.Button.new_with_label("🔄 刷新状态")
        self.refresh_btn.connect("clicked", self.on_refresh)
        status_box.pack_start(self.refresh_btn, False, False, int(5 * SCALE_FACTOR))
        
        # 日志区域
        log_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=int(5 * SCALE_FACTOR))
        log_box.set_vexpand(True)
        left_panel.pack_start(log_box, True, True, 0)
        
        log_frame = Gtk.Frame(label="操作日志")
        log_frame.get_style_context().add_class("log-card")
        log_frame.set_vexpand(True)
        log_box.pack_start(log_frame, True, True, 0)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(int(200 * SCALE_FACTOR))
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        log_frame.add(scrolled)
        
        self.log_buffer = Gtk.TextBuffer()
        log_view = Gtk.TextView(buffer=self.log_buffer, editable=False, wrap_mode=Gtk.WrapMode.WORD)
        log_view.get_style_context().add_class("log-view")
        scrolled.add(log_view)
        
        # 日志操作按钮
        log_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=int(5 * SCALE_FACTOR))
        log_box.pack_start(log_btn_box, False, False, 0)
        
        export_btn = Gtk.Button.new_with_label("📥 导出日志")
        export_btn.connect("clicked", self.on_export_log)
        log_btn_box.pack_start(export_btn, True, True, 0)
        
        clear_btn = Gtk.Button.new_with_label("🗑️ 清空日志")
        clear_btn.connect("clicked", self.on_clear_log)
        log_btn_box.pack_start(clear_btn, True, True, 0)
        
        # 右侧面板
        right_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=int(10 * SCALE_FACTOR))
        right_panel.set_hexpand(True)
        right_panel.set_vexpand(True)
        main_box.pack_start(right_panel, True, True, 0)
        
        # 操作按钮
        actions_frame = Gtk.Frame(label="切换模式")
        actions_frame.get_style_context().add_class("actions-card")
        right_panel.pack_start(actions_frame, False, False, 0)
        
        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=int(20 * SCALE_FACTOR))
        actions_box.set_margin_top(int(15 * SCALE_FACTOR))
        actions_box.set_margin_bottom(int(15 * SCALE_FACTOR))
        actions_box.set_margin_start(int(20 * SCALE_FACTOR))
        actions_box.set_margin_end(int(20 * SCALE_FACTOR))
        actions_frame.add(actions_box)
        
        self.normal_btn = Gtk.Button.new_with_label("🟢 正常模式\n(NVIDIA)")
        self.normal_btn.get_style_context().add_class("mode-button-normal")
        self.normal_btn.connect("clicked", self.on_switch_normal)
        actions_box.pack_start(self.normal_btn, True, True, 0)
        
        self.pt_btn = Gtk.Button.new_with_label("🟠 直通模式\n(VFIO)")
        self.pt_btn.get_style_context().add_class("mode-button-passthrough")
        self.pt_btn.connect("clicked", self.on_switch_passthrough)
        actions_box.pack_start(self.pt_btn, True, True, 0)
        
        # 虚拟机操作
        vm_frame = Gtk.Frame(label="虚拟机")
        vm_frame.get_style_context().add_class("vm-card")
        right_panel.pack_start(vm_frame, False, False, 0)
        
        vm_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=int(10 * SCALE_FACTOR))
        vm_box.set_margin_top(int(10 * SCALE_FACTOR))
        vm_box.set_margin_bottom(int(10 * SCALE_FACTOR))
        vm_box.set_margin_start(int(15 * SCALE_FACTOR))
        vm_box.set_margin_end(int(15 * SCALE_FACTOR))
        vm_frame.add(vm_box)
        
        self.vm_btn = Gtk.Button.new_with_label("🚀 启动虚拟机")
        self.vm_btn.connect("clicked", self.on_start_vm)
        vm_box.pack_start(self.vm_btn, True, True, 0)
        
        self.vm_close_btn = Gtk.Button.new_with_label("⏹️ 关闭虚拟机")
        self.vm_close_btn.connect("clicked", self.on_stop_vm)
        vm_box.pack_start(self.vm_close_btn, True, True, 0)
        
        # 警告
        warning_frame = Gtk.Frame()
        warning_frame.get_style_context().add_class("warning-card")
        right_panel.pack_start(warning_frame, False, False, 0)
        
        warning_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=int(8 * SCALE_FACTOR))
        warning_box.set_margin_top(int(10 * SCALE_FACTOR))
        warning_box.set_margin_bottom(int(10 * SCALE_FACTOR))
        warning_box.set_margin_start(int(15 * SCALE_FACTOR))
        warning_box.set_margin_end(int(15 * SCALE_FACTOR))
        warning_frame.add(warning_box)
        
        warning_label = Gtk.Label(label="")
        warning_label.set_markup("<span foreground='#FF6B35'>⚠️ 注意事项</span>")
        warning_label.set_halign(Gtk.Align.START)
        warning_box.pack_start(warning_label, False, False, 0)
        
        self.warning_text = Gtk.Label(label="")
        self.warning_text.set_halign(Gtk.Align.START)
        self.warning_text.set_line_wrap(True)
        warning_box.pack_start(self.warning_text, False, False, 0)
        
        self.warning_text.set_markup(
            "• <b>切换后系统将自动重启</b>\n"
            "• 切换前请保存所有工作\n"
            "• 确保没有应用程序正在使用 GPU\n\n"
            "快捷键: F5 刷新状态"
        )
        
        GLib.idle_add(lambda: (self.log("🚀 GPU 直通控制面板已启动"), False))

    def create_config_page(self, notebook):
        """创建配置页面"""
        config_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=int(10 * SCALE_FACTOR))
        config_box.set_margin_start(int(10 * SCALE_FACTOR))
        config_box.set_margin_end(int(10 * SCALE_FACTOR))
        config_box.set_margin_top(int(10 * SCALE_FACTOR))
        config_box.set_margin_bottom(int(10 * SCALE_FACTOR))
        
        label = Gtk.Label(label="⚙️ 配置检查")
        notebook.append_page(config_box, label)
        
        # 检查按钮
        check_btn = Gtk.Button.new_with_label("🔍 检查配置")
        check_btn.get_style_context().add_class("check-button")
        check_btn.connect("clicked", self.on_check_config)
        config_box.pack_start(check_btn, False, False, 0)
        
        repair_btn = Gtk.Button.new_with_label("🔧 自动修复")
        repair_btn.get_style_context().add_class("repair-button")
        repair_btn.connect("clicked", self.on_repair_config)
        config_box.pack_start(repair_btn, False, False, 0)
        
        # 配置检查结果
        result_frame = Gtk.Frame(label="检查结果")
        result_frame.set_vexpand(True)
        config_box.pack_start(result_frame, True, True, 0)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        result_frame.add(scrolled)
        
        self.config_result_buffer = Gtk.TextBuffer()
        result_view = Gtk.TextView(buffer=self.config_result_buffer, editable=False, wrap_mode=Gtk.WrapMode.WORD)
        result_view.get_style_context().add_class("log-view")
        scrolled.add(result_view)

    def create_info_page(self, notebook):
        """创建GPU信息页面"""
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=int(10 * SCALE_FACTOR))
        info_box.set_margin_start(int(10 * SCALE_FACTOR))
        info_box.set_margin_end(int(10 * SCALE_FACTOR))
        info_box.set_margin_top(int(10 * SCALE_FACTOR))
        info_box.set_margin_bottom(int(10 * SCALE_FACTOR))
        
        label = Gtk.Label(label="📊 GPU 信息")
        notebook.append_page(info_box, label)
        
        refresh_btn = Gtk.Button.new_with_label("🔄 刷新信息")
        refresh_btn.connect("clicked", self.update_gpu_info)
        info_box.pack_start(refresh_btn, False, False, 0)
        
        # GPU 信息
        info_frame = Gtk.Frame(label="详细信息")
        info_frame.set_vexpand(True)
        info_box.pack_start(info_frame, True, True, 0)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        info_frame.add(scrolled)
        
        self.gpu_info_buffer = Gtk.TextBuffer()
        info_view = Gtk.TextView(buffer=self.gpu_info_buffer, editable=False, wrap_mode=Gtk.WrapMode.WORD)
        info_view.get_style_context().add_class("log-view")
        scrolled.add(info_view)

    def create_history_page(self, notebook):
        """创建历史页面"""
        history_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=int(10 * SCALE_FACTOR))
        history_box.set_margin_start(int(10 * SCALE_FACTOR))
        history_box.set_margin_end(int(10 * SCALE_FACTOR))
        history_box.set_margin_top(int(10 * SCALE_FACTOR))
        history_box.set_margin_bottom(int(10 * SCALE_FACTOR))
        
        label = Gtk.Label(label="📜 操作历史")
        notebook.append_page(history_box, label)
        
        clear_btn = Gtk.Button.new_with_label("🗑️ 清空历史")
        clear_btn.connect("clicked", self.on_clear_history)
        history_box.pack_start(clear_btn, False, False, 0)
        
        # 统计信息
        stats_frame = Gtk.Frame(label="统计")
        history_box.pack_start(stats_frame, False, False, 0)
        
        stats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=int(20 * SCALE_FACTOR))
        stats_box.set_margin_top(int(10 * SCALE_FACTOR))
        stats_box.set_margin_bottom(int(10 * SCALE_FACTOR))
        stats_box.set_margin_start(int(15 * SCALE_FACTOR))
        stats_box.set_margin_end(int(15 * SCALE_FACTOR))
        stats_frame.add(stats_box)
        
        self.stats_label = Gtk.Label(label="总操作: 0 | 成功: 0 | 失败: 0")
        stats_box.pack_start(self.stats_label, True, True, 0)
        
        # 历史列表
        list_frame = Gtk.Frame(label="历史记录")
        list_frame.set_vexpand(True)
        history_box.pack_start(list_frame, True, True, 0)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        list_frame.add(scrolled)
        
        self.history_buffer = Gtk.TextBuffer()
        history_view = Gtk.TextView(buffer=self.history_buffer, editable=False, wrap_mode=Gtk.WrapMode.WORD)
        history_view.get_style_context().add_class("log-view")
        scrolled.add(history_view)
        
        self.update_history_display()

    def create_settings_page(self, notebook):
        """创建设置页面"""
        settings_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=int(15 * SCALE_FACTOR))
        settings_box.set_margin_start(int(15 * SCALE_FACTOR))
        settings_box.set_margin_end(int(15 * SCALE_FACTOR))
        settings_box.set_margin_top(int(15 * SCALE_FACTOR))
        settings_box.set_margin_bottom(int(15 * SCALE_FACTOR))
        
        label = Gtk.Label(label="🎛️ 设置")
        notebook.append_page(settings_box, label)
        
        # 虚拟机设置
        vm_frame = Gtk.Frame(label="虚拟机设置")
        settings_box.pack_start(vm_frame, False, False, 0)
        
        vm_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=int(10 * SCALE_FACTOR))
        vm_box.set_margin_top(int(10 * SCALE_FACTOR))
        vm_box.set_margin_start(int(15 * SCALE_FACTOR))
        vm_box.set_margin_end(int(15 * SCALE_FACTOR))
        vm_box.set_margin_bottom(int(10 * SCALE_FACTOR))
        vm_frame.add(vm_box)
        
        # VM 启动命令
        cmd_label = Gtk.Label(label="VM 启动命令:")
        cmd_label.set_halign(Gtk.Align.START)
        vm_box.pack_start(cmd_label, False, False, 0)
        
        self.vm_cmd_entry = Gtk.Entry()
        self.vm_cmd_entry.set_text(self.config.get('vm_command', ''))
        self.vm_cmd_entry.set_placeholder_text("例如: virsh start win10-gpu")
        vm_box.pack_start(self.vm_cmd_entry, True, True, 0)
        
        # VM 关闭命令
        close_label = Gtk.Label(label="VM 关闭命令:")
        close_label.set_halign(Gtk.Align.START)
        vm_box.pack_start(close_label, False, False, 0)
        
        self.vm_close_entry = Gtk.Entry()
        self.vm_close_entry.set_text(self.config.get('vm_close_command', ''))
        self.vm_close_entry.set_placeholder_text("例如: virsh shutdown win10-gpu")
        vm_box.pack_start(self.vm_close_entry, True, True, 0)
        
        # 自动选项
        self.auto_start_vm_check = Gtk.CheckButton(label="切换到直通模式后自动启动 VM")
        self.auto_start_vm_check.set_active(self.config.get('auto_start_vm', False))
        vm_box.pack_start(self.auto_start_vm_check, False, False, 0)
        
        self.auto_switch_back_check = Gtk.CheckButton(label="关闭 VM 后自动切换回正常模式")
        self.auto_switch_back_check.set_active(self.config.get('auto_switch_back', False))
        vm_box.pack_start(self.auto_switch_back_check, False, False, 0)
        
        # 界面设置
        ui_frame = Gtk.Frame(label="界面设置")
        settings_box.pack_start(ui_frame, False, False, 0)
        
        ui_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=int(10 * SCALE_FACTOR))
        ui_box.set_margin_top(int(10 * SCALE_FACTOR))
        ui_box.set_margin_start(int(15 * SCALE_FACTOR))
        ui_box.set_margin_end(int(15 * SCALE_FACTOR))
        ui_box.set_margin_bottom(int(10 * SCALE_FACTOR))
        ui_frame.add(ui_box)
        
        self.minimize_to_tray_check = Gtk.CheckButton(label="关闭窗口时最小化到托盘")
        self.minimize_to_tray_check.set_active(self.config.get('minimize_to_tray', False))
        ui_box.pack_start(self.minimize_to_tray_check, False, False, 0)
        
        # 保存按钮
        save_btn = Gtk.Button.new_with_label("💾 保存设置")
        save_btn.get_style_context().add_class("mode-button-normal")
        save_btn.connect("clicked", self.on_save_settings)
        settings_box.pack_start(save_btn, False, False, 0)

    def apply_css(self):
        """应用CSS样式"""
        base_font_size = int(11 * SCALE_FACTOR)
        medium_font_size = int(12 * SCALE_FACTOR)
        large_font_size = int(13 * SCALE_FACTOR)
        xl_font_size = int(14 * SCALE_FACTOR)
        
        border_radius = int(8 * SCALE_FACTOR)
        
        css = f"""
        /* 主窗口 */
        window {{
            background-color: @theme_bg_color;
        }}
        
        /* 状态卡片 */
        .status-card {{
            border-radius: {border_radius}px;
            border: 1px solid rgba(0,0,0,0.1);
        }}
        
        /* 操作按钮卡片 */
        .actions-card {{
            border-radius: {border_radius}px;
            border: 1px solid rgba(0,0,0,0.1);
        }}
        
        /* 正常模式按钮 */
        .mode-button-normal {{
            background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
            color: white;
            border-radius: {int(12 * SCALE_FACTOR)}px;
            padding: {int(12 * SCALE_FACTOR)}px {int(24 * SCALE_FACTOR)}px;
            font-weight: bold;
            font-size: {xl_font_size}px;
        }}
        
        .mode-button-normal:hover {{
            background: linear-gradient(135deg, #5CBF60 0%, #55B059 100%);
        }}
        
        /* 直通模式按钮 */
        .mode-button-passthrough {{
            background: linear-gradient(135deg, #FF9800 0%, #F57C00 100%);
            color: white;
            border-radius: {int(12 * SCALE_FACTOR)}px;
            padding: {int(12 * SCALE_FACTOR)}px {int(24 * SCALE_FACTOR)}px;
            font-weight: bold;
            font-size: {xl_font_size}px;
        }}
        
        .mode-button-passthrough:hover {{
            background: linear-gradient(135deg, #FFA830 0%, #FF8C00 100%);
        }}
        
        /* VM卡片 */
        .vm-card {{
            border-radius: {border_radius}px;
            border: 1px solid rgba(0,0,0,0.1);
        }}
        
        /* 检查按钮 */
        .check-button {{
            background: linear-gradient(135deg, #2196F3 0%, #1976D2 100%);
            color: white;
            border-radius: {int(8 * SCALE_FACTOR)}px;
            padding: {int(10 * SCALE_FACTOR)}px {int(20 * SCALE_FACTOR)}px;
            font-weight: bold;
        }}
        
        .check-button:hover {{
            background: linear-gradient(135deg, #42A5F5 0%, #1E88E5 100%);
        }}
        
        /* 修复按钮 */
        .repair-button {{
            background: linear-gradient(135deg, #FF9800 0%, #F57C00 100%);
            color: white;
            border-radius: {int(8 * SCALE_FACTOR)}px;
            padding: {int(10 * SCALE_FACTOR)}px {int(20 * SCALE_FACTOR)}px;
            font-weight: bold;
        }}
        
        .repair-button:hover {{
            background: linear-gradient(135deg, #FFA726 0%, #FB8C00 100%);
        }}
        
        /* 警告卡片 */
        .warning-card {{
            border-radius: {border_radius}px;
            border: 1px solid rgba(255, 107, 53, 0.3);
            background-color: rgba(255, 107, 53, 0.05);
        }}
        
        /* 日志卡片 */
        .log-card {{
            border-radius: {border_radius}px;
            border: 1px solid rgba(0,0,0,0.1);
        }}
        
        .log-view {{
            font-family: 'Monospace', monospace;
            font-size: {base_font_size}px;
            color: rgba(0,0,0,0.8);
        }}
        
        /* Frame标签 */
        frame > label {{
            font-weight: bold;
            font-size: {large_font_size}px;
            color: rgba(0,0,0,0.6);
        }}
        
        * {{
            font-size: {int(15 * SCALE_FACTOR)}px;
        }}
        """
        
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def log(self, message):
        """添加日志"""
        with self.log_lock:
            end_iter = self.log_buffer.get_end_iter()
            timestamp = GLib.DateTime.new_now_local().format("%H:%M:%S")
            self.log_buffer.insert(end_iter, f"[{timestamp}] {message}\n")
            self.log_buffer.place_cursor(end_iter)
            
            # 写入文件
            try:
                LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(LOG_FILE, 'a', encoding='utf-8') as f:
                    f.write(f"[{timestamp}] {message}\n")
            except:
                pass

    def run_command(self, cmd, timeout=10):
        """执行命令"""
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return result.returncode == 0, result.stdout, result.stderr
        except Exception as e:
            return False, "", str(e)

    def get_gpu_status(self):
        """获取GPU状态"""
        _, driver_output, _ = self.run_command(f"lspci -nnk -d {self.nvidia_devices['vga']} | grep 'Kernel driver'")
        _, module_output, _ = self.run_command("lsmod | grep -E '^nvidia |^vfio'")
        _, iommu_output, _ = self.run_command("test -d /sys/kernel/iommu_groups && echo 'enabled'")
        config_status = self.check_config_files_status()
        return driver_output, module_output, iommu_output, config_status

    def check_config_files_status(self):
        """检查配置文件状态"""
        status = []
        
        vfio_conf = "/etc/modprobe.d/vfio.conf"
        if os.path.exists(vfio_conf):
            _, content, _ = self.run_command(f"cat {vfio_conf}")
            if "##options" in content:
                status.append("VFIO:禁用")
            elif "options vfio-pci" in content:
                status.append("VFIO:启用")
        
        blacklist_conf = "/etc/modprobe.d/blacklist-nouveau.conf"
        if os.path.exists(blacklist_conf):
            _, content, _ = self.run_command(f"cat {blacklist_conf}")
            if "^blacklist nouveau" in content:
                status.append("黑名单:启用")
        
        grub_conf = "/etc/default/grub"
        if os.path.exists(grub_conf):
            _, content, _ = self.run_command(f"cat {grub_conf}")
            if "intel_iommu=on" in content or "amd_iommu=on" in content:
                status.append("IOMMU:启用")
        
        return " | ".join(status) if status else "无配置"

    def parse_mode(self, driver_output, module_output):
        """解析当前模式"""
        if "vfio-pci" in driver_output:
            return "直通模式", "passthrough"
        elif "nvidia" in driver_output:
            return "正常模式", "normal"
        elif "nvidia" in module_output:
            return "正常模式", "normal"
        elif "vfio" in module_output:
            return "直通模式", "passthrough"
        return "未知", "unknown"

    def update_status(self):
        """更新状态"""
        try:
            driver_output, module_output, iommu_output, config_status = self.get_gpu_status()
            mode, mode_type = self.parse_mode(driver_output, module_output)
            self.current_mode = mode_type
            
            colors = {'normal': '#4CAF50', 'passthrough': '#FF9800', 'unknown': '#757575'}
            color = colors.get(mode_type, colors['unknown'])
            
            self.mode_label.set_markup(f"模式: <span foreground='{color}'><b>{mode}</b></span>")
            self.driver_label.set_text(f"驱动: {driver_output.strip() if driver_output.strip() else '无'}")
            self.iommu_label.set_markup(f"IOMMU: <span foreground='green'>已启用</span>" if iommu_output.strip() == 'enabled' else "IOMMU: <span foreground='red'>未启用</span>")
            self.config_label.set_text(f"配置: {config_status}")
            
            self.update_buttons(mode_type)
            self.update_indicator_icon()
            self.update_indicator_status()
            
        except Exception as e:
            self.log(f"更新状态失败: {e}")

    def update_indicator_status(self):
        """更新托盘状态文本"""
        if self.indicator:
            mode_name = "正常模式" if self.current_mode == "normal" else "直通模式" if self.current_mode == "passthrough" else "未知"
            self.indicator_status.set_label(f"状态: {mode_name}")

    def update_buttons(self, current_mode):
        """更新按钮状态"""
        self.normal_btn.get_style_context().remove_class("button-active")
        self.normal_btn.get_style_context().remove_class("button-inactive")
        self.pt_btn.get_style_context().remove_class("button-active")
        self.pt_btn.get_style_context().remove_class("button-inactive")
        
        if current_mode == "normal":
            self.normal_btn.set_sensitive(False)
            self.normal_btn.set_label("✅ 正常模式\n(NVIDIA)")
            self.normal_btn.get_style_context().add_class("button-active")
            self.pt_btn.set_sensitive(True)
            self.pt_btn.set_label("🟠 直通模式\n(VFIO)")
            self.pt_btn.get_style_context().add_class("button-inactive")
        elif current_mode == "passthrough":
            self.normal_btn.set_sensitive(True)
            self.normal_btn.set_label("🟢 正常模式\n(NVIDIA)")
            self.normal_btn.get_style_context().add_class("button-inactive")
            self.pt_btn.set_sensitive(False)
            self.pt_btn.set_label("✅ 直通模式\n(VFIO)")
            self.pt_btn.get_style_context().add_class("button-active")
        else:
            self.normal_btn.set_sensitive(True)
            self.normal_btn.set_label("🟢 正常模式\n(NVIDIA)")
            self.pt_btn.set_sensitive(True)
            self.pt_btn.set_label("🟠 直通模式\n(VFIO)")

    def update_gpu_info(self):
        """更新GPU信息"""
        info = "=== GPU 设备信息 ===\n\n"
        
        # PCI 设备信息
        success, output, _ = self.run_command(f"lspci -nn -d {self.nvidia_devices['vga']}")
        if success:
            info += f"VGA 设备:\n{output}\n"
        
        # 驱动版本
        success, output, _ = self.run_command("nvidia-smi --query-gpu=driver_version,name --format=csv,noheader")
        if success:
            info += f"\n驱动版本:\n{output}"
        else:
            info += "\n驱动版本: 未安装 nvidia 驱动\n"
        
        # IOMMU 组
        success, output, _ = self.run_command("find /sys/kernel/iommu_groups/ -name '0000:*' -exec basename {} \\; 2>/dev/null | sort -u")
        if success and output.strip():
            info += f"\nIOMMU 组:\n{output}"
        
        # 内核模块
        success, output, _ = self.run_command("lsmod | grep -E 'nvidia|vfio'")
        if success:
            info += f"\n已加载模块:\n{output if output.strip() else '无'}"
        
        self.gpu_info_buffer.set_text(info)

    def update_history_display(self):
        """更新历史显示"""
        total = len(self.history)
        success = sum(1 for h in self.history if h['success'])
        failed = total - success
        self.stats_label.set_text(f"总操作: {total} | 成功: {success} | 失败: {failed}")
        
        text = ""
        for record in reversed(self.history):
            status = "✓" if record['success'] else "✗"
            text += f"{status} {record['timestamp']} - {record['action']}\n"
            if record['details']:
                text += f"    {record['details']}\n"
            text += "\n"
        
        self.history_buffer.set_text(text)

    def auto_refresh_status(self):
        """自动刷新状态"""
        self.update_status()
        return True

    def on_refresh(self, button):
        """刷新状态"""
        self.log("正在刷新状态...")
        self.update_status()
        self.update_gpu_info()
        self.log("状态已刷新")

    def on_export_log(self, button):
        """导出日志"""
        dialog = Gtk.FileChooserDialog(
            "保存日志",
            self,
            Gtk.FileChooserAction.SAVE,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        )
        dialog.set_current_name(f"gpu-switch-log-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt")
        
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            path = dialog.get_filename()
            start, end = self.log_buffer.get_bounds()
            content = self.log_buffer.get_text(start, end, True)
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.log(f"✓ 日志已导出到: {path}")
            except Exception as e:
                self.log(f"✗ 导出失败: {e}")
        dialog.destroy()

    def on_clear_log(self, button):
        """清空日志"""
        self.log_buffer.set_text("")
        self.log("日志已清空")

    def on_clear_history(self, button):
        """清空历史"""
        self.history = []
        self.save_history()
        self.update_history_display()
        self.log("历史记录已清空")

    def on_save_settings(self, button):
        """保存设置"""
        self.config['vm_command'] = self.vm_cmd_entry.get_text()
        self.config['vm_close_command'] = self.vm_close_entry.get_text()
        self.config['auto_start_vm'] = self.auto_start_vm_check.get_active()
        self.config['auto_switch_back'] = self.auto_switch_back_check.get_active()
        self.config['minimize_to_tray'] = self.minimize_to_tray_check.get_active()
        self.save_config()
        self.log("✓ 设置已保存")

    def on_check_config(self, button):
        """检查配置"""
        self.log("开始检查配置...")
        results = []
        
        # 检查 IOMMU
        _, iommu_output, _ = self.run_command("test -d /sys/kernel/iommu_groups && echo 'enabled'")
        if iommu_output.strip() == 'enabled':
            results.append("✓ IOMMU 已启用")
        else:
            results.append("✗ IOMMU 未启用 - 需要在 GRUB 中添加 intel_iommu=on 或 amd_iommu=on")
        
        # 检查 VFIO 模块
        success, output, _ = self.run_command("lsmod | grep '^vfio'")
        if success and output.strip():
            results.append("✓ VFIO 模块已加载")
        else:
            results.append("✗ VFIO 模块未加载")
        
        # 检查 NVIDIA 黑名单
        if os.path.exists("/etc/modprobe.d/blacklist-nouveau.conf"):
            results.append("✓ Nouveau 黑名单已配置")
        else:
            results.append("✗ Nouveau 黑名单未配置")
        
        # 检查 VFIO 配置
        vfio_conf = "/etc/modprobe.d/vfio.conf"
        if os.path.exists(vfio_conf):
            results.append("✓ VFIO 配置文件存在")
        else:
            results.append("✗ VFIO 配置文件不存在")
        
        # 显示结果
        text = "\n".join(results)
        self.config_result_buffer.set_text(text)
        self.log("配置检查完成")

    def on_repair_config(self, button):
        """修复配置"""
        self.log("开始自动修复配置...")
        
        # 需要root权限
        dialog = Gtk.MessageDialog(
            self, Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING,
            Gtk.ButtonsType.YES_NO,
            "自动修复需要 root 权限"
        )
        dialog.format_secondary_text("这将修改系统配置文件，是否继续？")
        response = dialog.run()
        dialog.destroy()
        
        if response != Gtk.ResponseType.YES:
            return
        
        # 执行修复脚本
        repair_script = self.script_dir / "gpu-switch-repair.sh"
        if not repair_script.exists():
            self.log("✗ 修复脚本不存在")
            return
        
        cmd = f"pkexec {repair_script}"
        self.log(f"执行修复: {cmd}")
        success, output, error = self.run_command(cmd, timeout=60)
        
        if success:
            self.log("✓ 修复完成")
            self.log(output)
            self.on_check_config(None)
        else:
            self.log(f"✗ 修复失败: {error}")

    def on_start_vm(self, button):
        """启动虚拟机"""
        cmd = self.config.get('vm_command', '').strip()
        if not cmd:
            self.log("⚠️ 请先在设置中配置 VM 启动命令")
            return
        
        self.log(f"启动虚拟机: {cmd}")
        thread = threading.Thread(target=self._run_vm_command, args=(cmd,))
        thread.daemon = True
        thread.start()

    def on_stop_vm(self, button):
        """关闭虚拟机"""
        cmd = self.config.get('vm_close_command', '').strip()
        if not cmd:
            self.log("⚠️ 请先在设置中配置 VM 关闭命令")
            return
        
        self.log(f"关闭虚拟机: {cmd}")
        thread = threading.Thread(target=self._run_vm_command, args=(cmd,))
        thread.daemon = True
        thread.start()

    def _run_vm_command(self, cmd):
        """运行VM命令"""
        success, output, error = self.run_command(cmd, timeout=300)
        GLib.idle_add(lambda: self._process_vm_result(success, output, error))

    def _process_vm_result(self, success, output, error):
        """处理VM结果"""
        if success:
            self.log("✓ 操作成功")
            if output:
                self.log(output)
            if self.config.get('auto_switch_back', False) and "shutdown" in self.config.get('vm_close_command', ''):
                self.log("提示: 需要手动切换回正常模式")
        else:
            self.log(f"✗ 操作失败: {error}")

    def execute_switch(self, mode):
        """执行切换"""
        self.log(f"🔄 开始切换到{mode}模式...")
        
        try:
            script_path = str(self.switch_script)
            
            if not os.path.exists(script_path):
                self.log(f"✗ 脚本不存在: {script_path}")
                GLib.idle_add(lambda: self.restore_buttons())
                return
            
            cmd = f"pkexec {script_path} {mode} --no-confirm"
            self.log(f"执行命令: {script_path} {mode} --no-confirm")
            
            process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            for line in process.stdout:
                if line.strip():
                    self.log(line.strip())
            
            stdout, stderr = process.communicate(timeout=300)
            
            if process.returncode == 0:
                self.log("✓ 切换成功，系统将自动重启")
                self.add_history(f"切换到{mode}模式", True)
                
                if self.config.get('auto_start_vm', False) and mode == "passthrough":
                    vm_cmd = self.config.get('vm_command', '').strip()
                    if vm_cmd:
                        self.log(f"🚀 将在重启后自动启动虚拟机: {vm_cmd}")
                
                if stdout:
                    for line in stdout.split('\n'):
                        if line.strip():
                            self.log(line)
            else:
                self.log("✗ 切换失败")
                self.add_history(f"切换到{mode}模式", False, stderr)
                if stderr:
                    for line in stderr.split('\n'):
                        if line.strip():
                            self.log(line)
                GLib.idle_add(lambda: self.restore_buttons())
            
            self.log("⚠️ 系统即将重启，请保存工作")
            
        except subprocess.TimeoutExpired:
            self.log("✗ 操作超时")
            GLib.idle_add(lambda: self.restore_buttons())
        except Exception as e:
            self.log(f"✗ 执行错误: {e}")
            GLib.idle_add(lambda: self.restore_buttons())
        finally:
            self.operation_in_progress = False

    def restore_buttons(self):
        """恢复按钮"""
        self.normal_btn.set_sensitive(True)
        self.pt_btn.set_sensitive(True)

    def confirm_switch(self, mode):
        """确认切换"""
        mode_name = "正常模式 (NVIDIA)" if mode == "normal" else "直通模式 (VFIO)"
        msg_type = Gtk.MessageType.QUESTION if mode == "normal" else Gtk.MessageType.WARNING
        
        dialog = Gtk.MessageDialog(
            self, 0, msg_type, Gtk.ButtonsType.OK_CANCEL, f"切换到{mode_name}"
        )
        dialog.format_secondary_text(
            f"这将从{'直通' if mode == 'normal' else '正常'}模式切换到{mode_name}。\n\n"
            "⚠️ <b>系统将自动重启！</b>\n"
            "请保存所有未保存的工作。\n\n"
            "继续?"
        )
        
        response = dialog.run()
        dialog.destroy()
        return response == Gtk.ResponseType.OK

    def on_switch_normal(self, button):
        """切换到正常模式"""
        if self.operation_in_progress:
            self.log("⚠️ 操作进行中，请等待")
            return
        
        if not self.confirm_switch("normal"):
            return
        
        self.operation_in_progress = True
        self.normal_btn.set_sensitive(False)
        self.pt_btn.set_sensitive(False)
        
        thread = threading.Thread(target=self.execute_switch, args=("normal",))
        thread.daemon = True
        thread.start()

    def on_switch_passthrough(self, button):
        """切换到直通模式"""
        if self.operation_in_progress:
            self.log("⚠️ 操作进行中，请等待")
            return
        
        if not self.confirm_switch("passthrough"):
            return
        
        self.operation_in_progress = True
        self.normal_btn.set_sensitive(False)
        self.pt_btn.set_sensitive(False)
        
        thread = threading.Thread(target=self.execute_switch, args=("passthrough",))
        thread.daemon = True
        thread.start()

    def on_destroy(self, widget):
        """窗口关闭"""
        if self.config.get('minimize_to_tray', False) and HAS_INDICATOR:
            self.hide()
        else:
            Gtk.main_quit()

def main():
    win = GPUSwitcher()
    win.connect("delete-event", lambda w, e: (w.on_destroy(w), True))
    win.show_all()
    Gtk.main()

if __name__ == "__main__":
    main()
