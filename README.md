# GPU 直通管理器 (GPU Switch Manager)

一个基于 GTK3 的 GPU 直通模式切换工具,支持在正常模式和 VFIO 直通模式之间切换,专为 NVIDIA GPU 设计。

![GPU Switch Manager](https://img.shields.io/badge/Python-3-blue.svg)
![GTK](https://img.shields.io/badge/GTK-3.0-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## ✨ 功能特性

### 🎨 现代化界面
- 基于 Adwaita 主题的美观界面
- 渐变色按钮和平滑的动画效果
- 圆角卡片设计和阴影效果
- 响应式布局,支持窗口缩放

### 🔧 核心功能
- **模式切换**: 一键切换正常模式和直通模式
- **状态监控**: 实时显示 GPU 驱动、IOMMU、配置文件状态
- **自动备份**: 配置文件自动备份到 `/etc/gpu-switch-backup/`
- **日志记录**: 详细的操作日志,便于问题排查
- **权限管理**: 使用 pkexec 安全执行需要 root 权限的操作

### 🛡️ 安全性
- 操作前确认对话框,防止误操作
- 线程安全的日志记录
- 配置文件自动备份机制
- 完善的错误处理

## 📦 安装

### 依赖项
- Python 3.x
- GTK3 (`python-gobject`)
- Polkit (`policykit-1`)
- pkexec
- grub-mkconfig
- mkinitcpio (Arch Linux)

### Arch Linux
```bash
sudo pacman -S python-gobject polkit
```

### Ubuntu/Debian
```bash
sudo apt-get install python3-gi policykit-1
```

## 🚀 使用方法

### GUI 启动
```bash
./gpu-switch-gui.py
```

### 命令行启动
```bash
sudo ./gpu-switch-v3 status        # 查看当前状态
sudo ./gpu-switch-v3 normal        # 切换到正常模式
sudo ./gpu-switch-v3 passthrough   # 切换到直通模式
```

## 📋 项目结构

```
.
├── gpu-switch-gui.py          # GUI 主程序 (PyGTK3)
├── gpu-switch-v3              # Shell 脚本 (核心切换逻辑)
├── gpu-switch                 # 旧版脚本 (兼容性保留)
├── gpu-switch-hotplug         # 热插拔脚本
├── gpu-switch-gui.desktop     # 桌面快捷方式
└── README.md                  # 项目文档
```

## ⚙️ 配置

### NVIDIA 设备 ID
编辑 `gpu-switch-v3` 中的设备 ID:
```bash
NVIDIA_VGA="10de:2206"      # 显卡设备 ID
NVIDIA_AUDIO="10de:1aef"    # 音频设备 ID
```

### 查找设备 ID
```bash
lspci -nn | grep -i nvidia
```

## 🎯 工作原理

### 正常模式
- 加载 NVIDIA 专有驱动
- 禁用 VFIO 绑定
- 移除 IOMMU 内核参数
- 启用正常图形功能

### 直通模式
- 禁用 NVIDIA 驱动
- 绑定设备到 VFIO 驱动
- 启用 IOMMU 支持
- 配置 PCIe ASPM 和电源管理
- 添加驱动黑名单

## 🔒 权限说明

脚本需要 root 权限来修改以下配置:
- `/etc/modprobe.d/vfio.conf`
- `/etc/modprobe.d/blacklist-nouveau.conf`
- `/etc/modprobe.d/vfio-pci-options.conf`
- `/etc/default/grub`
- `/boot/grub/grub.cfg`
- initramfs 镜像

## ⚠️ 注意事项

1. **重启要求**: 模式切换后必须重启系统才能生效
2. **备份重要**: 所有配置修改前会自动备份
3. **权限要求**: 需要管理员权限才能执行切换操作
4. **兼容性**: 主要为 Arch Linux 设计,其他发行版可能需要调整
5. **设备 ID**: 确保脚本中的设备 ID 与你的硬件匹配

## 🤝 贡献

欢迎提交 Issue 和 Pull Request!

## 📄 许可证

MIT License

## 🙏 致谢

- GTK3 开发团队
- Arch Linux 社区
- VFIO 项目

## 📮 联系方式

如有问题或建议,请提交 Issue。

---

**注意**: 本工具仅供学习和技术研究使用,使用本工具造成的任何损失概不负责。
