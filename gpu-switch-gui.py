#!/usr/bin/env python3
# GPU 直通控制面板 - 任务栏托盘工具

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk
import subprocess
import threading
import os
import sys
from pathlib import Path

class GPUSwitcher(Gtk.Window):
    def __init__(self):
        super().__init__(title="GPU 直通控制面板")
        # 设置最小大小和默认大小
        self.set_size_request(480, 600)  # 最小大小
        self.set_default_size(500, 700)  # 默认大小
        self.set_border_width(15)
        self.set_resizable(True)
        self.set_position(Gtk.WindowPosition.CENTER)

        # 配置路径
        self.script_dir = Path(__file__).parent
        self.switch_script = self.script_dir / "gpu-switch-v3"
        if not self.switch_script.exists():
            # 回退到其他脚本
            for script_name in ["gpu-switch-v3", "gpu-switch", "gpu-switch-v2"]:
                self.switch_script = self.script_dir / script_name
                if self.switch_script.exists():
                    break

        # 线程锁
        self.log_lock = threading.Lock()
        self.operation_in_progress = False

        # NVIDIA 设备 ID (与脚本保持一致)
        self.nvidia_devices = {
            'vga': '10de:2206',
            'audio': '10de:1aef'
        }

        # 切换模式: 'reboot' (重启切换) 或 'hotplug' (热切换)
        self.switch_mode = 'reboot'

        # GPU 占用状态
        self.gpu_usage_detected = False

        self.setup_ui()
        self.update_status()

        # 启动后自动检测 GPU 占用（延迟 0.5 秒确保 UI 加载完成）
        GLib.timeout_add(500, self.auto_check_gpu_usage)

    def setup_ui(self):
        # 应用 CSS 样式
        self.apply_css()

        # 主容器
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        self.add(vbox)

        # 标题
        title_label = Gtk.Label(label="")
        title_label.set_markup("<big><b>🖥️ GPU 直通控制面板</b></big>")
        title_label.set_margin_top(5)
        title_label.set_margin_bottom(5)
        vbox.pack_start(title_label, False, False, 0)

        # 状态卡片
        self.status_frame = Gtk.Frame(label="当前状态")
        self.status_frame.get_style_context().add_class("status-card")
        vbox.pack_start(self.status_frame, False, False, 0)

        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        status_box.set_margin_top(10)
        status_box.set_margin_bottom(10)
        status_box.set_margin_start(15)
        status_box.set_margin_end(15)
        self.status_frame.add(status_box)

        self.mode_label = Gtk.Label(label="模式: 检测中...")
        self.mode_label.set_halign(Gtk.Align.START)
        self.mode_label.get_style_context().add_class("status-label")
        status_box.pack_start(self.mode_label, False, False, 0)

        self.driver_label = Gtk.Label(label="驱动: 检测中...")
        self.driver_label.set_halign(Gtk.Align.START)
        self.driver_label.get_style_context().add_class("status-label")
        status_box.pack_start(self.driver_label, False, False, 0)

        self.iommu_label = Gtk.Label(label="IOMMU: 检测中...")
        self.iommu_label.set_halign(Gtk.Align.START)
        self.iommu_label.get_style_context().add_class("status-label")
        status_box.pack_start(self.iommu_label, False, False, 0)

        self.config_label = Gtk.Label(label="配置: 检测中...")
        self.config_label.set_halign(Gtk.Align.START)
        self.config_label.get_style_context().add_class("status-label")
        status_box.pack_start(self.config_label, False, False, 0)

        # 刷新按钮
        refresh_btn = Gtk.Button.new_with_label("🔄 刷新状态")
        refresh_btn.get_style_context().add_class("refresh-button")
        refresh_btn.connect("clicked", self.on_refresh)
        status_box.pack_start(refresh_btn, False, False, 5)

        # 分隔线
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        vbox.pack_start(separator, False, False, 10)

        # 切换模式选择
        mode_frame = Gtk.Frame(label="切换方式")
        mode_frame.get_style_context().add_class("mode-card")
        vbox.pack_start(mode_frame, False, False, 0)

        mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        mode_box.set_margin_top(10)
        mode_box.set_margin_bottom(10)
        mode_box.set_margin_start(20)
        mode_box.set_margin_end(20)
        mode_frame.add(mode_box)

        self.reboot_toggle = Gtk.ToggleButton.new_with_label("🔄 重启切换 (安全)")
        self.reboot_toggle.set_size_request(180, 40)
        self.reboot_toggle.set_active(True)
        self.reboot_toggle.get_style_context().add_class("toggle-button-reboot")
        self.reboot_toggle.connect("toggled", self.on_toggle_switch_mode)
        mode_box.pack_start(self.reboot_toggle, True, True, 0)

        self.hotplug_toggle = Gtk.ToggleButton.new_with_label("⚡ 热切换 (快速)")
        self.hotplug_toggle.set_size_request(180, 40)
        self.hotplug_toggle.set_active(False)
        self.hotplug_toggle.get_style_context().add_class("toggle-button-hotplug")
        self.hotplug_toggle.connect("toggled", self.on_toggle_switch_mode)
        mode_box.pack_start(self.hotplug_toggle, True, True, 0)

        # 分隔线
        separator2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        vbox.pack_start(separator2, False, False, 10)

        # GPU 占用状态提示（启动时自动显示）
        self.gpu_usage_label = Gtk.Label(label="")
        self.gpu_usage_label.set_halign(Gtk.Align.CENTER)
        self.gpu_usage_label.set_margin_start(10)
        self.gpu_usage_label.set_margin_end(10)
        self.gpu_usage_label.set_margin_top(5)
        self.gpu_usage_label.set_margin_bottom(5)
        self.gpu_usage_label.set_line_wrap(True)
        vbox.pack_start(self.gpu_usage_label, False, False, 0)

        # 分隔线
        separator3 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        vbox.pack_start(separator3, False, False, 10)

        # GPU 清理按钮区域
        cleanup_frame = Gtk.Frame(label="GPU 清理")
        cleanup_frame.get_style_context().add_class("cleanup-card")
        vbox.pack_start(cleanup_frame, False, False, 0)

        cleanup_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        cleanup_box.set_margin_top(10)
        cleanup_box.set_margin_bottom(10)
        cleanup_box.set_margin_start(20)
        cleanup_box.set_margin_end(20)
        cleanup_box.set_hexpand(True)
        cleanup_frame.add(cleanup_box)

        # 快速清理按钮
        quick_cleanup_btn = Gtk.Button.new_with_label("🧹 快速清理 GPU")
        quick_cleanup_btn.set_hexpand(True)
        quick_cleanup_btn.get_vexpand(False)
        quick_cleanup_btn.get_style_context().add_class("cleanup-button-quick")
        quick_cleanup_btn.connect("clicked", self.on_quick_cleanup)
        cleanup_box.pack_start(quick_cleanup_btn, True, True, 0)

        # 完整清理按钮
        full_cleanup_btn = Gtk.Button.new_with_label("⚡ 完整清理")
        full_cleanup_btn.set_hexpand(True)
        full_cleanup_btn.set_vexpand(False)
        full_cleanup_btn.get_style_context().add_class("cleanup-button-full")
        full_cleanup_btn.connect("clicked", self.on_full_cleanup)
        cleanup_box.pack_start(full_cleanup_btn, True, True, 0)

        # 分隔线
        separator4 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        vbox.pack_start(separator4, False, False, 10)

        # 操作按钮
        actions_frame = Gtk.Frame(label="切换模式")
        actions_frame.get_style_context().add_class("actions-card")
        vbox.pack_start(actions_frame, False, False, 0)

        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        actions_box.set_margin_top(15)
        actions_box.set_margin_bottom(15)
        actions_box.set_margin_start(20)
        actions_box.set_margin_end(20)
        actions_box.set_hexpand(True)
        actions_frame.add(actions_box)

        # 正常模式按钮
        self.normal_btn = Gtk.Button.new_with_label("🟢 正常模式\n(NVIDIA)")
        self.normal_btn.set_hexpand(True)
        self.normal_btn.set_vexpand(False)
        self.normal_btn.get_style_context().add_class("mode-button-normal")
        self.normal_btn.connect("clicked", self.on_switch_normal)
        actions_box.pack_start(self.normal_btn, True, True, 0)

        # 直通模式按钮
        self.pt_btn = Gtk.Button.new_with_label("🟠 直通模式\n(VFIO)")
        self.pt_btn.set_hexpand(True)
        self.pt_btn.set_vexpand(False)
        self.pt_btn.get_style_context().add_class("mode-button-passthrough")
        self.pt_btn.connect("clicked", self.on_switch_passthrough)
        actions_box.pack_start(self.pt_btn, True, True, 0)

        # 警告信息
        warning_frame = Gtk.Frame()
        warning_frame.get_style_context().add_class("warning-card")
        vbox.pack_start(warning_frame, False, False, 0)

        warning_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        warning_box.set_margin_top(10)
        warning_box.set_margin_bottom(10)
        warning_box.set_margin_start(15)
        warning_box.set_margin_end(15)
        warning_frame.add(warning_box)

        warning_label = Gtk.Label(label="")
        warning_label.set_markup("<span foreground='#FF6B35'>⚠️  注意事项</span>")
        warning_label.set_halign(Gtk.Align.START)
        warning_label.get_style_context().add_class("warning-title")
        warning_box.pack_start(warning_label, False, False, 0)

        self.warning_text = Gtk.Label(label="")
        self.warning_text.set_halign(Gtk.Align.START)
        self.warning_text.set_line_wrap(True)
        self.warning_text.set_margin_start(5)
        self.warning_text.get_style_context().add_class("warning-text")
        warning_box.pack_start(self.warning_text, False, False, 0)

        # 初始化警告文本
        self.update_warning_text()

        # 日志输出区域
        log_frame = Gtk.Frame(label="操作日志")
        log_frame.get_style_context().add_class("log-card")
        log_frame.set_vexpand(True)  # 允许垂直扩展
        vbox.pack_start(log_frame, True, True, 0)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_vexpand(True)  # 允许垂直扩展
        scrolled_window.set_hexpand(True)  # 允许水平扩展
        scrolled_window.set_min_content_height(150)
        scrolled_window.set_min_content_width(440)
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.get_style_context().add_class("log-scroll")

        self.log_buffer = Gtk.TextBuffer()
        log_view = Gtk.TextView(buffer=self.log_buffer, editable=False, wrap_mode=Gtk.WrapMode.WORD)
        log_view.set_margin_top(8)
        log_view.set_margin_bottom(8)
        log_view.set_margin_start(8)
        log_view.set_margin_end(8)
        log_view.set_vexpand(True)
        log_view.set_hexpand(True)
        log_view.get_style_context().add_class("log-view")

        scrolled_window.add(log_view)
        log_frame.add(scrolled_window)

        # 窗口显示后再添加日志，避免初始化错误
        GLib.idle_add(lambda: (self.log("🚀 GPU 直通控制面板已启动"), False))

    def auto_check_gpu_usage(self):
        """启动时自动检测 GPU 占用"""
        self.log("📊 自动检测 GPU 占用情况...")

        monitor_script = self.script_dir / "gpu-monitor.sh"
        if not monitor_script.exists():
            self.log("⚠️ GPU 监控脚本不存在，跳过检测")
            return False

        # 在后台线程中运行检测
        thread = threading.Thread(target=self._run_gpu_check_thread, args=(monitor_script,))
        thread.daemon = True
        thread.start()

        return False  # 只运行一次

    def _run_gpu_check_thread(self, script_path):
        """在后台线程中运行 GPU 检测"""
        try:
            success, output, error = self.run_command(str(script_path))
            GLib.idle_add(lambda: self._process_gpu_check_result(success, output, error))
        except Exception as e:
            GLib.idle_add(lambda: self.log(f"GPU 检测出错: {e}"))

    def on_quick_cleanup(self, button):
        """快速清理按钮 - 关闭计算进程和浏览器"""
        self.confirm_and_cleanup("quick")

    def on_full_cleanup(self, button):
        """完整清理按钮 - 关闭所有进程包括显示服务"""
        self.confirm_and_cleanup("full")

    def confirm_and_cleanup(self, cleanup_type):
        """确认并执行清理"""
        if cleanup_type == "quick":
            msg = "快速清理 GPU 占用\n\n这将:\n• 关闭计算/CUDA 进程\n• 关闭浏览器进程\n\n是否继续?"
        else:
            msg = "完整清理 GPU\n\n这将:\n• 关闭所有计算进程\n• 关闭浏览器进程\n• 停止显示服务\n⚠️ 警告: 停止显示服务会退出图形界面！\n\n是否继续?"

        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.WARNING if cleanup_type == "full" else Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="清理 GPU 占用"
        )
        dialog.format_secondary_text(msg)
        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.YES:
            self.run_cleanup(cleanup_type)

    def run_cleanup(self, cleanup_type):
        """执行清理操作"""
        cleanup_script = self.script_dir / "kill-gpu-processes.sh"

        if not cleanup_script.exists():
            self.log("✗ 清理脚本不存在")
            return

        if self.operation_in_progress:
            self.log("⚠️ 操作进行中，请稍候")
            return

        self.operation_in_progress = True

        if cleanup_type == "quick":
            self.log("🧹 开始快速清理...")
            # 直接调用清理命令
            cmd = f"pkexec {cleanup_script} cleanup-quick"
        else:
            self.log("⚡ 开始完整清理...")
            cmd = f"pkexec {cleanup_script} cleanup-full"

        # 在后台线程中运行清理
        thread = threading.Thread(target=self._run_cleanup_thread, args=(cmd,))
        thread.daemon = True
        thread.start()

    def _run_cleanup_thread(self, cmd):
        """在后台线程中运行清理"""
        try:
            success, output, error = self.run_command(cmd)

            if success:
                GLib.idle_add(lambda: self._process_cleanup_result(output))
            else:
                GLib.idle_add(lambda: self.log(f"✗ 清理失败: {error}"))

            GLib.idle_add(lambda: setattr(self, 'operation_in_progress', False))
        except Exception as e:
            GLib.idle_add(lambda: self.log(f"✗ 清理出错: {e}"))
            GLib.idle_add(lambda: setattr(self, 'operation_in_progress', False))

    def _process_cleanup_result(self, output):
        """处理清理结果"""
        self.log("=== 清理结果 ===")
        for line in output.split('\n'):
            if line.strip():
                self.log(line.strip())

        self.log("✓ 清理完成，请刷新状态")
        self.update_status()

    def _process_gpu_check_result(self, success, output, error):
        """处理 GPU 检测结果"""
        if not success:
            self.log("⚠️ GPU 监控不可用（nvidia-smi 可能未安装）")
            return

        # 解析输出，检测是否有进程占用
        has_compute = False
        has_gui = False
        has_browser = False
        has_game = False

        lines = output.split('\n')
        for line in lines:
            if 'CUDA' in line or '计算进程' in line:
                has_compute = True
            elif 'Xorg' in line or 'gnome-shell' in line or 'kwin' in line:
                has_gui = True
            elif 'chrome' in line.lower() or 'firefox' in line.lower():
                has_browser = True
            elif 'steam' in line.lower() or 'game' in line.lower():
                has_game = True

        # 更新状态
        self.gpu_usage_detected = has_compute or has_game

        # 更新提示标签
        if self.gpu_usage_detected:
            self.gpu_usage_label.set_markup(
                "<span foreground='#FF5722'>⚠️ 检测到 GPU 被占用！热切换前请关闭相关应用</span>"
            )
            self.log("⚠️ 检测到 GPU 占用")
        elif has_gui or has_browser:
            self.gpu_usage_label.set_markup(
                "<span foreground='#FF9800'>ℹ️ 检测到可能使用 GPU 的进程（显示服务/浏览器）</span>"
            )
            self.log("ℹ️ 检测到可能使用 GPU 的进程")
        else:
            self.gpu_usage_label.set_markup(
                "<span foreground='#4CAF50'>✓ GPU 空闲，可以安全切换</span>"
            )
            self.log("✓ GPU 空闲，可以安全切换")

        # 在日志中显示详细结果
        self.log("=== GPU 监控结果 ===")
        for line in lines[:30]:  # 只显示前 30 行
            if line.strip():
                self.log(line.strip())

    def apply_css(self):
        """应用自定义 CSS 样式"""
        css = """
        /* 主窗口样式 */
        window {
            background-color: @theme_bg_color;
        }

        /* 状态卡片 */
        .status-card {
            border-radius: 8px;
            border: 1px solid rgba(0,0,0,0.1);
        }

        .status-card label {
            font-size: 13px;
            padding: 4px 0;
        }

        /* 操作按钮卡片 */
        .actions-card {
            border-radius: 8px;
            border: 1px solid rgba(0,0,0,0.1);
        }

        /* 正常模式按钮 */
        .mode-button-normal {
            background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
            color: white;
            border-radius: 12px;
            padding: 12px 24px;
            font-weight: bold;
            font-size: 14px;
            text-shadow: 0 1px 2px rgba(0,0,0,0.2);
            box-shadow: 0 2px 4px rgba(76, 175, 80, 0.3);
        }

        .mode-button-normal:hover {
            background: linear-gradient(135deg, #5CBF60 0%, #55B059 100%);
            box-shadow: 0 4px 8px rgba(76, 175, 80, 0.4);
        }

        /* 直通模式按钮 */
        .mode-button-passthrough {
            background: linear-gradient(135deg, #FF9800 0%, #F57C00 100%);
            color: white;
            border-radius: 12px;
            padding: 12px 24px;
            font-weight: bold;
            font-size: 14px;
            text-shadow: 0 1px 2px rgba(0,0,0,0.2);
            box-shadow: 0 2px 4px rgba(255, 152, 0, 0.3);
        }

        .mode-button-passthrough:hover {
            background: linear-gradient(135deg, #FFA830 0%, #FF8C00 100%);
            box-shadow: 0 4px 8px rgba(255, 152, 0, 0.4);
        }

        /* 激活状态按钮 */
        .button-active {
            opacity: 1;
        }

        .button-active:disabled {
            opacity: 0.8;
        }

        /* 切换方式选择按钮 */
        .mode-card {
            border-radius: 8px;
            border: 1px solid rgba(0,0,0,0.1);
        }

        .toggle-button-reboot {
            border-radius: 6px;
            padding: 8px 16px;
            font-size: 12px;
            font-weight: bold;
            border: 2px solid #4CAF50;
        }

        .toggle-button-reboot:checked {
            background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
            color: white;
        }

        .toggle-button-hotplug {
            border-radius: 6px;
            padding: 8px 16px;
            font-size: 12px;
            font-weight: bold;
            border: 2px solid #FF9800;
        }

        .toggle-button-hotplug:checked {
            background: linear-gradient(135deg, #FF9800 0%, #F57C00 100%);
            color: white;
        }

        .toggle-button-reboot:not(:checked):hover,
        .toggle-button-hotplug:not(:checked):hover {
            background-color: rgba(0,0,0,0.05);
        }

        /* GPU 清理卡片 */
        .cleanup-card {
            border-radius: 8px;
            border: 1px solid rgba(0,0,0,0.1);
        }

        .cleanup-button-quick {
            border-radius: 6px;
            padding: 10px 20px;
            font-size: 13px;
            font-weight: bold;
            background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
            color: white;
            border: none;
        }

        .cleanup-button-quick:hover {
            background: linear-gradient(135deg, #66BB6A 0%, #43a047 100%);
            box-shadow: 0 2px 8px rgba(76, 175, 80, 0.4);
        }

        .cleanup-button-full {
            border-radius: 6px;
            padding: 10px 20px;
            font-size: 13px;
            font-weight: bold;
            background: linear-gradient(135deg, #FF5722 0%, #F4511E 100%);
            color: white;
            border: none;
        }

        .cleanup-button-full:hover {
            background: linear-gradient(135deg, #FF7043 0%, #E64A19 100%);
            box-shadow: 0 2px 8px rgba(255, 87, 34, 0.4);
        }

        /* 非激活状态按钮 */
        .button-inactive {
            opacity: 0.7;
        }

        .button-inactive:hover {
            opacity: 1;
        }

        /* 刷新按钮 */
        .refresh-button {
            border-radius: 6px;
            padding: 8px 16px;
            font-size: 12px;
        }

        /* 警告卡片 */
        .warning-card {
            border-radius: 8px;
            border: 1px solid rgba(255, 107, 53, 0.3);
            background-color: rgba(255, 107, 53, 0.05);
        }

        .warning-title {
            font-weight: bold;
            font-size: 14px;
        }

        .warning-text {
            font-size: 11px;
            color: rgba(0,0,0,0.7);
        }

        /* 日志卡片 */
        .log-card {
            border-radius: 8px;
            border: 1px solid rgba(0,0,0,0.1);
        }

        .log-scroll {
            border-radius: 6px;
        }

        .log-view {
            font-family: 'Monospace', monospace;
            font-size: 11px;
            color: rgba(0,0,0,0.8);
            background-color: rgba(0,0,0,0.02);
        }

        /* Frame 标签样式 */
        frame > label {
            font-weight: bold;
            font-size: 12px;
            color: rgba(0,0,0,0.6);
        }

        /* 分隔线 */
        separator {
            background-color: rgba(0,0,0,0.1);
        }
        """

        # 应用 CSS
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def log(self, message):
        """添加日志信息"""
        with self.log_lock:
            end_iter = self.log_buffer.get_end_iter()
            timestamp = GLib.DateTime.new_now_local().format("%H:%M:%S")
            self.log_buffer.insert(end_iter, f"[{timestamp}] {message}\n")
            # 自动滚动到底部
            self.log_buffer.place_cursor(end_iter)

    def run_command(self, cmd):
        """执行命令并返回输出"""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0, result.stdout, result.stderr
        except Exception as e:
            return False, "", str(e)

    def get_gpu_status(self):
        """获取GPU状态"""
        # 检查驱动
        _, driver_output, _ = self.run_command(f"lspci -nnk -d {self.nvidia_devices['vga']} | grep 'Kernel driver'")

        # 检查模块
        _, module_output, _ = self.run_command("lsmod | grep -E '^nvidia |^vfio'")

        # 检查IOMMU
        _, iommu_output, _ = self.run_command("test -d /sys/kernel/iommu_groups && echo 'enabled'")

        # 检查配置文件
        config_status = self.check_config_files()

        return driver_output, module_output, iommu_output, config_status

    def check_config_files(self):
        """检查配置文件状态"""
        status = []

        # 检查 VFIO 配置
        vfio_conf = "/etc/modprobe.d/vfio.conf"
        if os.path.exists(vfio_conf):
            success, content, _ = self.run_command(f"cat {vfio_conf}")
            if "##options" in content:
                status.append("VFIO:禁用")
            elif "options vfio-pci" in content:
                status.append("VFIO:启用")

        # 检查黑名单配置
        blacklist_conf = "/etc/modprobe.d/blacklist-nouveau.conf"
        if os.path.exists(blacklist_conf):
            success, content, _ = self.run_command(f"cat {blacklist_conf}")
            if "^blacklist nouveau" in content:
                status.append("黑名单:启用")
            else:
                status.append("黑名单:禁用")

        # 检查 GRUB IOMMU
        grub_conf = "/etc/default/grub"
        if os.path.exists(grub_conf):
            success, content, _ = self.run_command(f"cat {grub_conf}")
            if "intel_iommu=on" in content or "amd_iommu=on" in content:
                status.append("IOMMU:启用")
            else:
                status.append("IOMMU:禁用")

        return " | ".join(status) if status else "无配置"

    def parse_mode(self, driver_output, module_output):
        """解析当前模式"""
        # lspci -nnk 输出格式: Kernel driver in use: vfio-pci
        if "vfio-pci" in driver_output:
            return "直通模式", "passthrough"
        elif "nvidia" in driver_output:
            return "正常模式", "normal"
        # 如果VGA驱动不是nvidia也不是vfio，检查内核模块
        elif "nvidia" in module_output:
            return "正常模式", "normal"
        elif "vfio" in module_output:
            return "直通模式", "passthrough"
        else:
            return "未知", "unknown"

    def update_status(self):
        """更新状态显示"""
        try:
            driver_output, module_output, iommu_output, config_status = self.get_gpu_status()
            mode, mode_type = self.parse_mode(driver_output, module_output)

            # 颜色定义
            colors = {
                'normal': '#4CAF50',      # 绿色
                'passthrough': '#FF9800', # 橙色
                'unknown': '#757575'      # 灰色
            }
            color = colors.get(mode_type, colors['unknown'])

            # 更新模式标签
            self.mode_label.set_markup(f"模式: <span foreground='{color}'><b>{mode}</b></span>")

            # 更新驱动标签
            if driver_output.strip():
                self.driver_label.set_text(f"驱动: {driver_output.strip()}")
            else:
                self.driver_label.set_text("驱动: 无")

            # 更新IOMMU标签
            if iommu_output.strip() == 'enabled':
                self.iommu_label.set_markup("IOMMU: <span foreground='green'>已启用</span>")
            else:
                self.iommu_label.set_markup("IOMMU: <span foreground='red'>未启用</span>")

            # 更新配置标签
            self.config_label.set_text(f"配置: {config_status}")

            # 更新按钮状态
            self.update_buttons(mode_type)

        except Exception as e:
            self.log(f"更新状态失败: {e}")

    def update_buttons(self, current_mode):
        """更新按钮状态"""
        # 清除之前的样式
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
            self.normal_btn.get_style_context().add_class("button-inactive")
            self.pt_btn.set_sensitive(True)
            self.pt_btn.set_label("🟠 直通模式\n(VFIO)")
            self.pt_btn.get_style_context().add_class("button-inactive")

    def on_refresh(self, button):
        """刷新按钮点击事件"""
        self.log("正在刷新状态...")
        self.update_status()
        self.log("状态已刷新")

    def on_toggle_switch_mode(self, button):
        """切换热切换/重启切换模式"""
        if button == self.reboot_toggle and button.get_active():
            self.hotplug_toggle.set_active(False)
            self.switch_mode = 'reboot'
            self.log("🔄 已切换到重启切换模式 (安全)")
            self.update_warning_text()
        elif button == self.hotplug_toggle and button.get_active():
            self.reboot_toggle.set_active(False)
            self.switch_mode = 'hotplug'
            self.log("⚡ 已切换到热切换模式 (快速)")
            self.update_warning_text()
        else:
            # 防止两个都不选中
            if self.switch_mode == 'reboot':
                self.reboot_toggle.set_active(True)
            else:
                self.hotplug_toggle.set_active(True)

    def update_warning_text(self):
        """根据切换模式更新警告文本"""
        if self.switch_mode == 'reboot':
            self.warning_text.set_markup(
                "• <b>重启切换: 切换后系统将自动重启</b>\n"
                "• 切换前请保存所有工作\n"
                "• 更安全，但需要重启时间"
            )
        else:
            self.warning_text.set_markup(
                "• <b>热切换: 无需重启，快速切换</b>\n"
                "• 需要预先启用 IOMMU\n"
                "• 可能需要关闭显示服务和应用程序"
            )

    def execute_switch(self, mode):
        """执行切换操作"""
        if self.switch_mode == 'reboot':
            self.execute_reboot_switch(mode)
        else:
            self.execute_hotplug_switch(mode)

    def execute_reboot_switch(self, mode):
        """执行重启切换操作"""
        self.log(f"🔄 开始切换到{mode}模式 (重启方式)...")

        try:
            script_path = str(self.switch_script)

            if not os.path.exists(script_path):
                self.log(f"✗ 脚本不存在: {script_path}")
                GLib.idle_add(lambda: (self.restore_buttons(), False))
                return

            if mode == "normal":
                cmd = f"pkexec {script_path} normal --no-confirm"
            else:
                cmd = f"pkexec {script_path} passthrough --no-confirm"

            self.log(f"执行命令: {script_path} {mode} --no-confirm")

            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # 实时输出日志
            for line in process.stdout:
                if line.strip():
                    self.log(line.strip())

            stdout, stderr = process.communicate(timeout=300)

            if process.returncode == 0:
                self.log("✓ 切换成功，系统将自动重启")
                if stdout:
                    for line in stdout.split('\n'):
                        if line.strip():
                            self.log(line)
            else:
                self.log("✗ 切换失败")
                if stderr:
                    for line in stderr.split('\n'):
                        if line.strip():
                            self.log(line)
                GLib.idle_add(lambda: (self.restore_buttons(), False))

            # 系统即将重启，不更新状态
            self.log("⚠️ 系统即将重启，请保存工作")

        except subprocess.TimeoutExpired:
            self.log("✗ 操作超时")
            GLib.idle_add(lambda: (self.restore_buttons(), False))
        except Exception as e:
            self.log(f"✗ 执行错误: {e}")
            GLib.idle_add(lambda: (self.restore_buttons(), False))
        finally:
            self.operation_in_progress = False

    def execute_hotplug_switch(self, mode):
        """执行热切换操作"""
        self.log(f"⚡ 开始切换到{mode}模式 (热切换方式)...")

        # 首先运行 GPU 监控
        self.run_gpu_monitor()

        # 检查热切换脚本是否存在
        hotplug_script = self.script_dir / "gpu-hotplug-safe.sh"
        fallback_script = self.script_dir / "gpu-switch-hotplug"

        if hotplug_script.exists():
            script_path = str(hotplug_script)
            self.log(f"使用安全热切换脚本 (自动模式)")
        elif fallback_script.exists():
            script_path = str(fallback_script)
            self.log(f"使用标准热切换脚本")
        else:
            self.log(f"✗ 未找到热切换脚本")
            self.log(f"  请确保以下文件存在:")
            self.log(f"  - gpu-hotplug-safe.sh")
            self.log(f"  - 或 gpu-switch-hotplug")
            GLib.idle_add(lambda: (self.restore_buttons(), False))
            return

        try:
            if mode == "normal":
                cmd = f"pkexec {script_path} normal --auto"
            else:
                cmd = f"pkexec {script_path} passthrough --auto"

            self.log(f"执行命令: {script_path} {mode} --auto")

            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # 实时输出日志
            for line in process.stdout:
                if line.strip():
                    self.log(line.strip())

            stdout, stderr = process.communicate(timeout=120)

            if process.returncode == 0:
                self.log("✓ 热切换成功")
                if stdout:
                    for line in stdout.split('\n'):
                        if line.strip():
                            self.log(line)
                # 更新状态
                GLib.timeout_add(1000, self.update_status)
            else:
                self.log("✗ 热切换失败")
                if stderr:
                    for line in stderr.split('\n'):
                        if line.strip():
                            self.log(line)
                GLib.idle_add(lambda: (self.restore_buttons(), False))

            if mode == "normal":
                self.log("💡 如需启动显示服务，运行: sudo systemctl start display-manager")

        except subprocess.TimeoutExpired:
            self.log("✗ 操作超时")
            GLib.idle_add(lambda: (self.restore_buttons(), False))
        except Exception as e:
            self.log(f"✗ 执行错误: {e}")
            GLib.idle_add(lambda: (self.restore_buttons(), False))
        finally:
            self.operation_in_progress = False

    def restore_buttons(self):
        """恢复按钮状态"""
        self.normal_btn.set_sensitive(True)
        self.pt_btn.set_sensitive(True)

    def confirm_switch(self, mode):
        """显示切换确认对话框"""
        mode_name = "正常模式 (NVIDIA)" if mode == "normal" else "直通模式 (VFIO)"
        msg_type = Gtk.MessageType.QUESTION if mode == "normal" else Gtk.MessageType.WARNING

        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=msg_type,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=f"切换到{mode_name}"
        )

        if self.switch_mode == 'reboot':
            dialog.format_secondary_text(
                f"这将从{'直通' if mode == 'normal' else '正常'}模式切换到{mode_name}。\n\n"
                "⚠️ <b>系统将自动重启！</b>\n"
                "请保存所有未保存的工作。\n\n"
                "继续?"
            )
        else:
            dialog.format_secondary_text(
                f"这将从{'直通' if mode == 'normal' else '正常'}模式切换到{mode_name}。\n\n"
                "⚡ <b>热切换模式 - 无需重启</b>\n"
                "• 确保没有应用程序正在使用 GPU\n"
                "• 可能需要停止显示服务\n\n"
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
        """窗口关闭事件"""
        Gtk.main_quit()

def main():
    win = GPUSwitcher()
    win.connect("destroy", win.on_destroy)
    win.show_all()
    Gtk.main()

if __name__ == "__main__":
    main()
