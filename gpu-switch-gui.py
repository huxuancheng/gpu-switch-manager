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
        self.set_default_size(480, 580)
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

        self.setup_ui()
        self.update_status()

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

        # 操作按钮
        actions_frame = Gtk.Frame(label="切换模式")
        actions_frame.get_style_context().add_class("actions-card")
        vbox.pack_start(actions_frame, False, False, 0)

        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        actions_box.set_margin_top(15)
        actions_box.set_margin_bottom(15)
        actions_box.set_margin_start(20)
        actions_box.set_margin_end(20)
        actions_frame.add(actions_box)

        # 正常模式按钮
        self.normal_btn = Gtk.Button.new_with_label("🟢 正常模式\n(NVIDIA)")
        self.normal_btn.set_size_request(160, 75)
        self.normal_btn.get_style_context().add_class("mode-button-normal")
        self.normal_btn.connect("clicked", self.on_switch_normal)
        actions_box.pack_start(self.normal_btn, True, True, 0)

        # 直通模式按钮
        self.pt_btn = Gtk.Button.new_with_label("🟠 直通模式\n(VFIO)")
        self.pt_btn.set_size_request(160, 75)
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

        warning_text = Gtk.Label(label="")
        warning_text.set_markup(
            "• <b>切换模式后系统将自动重启</b>\n"
            "• 切换前请保存所有工作\n"
            "• 切换需要管理员权限"
        )
        warning_text.set_halign(Gtk.Align.START)
        warning_text.set_line_wrap(True)
        warning_text.set_margin_start(5)
        warning_text.get_style_context().add_class("warning-text")
        warning_box.pack_start(warning_text, False, False, 0)

        # 日志输出区域
        log_frame = Gtk.Frame(label="操作日志")
        log_frame.get_style_context().add_class("log-card")
        vbox.pack_start(log_frame, True, True, 0)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_min_content_height(150)
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.get_style_context().add_class("log-scroll")

        self.log_buffer = Gtk.TextBuffer()
        log_view = Gtk.TextView(buffer=self.log_buffer, editable=False, wrap_mode=Gtk.WrapMode.WORD)
        log_view.set_margin_top(8)
        log_view.set_margin_bottom(8)
        log_view.set_margin_start(8)
        log_view.set_margin_end(8)
        log_view.get_style_context().add_class("log-view")

        scrolled_window.add(log_view)
        log_frame.add(scrolled_window)

        # 窗口显示后再添加日志，避免初始化错误
        GLib.idle_add(lambda: (self.log("🚀 GPU 直通控制面板已启动"), False))

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

    def execute_switch(self, mode):
        """执行切换操作"""
        self.log(f"开始切换到{mode}模式...")

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
        """窗口关闭事件"""
        Gtk.main_quit()

def main():
    win = GPUSwitcher()
    win.connect("destroy", win.on_destroy)
    win.show_all()
    Gtk.main()

if __name__ == "__main__":
    main()
