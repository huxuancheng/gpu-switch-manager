#!/usr/bin/env python3
# GPU 直通控制面板 - 简化版

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
import json
from pathlib import Path
from datetime import datetime

# 配置文件路径
CONFIG_FILE = Path.home() / ".gpu-switcher" / "config.json"

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

class GPUSwitcher(Gtk.Window):
    def __init__(self):
        super().__init__(title="GPU 直通控制面板")
        self.set_icon_name("video-display")
        
        # 加载配置
        self.load_config()
        
        # 窗口大小
        min_width = int(800 * SCALE_FACTOR)
        min_height = int(500 * SCALE_FACTOR)
        default_width = int(900 * SCALE_FACTOR)
        default_height = int(650 * SCALE_FACTOR)
        
        self.set_size_request(min_width, min_height)
        self.set_default_size(default_width, default_height)
        self.set_border_width(int(10 * SCALE_FACTOR))
        self.set_resizable(True)
        self.set_position(Gtk.WindowPosition.CENTER)

        # 配置路径
        self.script_dir = Path(__file__).parent
        self.switch_script = self.script_dir / "gpu-switch-v3"
        for script_name in ["gpu-switch-v3", "gpu-switch", "gpu-switch-v2"]:
            if self.switch_script.exists():
                break
            self.switch_script = self.script_dir / script_name

        # 状态
        self.operation_in_progress = False
        self.current_mode = "unknown"

        # NVIDIA 设备 ID
        self.nvidia_devices = {'vga': '10de:2206', 'audio': '10de:1aef'}

        # 创建系统托盘
        self.indicator = None
        if HAS_INDICATOR:
            self.create_indicator()

        # 初始化UI
        self.setup_ui()
        self.update_status()
        GLib.timeout_add(30000, self.auto_refresh_status)

    def load_config(self):
        """加载配置"""
        self.config = {'minimize_to_tray': False}
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
            pass

    def create_indicator(self):
        """创建系统托盘图标"""
        try:
            self.indicator = AppIndicator3.Indicator.new(
                "gpu-switcher",
                "video-display",
                AppIndicator3.IndicatorCategory.APPLICATION_STATUS
            )
            self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            
            # 创建菜单
            menu = Gtk.Menu()
            
            # 状态项
            self.indicator_status = Gtk.MenuItem("状态: 检测中...")
            self.indicator_status.set_sensitive(False)
            menu.append(self.indicator_status)
            
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
            pass

    def on_show_window(self, item):
        """显示主窗口"""
        self.show_all()
        self.present()

    def on_quit(self, item):
        """退出程序"""
        Gtk.main_quit()

    def setup_ui(self):
        """设置UI"""
        self.apply_css()
        
        # 主布局
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=int(10 * SCALE_FACTOR))
        main_box.set_margin_start(int(10 * SCALE_FACTOR))
        main_box.set_margin_end(int(10 * SCALE_FACTOR))
        main_box.set_margin_top(int(10 * SCALE_FACTOR))
        main_box.set_margin_bottom(int(10 * SCALE_FACTOR))
        self.add(main_box)
        
        # 标题
        title = Gtk.Label(label="")
        title.set_markup("<big><b>🖥️ GPU 直通控制面板</b></big>")
        main_box.pack_start(title, False, False, 0)
        
        # 状态区域
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=int(10 * SCALE_FACTOR))
        main_box.pack_start(status_box, False, False, 0)
        
        self.mode_label = Gtk.Label(label="模式: 检测中...")
        self.mode_label.get_style_context().add_class("status-label")
        status_box.pack_start(self.mode_label, True, True, 0)
        
        self.driver_label = Gtk.Label(label="驱动: 检测中...")
        self.driver_label.get_style_context().add_class("status-label")
        status_box.pack_start(self.driver_label, True, True, 0)
        
        self.iommu_label = Gtk.Label(label="IOMMU: 检测中...")
        self.iommu_label.get_style_context().add_class("status-label")
        status_box.pack_start(self.iommu_label, True, True, 0)
        
        # 按钮区域
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=int(20 * SCALE_FACTOR))
        main_box.pack_start(btn_box, False, False, int(10 * SCALE_FACTOR))
        
        self.normal_btn = Gtk.Button.new_with_label("🟢 正常模式")
        self.normal_btn.get_style_context().add_class("mode-button-normal")
        self.normal_btn.connect("clicked", self.on_switch_normal)
        btn_box.pack_start(self.normal_btn, True, True, 0)
        
        self.pt_btn = Gtk.Button.new_with_label("🟠 直通模式")
        self.pt_btn.get_style_context().add_class("mode-button-passthrough")
        self.pt_btn.connect("clicked", self.on_switch_passthrough)
        btn_box.pack_start(self.pt_btn, True, True, 0)
        
        # 日志区域
        log_frame = Gtk.Frame(label="操作日志")
        log_frame.set_vexpand(True)
        main_box.pack_start(log_frame, True, True, 0)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(int(200 * SCALE_FACTOR))
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        log_frame.add(scrolled)
        
        self.log_buffer = Gtk.TextBuffer()
        log_view = Gtk.TextView(buffer=self.log_buffer, editable=False, wrap_mode=Gtk.WrapMode.WORD)
        scrolled.add(log_view)
        
        # 日志按钮
        log_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=int(5 * SCALE_FACTOR))
        main_box.pack_start(log_btn_box, False, False, 0)
        
        refresh_btn = Gtk.Button.new_with_label("🔄 刷新")
        refresh_btn.connect("clicked", self.on_refresh)
        log_btn_box.pack_start(refresh_btn, True, True, 0)
        
        export_btn = Gtk.Button.new_with_label("📥 导出")
        export_btn.connect("clicked", self.on_export_log)
        log_btn_box.pack_start(export_btn, True, True, 0)
        
        clear_btn = Gtk.Button.new_with_label("🗑️ 清空")
        clear_btn.connect("clicked", self.on_clear_log)
        log_btn_box.pack_start(clear_btn, True, True, 0)
        
        # 设置选项
        setting_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=int(10 * SCALE_FACTOR))
        main_box.pack_start(setting_box, False, False, int(5 * SCALE_FACTOR))
        
        self.minimize_tray_check = Gtk.CheckButton(label="关闭时最小化到托盘")
        self.minimize_tray_check.set_active(self.config.get('minimize_to_tray', False))
        setting_box.pack_start(self.minimize_tray_check, True, True, 0)
        
        save_btn = Gtk.Button.new_with_label("💾 保存")
        save_btn.connect("clicked", self.on_save_settings)
        setting_box.pack_start(save_btn, False, False, 0)
        
        GLib.idle_add(lambda: (self.log("🚀 GPU 直通控制面板已启动"), False))

    def apply_css(self):
        """应用CSS样式"""
        css = f"""
        .mode-button-normal {{
            background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
            color: white;
            border-radius: {int(8 * SCALE_FACTOR)}px;
            padding: {int(12 * SCALE_FACTOR)}px {int(24 * SCALE_FACTOR)}px;
            font-weight: bold;
            font-size: {int(14 * SCALE_FACTOR)}px;
        }}
        .mode-button-normal:hover {{
            background: linear-gradient(135deg, #5CBF60 0%, #55B059 100%);
        }}
        .mode-button-passthrough {{
            background: linear-gradient(135deg, #FF9800 0%, #F57C00 100%);
            color: white;
            border-radius: {int(8 * SCALE_FACTOR)}px;
            padding: {int(12 * SCALE_FACTOR)}px {int(24 * SCALE_FACTOR)}px;
            font-weight: bold;
            font-size: {int(14 * SCALE_FACTOR)}px;
        }}
        .mode-button-passthrough:hover {{
            background: linear-gradient(135deg, #FFA830 0%, #FF8C00 100%);
        }}
        .status-label {{
            font-weight: bold;
            font-size: {int(13 * SCALE_FACTOR)}px;
            padding: {int(8 * SCALE_FACTOR)}px;
            background-color: rgba(0,0,0,0.05);
            border-radius: {int(6 * SCALE_FACTOR)}px;
        }}
        frame > label {{
            font-weight: bold;
            font-size: {int(12 * SCALE_FACTOR)}px;
        }}
        * {{
            font-size: {int(12 * SCALE_FACTOR)}px;
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
        end_iter = self.log_buffer.get_end_iter()
        timestamp = GLib.DateTime.new_now_local().format("%H:%M:%S")
        self.log_buffer.insert(end_iter, f"[{timestamp}] {message}\n")
        self.log_buffer.place_cursor(end_iter)

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
        return driver_output, module_output, iommu_output

    def parse_mode(self, driver_output, module_output):
        """解析当前模式"""
        if "vfio-pci" in driver_output:
            return "直通模式", "passthrough"
        elif "nvidia" in driver_output or "nvidia" in module_output:
            return "正常模式", "normal"
        elif "vfio" in module_output:
            return "直通模式", "passthrough"
        return "未知", "unknown"

    def update_status(self):
        """更新状态"""
        try:
            driver_output, module_output, iommu_output = self.get_gpu_status()
            mode, mode_type = self.parse_mode(driver_output, module_output)
            self.current_mode = mode_type
            
            colors = {'normal': '#4CAF50', 'passthrough': '#FF9800', 'unknown': '#757575'}
            color = colors.get(mode_type, colors['unknown'])
            
            self.mode_label.set_markup(f"<span foreground='{color}'><b>{mode}</b></span>")
            self.driver_label.set_text(f"驱动: {driver_output.strip() if driver_output.strip() else '无'}")
            self.iommu_label.set_markup(f"<span foreground='green'>已启用</span>" if iommu_output.strip() == 'enabled' else "<span foreground='red'>未启用</span>")
            
            self.update_buttons(mode_type)
            
            # 更新托盘状态
            if self.indicator:
                mode_name = "正常模式" if self.current_mode == "normal" else "直通模式" if self.current_mode == "passthrough" else "未知"
                self.indicator_status.set_label(f"状态: {mode_name}")
        except Exception as e:
            self.log(f"更新状态失败: {e}")

    def update_buttons(self, current_mode):
        """更新按钮状态"""
        if current_mode == "normal":
            self.normal_btn.set_sensitive(False)
            self.normal_btn.set_label("✅ 正常模式")
            self.pt_btn.set_sensitive(True)
            self.pt_btn.set_label("🟠 直通模式")
        elif current_mode == "passthrough":
            self.normal_btn.set_sensitive(True)
            self.normal_btn.set_label("🟢 正常模式")
            self.pt_btn.set_sensitive(False)
            self.pt_btn.set_label("✅ 直通模式")
        else:
            self.normal_btn.set_sensitive(True)
            self.normal_btn.set_label("🟢 正常模式")
            self.pt_btn.set_sensitive(True)
            self.pt_btn.set_label("🟠 直通模式")

    def auto_refresh_status(self):
        """自动刷新状态"""
        self.update_status()
        return True

    def on_refresh(self, button):
        """刷新状态"""
        self.log("正在刷新状态...")
        self.update_status()
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

    def on_save_settings(self, button):
        """保存设置"""
        self.config['minimize_to_tray'] = self.minimize_tray_check.get_active()
        self.save_config()
        self.log("✓ 设置已保存")

    def confirm_switch(self, mode):
        """确认切换"""
        mode_name = "正常模式" if mode == "normal" else "直通模式"
        dialog = Gtk.MessageDialog(
            self, 0, Gtk.MessageType.WARNING,
            Gtk.ButtonsType.OK_CANCEL, f"切换到{mode_name}"
        )
        dialog.format_secondary_text("⚠️ <b>系统将自动重启！</b>\n请保存所有未保存的工作。")
        response = dialog.run()
        dialog.destroy()
        return response == Gtk.ResponseType.OK

    def execute_switch(self, mode):
        """执行切换"""
        self.log(f"🔄 开始切换到{mode}模式...")
        
        try:
            script_path = str(self.switch_script)
            if not os.path.exists(script_path):
                self.log(f"✗ 脚本不存在: {script_path}")
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
                self.restore_buttons()
            
            self.log("⚠️ 系统即将重启，请保存工作")
            
        except subprocess.TimeoutExpired:
            self.log("✗ 操作超时")
            self.restore_buttons()
        except Exception as e:
            self.log(f"✗ 执行错误: {e}")
            self.restore_buttons()
        finally:
            self.operation_in_progress = False

    def restore_buttons(self):
        """恢复按钮"""
        self.normal_btn.set_sensitive(True)
        self.pt_btn.set_sensitive(True)

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

    def on_destroy(self, widget, event):
        """窗口关闭"""
        if self.config.get('minimize_to_tray', False) and HAS_INDICATOR:
            self.hide()
            return True
        else:
            Gtk.main_quit()
            return False

def main():
    win = GPUSwitcher()
    win.connect("delete-event", win.on_destroy)
    win.show_all()
    Gtk.main()

if __name__ == "__main__":
    main()
