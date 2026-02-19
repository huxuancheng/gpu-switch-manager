#!/bin/bash
# GPU 直通配置自动修复脚本

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log "=== GPU 直通配置自动修复工具 ==="

# 1. 检查 IOMMU
log "[1/6] 检查 IOMMU 配置..."
if [ -d /sys/kernel/iommu_groups ]; then
    log_success "IOMMU 已启用"
else
    log_warning "IOMMU 未启用"
    
    # 检测 CPU 类型
    if grep -q "Intel" /proc/cpuinfo; then
        IOMMU_PARAM="intel_iommu=on"
    elif grep -q "AMD" /proc/cpuinfo; then
        IOMMU_PARAM="amd_iommu=on"
    else
        log_error "无法检测 CPU 类型"
        exit 1
    fi
    
    log "检测到 ${IOMMU_PARAM%=*} CPU"
    
    # 检查 GRUB 配置
    GRUB_FILE="/etc/default/grub"
    if [ -f "$GRUB_FILE" ]; then
        if ! grep -q "$IOMMU_PARAM" "$GRUB_FILE"; then
            log "添加 $IOMMU_PARAM 到 GRUB..."
            sed -i "s/^GRUB_CMDLINE_LINUX_DEFAULT=\"\(.*\)\"/GRUB_CMDLINE_LINUX_DEFAULT=\"\1 $IOMMU_PARAM\"/" "$GRUB_FILE"
            log_success "已添加 $IOMMU_PARAM 到 GRUB"
            
            log "更新 GRUB..."
            update-grub
            log_success "GRUB 已更新"
            log_warning "需要重启系统使 IOMMU 生效"
        else
            log_success "$IOMMU_PARAM 已在 GRUB 配置中"
        fi
    else
        log_error "GRUB 配置文件不存在"
    fi
fi

# 2. 创建 VFIO 配置
log ""
log "[2/6] 配置 VFIO..."
VFIO_CONF="/etc/modprobe.d/vfio.conf"
if [ ! -f "$VFIO_CONF" ]; then
    log "创建 VFIO 配置文件..."
    cat > "$VFIO_CONF" << 'EOF'
# VFIO PCI 设备直通配置
# 取消注释以启用直通模式
#options vfio-pci ids=10de:2206,10de:1aef
#options vfio-pci disable_vga=1
EOF
    log_success "VFIO 配置文件已创建: $VFIO_CONF"
else
    log_success "VFIO 配置文件已存在"
fi

# 3. 创建 NVIDIA 黑名单
log ""
log "[3/6] 配置 NVIDIA 驱动黑名单..."
BLACKLIST_CONF="/etc/modprobe.d/blacklist-nouveau.conf"
if [ ! -f "$BLACKLIST_CONF" ]; then
    log "创建 NVIDIA 黑名单..."
    cat > "$BLACKLIST_CONF" << 'EOF'
blacklist nouveau
blacklist lbm-nouveau
options nouveau modeset=0
alias nouveau off
alias lbm-nouveau off
EOF
    log_success "NVIDIA 黑名单已创建: $BLACKLIST_CONF"
else
    log_success "NVIDIA 黑名单已存在"
fi

# 4. 配置 initramfs
log ""
log "[4/6] 配置 initramfs..."
INITRAMFS_CONF="/etc/initramfs-tools/modules"
if [ ! -f "$INITRAMFS_CONF" ]; then
    log "创建 initramfs 配置..."
    cat > "$INITRAMFS_CONF" << 'EOF'
# VFIO 模块
vfio
vfio_pci
vfio_iommu_type1
EOF
    log_success "initramfs 配置已创建: $INITRAMFS_CONF"
else
    # 检查模块是否存在
    if ! grep -q "vfio_pci" "$INITRAMFS_CONF"; then
        log "添加 VFIO 模块到 initramfs..."
        echo -e "\n# VFIO 模块\nvfio\nvfio_pci\nvfio_iommu_type1" >> "$INITRAMFS_CONF"
        log_success "VFIO 模块已添加"
    else
        log_success "VFIO 模块已配置"
    fi
fi

# 5. 创建 QEMU 用户组
log ""
log "[5/6] 配置 QEMU/KVM..."
if ! grep -q "^kvm:" /etc/group; then
    log "创建 kvm 用户组..."
    groupadd kvm 2>/dev/null
    usermod -aG kvm "$SUDO_USER" 2>/dev/null
    log_success "kvm 用户组已创建"
else
    log_success "kvm 用户组已存在"
fi

# 6. 创建虚拟化配置文件
log ""
log "[6/6] 配置虚拟化..."
LIBVIRTD_CONF="/etc/libvirt/qemu.conf"
if [ ! -f "$LIBVIRTD_CONF" ]; then
    log "创建 libvirt QEMU 配置..."
    cat > "$LIBVIRTD_CONF" << 'EOF'
# QEMU 配置
# 允许非 root 用户访问
user = "root"
group = "kvm"
# 取消注释以使用 NVIDIA GPU
#nvidia_iommu = 1
EOF
    log_success "libvirt QEMU 配置已创建"
else
    log_success "libvirt QEMU 配置已存在"
fi

# 更新 initramfs
log ""
log "更新 initramfs..."
update-initramfs -u -k all
log_success "initramfs 已更新"

# 完成
log ""
log "=== 修复完成 ==="
log ""
log "下一步操作："
log "  1. ${YELLOW}重启系统${NC}（使所有更改生效）"
log "  2. 检查 IOMMU: ${GREEN}ls -l /sys/kernel/iommu_groups/${NC}"
log "  3. 测试切换模式: 使用 GPU 控制面板"
log ""
log "配置文件位置："
log "  • VFIO: ${GREEN}/etc/modprobe.d/vfio.conf${NC}"
log "  • 黑名单: ${GREEN}/etc/modprobe.d/blacklist-nouveau.conf${NC}"
log "  • GRUB: ${GREEN}/etc/default/grub${NC}"
log ""
