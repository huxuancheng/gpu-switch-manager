# GPU 直通管理器 (GPU Switch Manager)

一个简洁高效的 GPU 直通模式切换工具,支持在正常模式和 VFIO 直通模式之间切换,专为 NVIDIA GPU 设计。

![GPU Switch Manager](https://img.shields.io/badge/Python-3-blue.svg)
![GTK](https://img.shields.io/badge/GTK-3.0-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## ✨ 功能特性

### 🎨 简洁界面
- 基于 GTK3 的清爽界面
- 渐变色按钮和现代化设计
- 响应式布局,自动适配系统 DPI
- 支持系统托盘最小化

### 🔧 核心功能
- **模式切换**: 一键切换正常模式和直通模式
- **状态监控**: 实时显示 GPU 驱动、IOMMU 状态
- **日志记录**: 详细的操作日志,便于问题排查
- **日志导出**: 支持导出日志文件
- **系统托盘**: 可最小化到托盘,方便后台运行

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
sudo pacman -S python-gobject polkit python-appindicator
```

### Ubuntu/Debian
```bash
sudo apt-get install python3-gi policykit-1 gir1.2-appindicator3-0.1
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

## 📊 兼容性

### ✅ 完全支持

| 类别 | 支持项 |
|------|--------|
| **操作系统** | Arch Linux, Manjaro, EndeavourOS 等 Arch 系发行版 |
| **CPU 架构** | AMD64 (x86_64) |
| **GPU 品牌** | NVIDIA (主要支持) |
| **桌面环境** | GNOME, KDE Plasma, XFCE, MATE, LXQt 及其他 GTK3 环境 |
| **CPU 类型** | Intel (支持 Intel IOMMU), AMD (支持 AMD IOMMU) |

### ⚠️ 部分支持

| 发行版 | initramfs 工具 | 适配需求 |
|--------|---------------|----------|
| Ubuntu/Debian | `update-initramfs` | 需修改脚本第 213、285 行 |
| Fedora/RHEL | `dracut` | 需修改脚本第 213、285 行 |
| openSUSE | `dracut` | 需修改脚本第 213、285 行 |

### ❌ 不支持

- Windows / macOS
- 无 systemd 的发行版
- 非虚拟化支持的环境

### 🔧 其他发行版适配

如果需要在 Ubuntu/Debian 使用，将 `gpu-switch-v3` 中的命令修改为：

```bash
# 第 213 行和第 285 行
# 将:
mkinitcpio -P

# 改为:
update-initramfs -u -k all
```

如果需要在 Fedora/RHEL 使用，改为：

```bash
dracut -f
```

### ⚠️ 注意事项

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
