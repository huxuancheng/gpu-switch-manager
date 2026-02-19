#!/bin/bash
# 安全热切换脚本 - 增强版
# 增加更多安全检查和恢复机制

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 配置
NVIDIA_VGA="10de:2206"
NVIDIA_AUDIO="10de:1a86"
GPU_BUS="0000:02:00.0"
AUDIO_BUS="0000:02:00.1"
BACKUP_DIR="/tmp/gpu-hotplug-backup"

# 自动模式（非交互式），用于 GUI 调用
AUTO_MODE=false

# 解析参数
for arg in "$@"; do
    case $arg in
        --auto)
            AUTO_MODE=true
            shift
            ;;
        *)
            ;;
    esac
done

# 创建备份目录
mkdir -p "$BACKUP_DIR"

# 日志函数
log() { echo -e "$1" | tee -a "$BACKUP_DIR/hotplug.log"; }
log_error() { log "${RED}[错误] $1${NC}"; }
log_success() { log "${GREEN}[成功] $1${NC}"; }
log_warning() { log "${YELLOW}[警告] $1${NC}"; }
log_info() { log "${BLUE}[信息] $1${NC}"; }

# 保存当前状态
backup_state() {
    log_info "备份当前状态..."
    {
        date
        echo "=== 驱动状态 ==="
        lsmod | grep -E "nvidia|vfio"
        echo "=== GPU 驱动 ==="
        lspci -nnk -d $NVIDIA_VGA 2>/dev/null
    } > "$BACKUP_DIR/state_$(date +%Y%m%d_%H%M%S).txt"
}

# 检查 GPU 占用（增强版）
check_gpu_usage() {
    log_info "检查 GPU 使用情况..."

    local found_usage=false

    # 1. 检查计算进程
    if command -v nvidia-smi >/dev/null 2>&1; then
        processes=$(nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader 2>/dev/null)
        if [ -n "$processes" ]; then
            log_warning "检测到计算进程正在使用 GPU:"
            echo "$processes" | tee -a "$BACKUP_DIR/hotplug.log" | while IFS=, read -r pid name mem; do
                log_warning "  - PID: $(echo $pid | tr -d ' '), 进程: $(echo $name | tr -d ' '), 显存: $(echo $mem | tr -d ' ') MB"
            done
            found_usage=true
        fi
    fi

    # 2. 检查 /dev/nvidia 设备占用
    if [ -e /dev/nvidia0 ]; then
        device_users=$(sudo lsof /dev/nvidia* 2>/dev/null | grep -v COMMAND || true)
        if [ -n "$device_users" ]; then
            if [ "$found_usage" = false ]; then
                log_warning "检测到设备文件被占用:"
            fi
            echo "$device_users" | tee -a "$BACKUP_DIR/hotplug.log" | while read -r command pid user fd type device size node name; do
                if [ "$command" != "COMMAND" ]; then
                    log_warning "  - $command (PID: $pid, 用户: $user) - $name"
                fi
            done
            found_usage=true
        fi
    fi

    # 3. 检查常见图形进程
    local graphical_procs=("Xorg" "gnome-shell" "kwin_x11" "plasmashell")
    for proc in "${graphical_procs[@]}"; do
        if pgrep -x "$proc" >/dev/null 2>&1; then
            pids=$(pgrep -x "$proc" | head -3)
            if [ "$found_usage" = false ]; then
                log_warning "检测到图形进程:"
            fi
            log_warning "  - $proc (PID: $pids)"
            found_usage=true
        fi
    done

    # 4. 检查浏览器进程
    local browsers=("chrome" "chromium" "firefox")
    for browser in "${browsers[@]}"; do
        if pgrep -f "$browser" >/dev/null 2>&1; then
            count=$(pgrep -f "$browser" | wc -l)
            if [ "$found_usage" = false ]; then
                log_warning "检测到可能使用 GPU 的进程:"
            fi
            log_warning "  - $browser ($count 个进程)"
            found_usage=true
        fi
    done

    # 5. 检查游戏进程
    local games=("steam" "Lutris" "heroic" "minecraft")
    for game in "${games[@]}"; do
        if pgrep -if "$game" >/dev/null 2>&1; then
            if [ "$found_usage" = false ]; then
                log_warning "检测到游戏进程:"
            fi
            log_warning "  - $game (PID: $(pgrep -if "$game" | head -1))"
            found_usage=true
        fi
    done

    if [ "$found_usage" = false ]; then
        log_success "未检测到 GPU 占用"
        return 0
    fi

    return 1
}

# 强制停止 GPU 进程
force_stop_gpu() {
    log_warning "强制停止 GPU 相关进程..."

    # 1. 停止 display-manager
    systemctl stop display-manager 2>/dev/null || true
    systemctl stop gdm 2>/dev/null || true
    systemctl stop sddm 2>/dev/null || true
    sleep 2

    # 2. 杀死 NVIDIA 进程
    killall -9 nvidia-smi 2>/dev/null || true
    killall -9 nvidia-persistenced 2>/dev/null || true
    sleep 1

    # 3. 强制释放设备
    if [ -e /dev/nvidia0 ]; then
        sudo fuser -k /dev/nvidia* 2>/dev/null || true
    fi
    sleep 1

    log_success "已停止所有 GPU 进程"
}

# 检查 IOMMU
check_iommu() {
    log_info "检查 IOMMU 状态..."
    if [ ! -d /sys/kernel/iommu_groups ]; then
        log_error "IOMMU 未启用，无法进行热切换"
        return 1
    fi
    log_success "IOMMU 已启用"
    return 0
}

# 检查虚拟机
check_vms() {
    log_info "检查虚拟机状态..."

    if command -v virsh >/dev/null 2>&1; then
        running_vms=$(virsh list --name --state-running 2>/dev/null)
        if [ -n "$running_vms" ]; then
            log_error "以下虚拟机正在运行，请先关闭:"
            echo "$running_vms" | tee -a "$BACKUP_DIR/hotplug.log"
            return 1
        fi
    fi

    log_success "无运行中的虚拟机"
    return 0
}

# 安全卸载 NVIDIA 驱动
safe_unload_nvidia() {
    log_info "卸载 NVIDIA 驱动..."

    # 尝试正常卸载
    rmmod nvidia_drm nvidia_modeset nvidia_uvm nvidia 2>/dev/null
    if [ $? -eq 0 ]; then
        log_success "NVIDIA 驱动卸载成功"
        return 0
    fi

    # 卸载失败，强制停止进程后重试
    log_warning "正常卸载失败，尝试强制停止进程..."
    force_stop_gpu
    sleep 2

    # 再次尝试卸载
    rmmod nvidia_drm nvidia_modeset nvidia_uvm nvidia 2>/dev/null
    if [ $? -eq 0 ]; then
        log_success "NVIDIA 驱动卸载成功"
        return 0
    fi

    log_error "NVIDIA 驱动卸载失败"
    log_info "已使用的模块:"
    lsmod | grep nvidia | tee -a "$BACKUP_DIR/hotplug.log"
    return 1
}

# 切换到直通模式
enable_passthrough() {
    log_info "切换到直通模式..."

    # 安全检查
    check_iommu || return 1
    check_vms || return 1

    # 备份状态
    backup_state

    # 检查 GPU 占用
    if ! check_gpu_usage; then
        if [ "$AUTO_MODE" = true ]; then
            log_warning "检测到 GPU 占用，自动模式将强制停止进程..."
            force_stop_gpu
        else
            log_warning "检测到 GPU 占用，是否强制停止? (yes/no)"
            read -p "> " answer
            if [ "$answer" = "yes" ]; then
                force_stop_gpu
            else
                log_error "已取消切换"
                return 1
            fi
        fi
    fi

    # 卸载 NVIDIA 驱动
    safe_unload_nvidia || return 1

    # 解绑设备
    log_info "解绑 GPU 设备..."
    if [ -e "/sys/bus/pci/drivers/nvidia/$GPU_BUS" ]; then
        echo -n "$GPU_BUS" > /sys/bus/pci/drivers/nvidia/unbind 2>/dev/null
        log_success "GPU 已解绑"
    fi

    if [ -e "/sys/bus/pci/drivers/snd_hda_intel/$AUDIO_BUS" ]; then
        echo -n "$AUDIO_BUS" > /sys/bus/pci/drivers/snd_hda_intel/unbind 2>/dev/null
        log_success "音频设备已解绑"
    fi

    sleep 2

    # 绑定到 VFIO
    log_info "绑定到 VFIO 驱动..."
    if ! echo "$GPU_BUS" > /sys/bus/pci/drivers/vfio-pci/bind 2>/dev/null; then
        log_warning "绑定失败，重新加载 VFIO 模块..."
        rmmod vfio_pci vfio vfio_iommu_type1 2>/dev/null
        modprobe vfio_pci ids=$NVIDIA_VGA,$NVIDIA_AUDIO
        modprobe vfio vfio_iommu_type1
        sleep 1
        echo "$GPU_BUS" > /sys/bus/pci/drivers/vfio-pci/bind 2>/dev/null
    fi

    # 验证结果
    if lspci -nnk -d $NVIDIA_VGA | grep -q "vfio-pci"; then
        log_success "✓ 直通模式已启用"
        log_info "现在可以启动虚拟机进行直通"
        return 0
    else
        log_error "✗ 直通模式启用失败"
        log_info "当前驱动状态:"
        lspci -nnk -d $NVIDIA_VGA | tee -a "$BACKUP_DIR/hotplug.log"
        return 1
    fi
}

# 切换到正常模式
enable_normal() {
    log_info "切换到正常模式..."

    # 检查虚拟机
    check_vms || return 1

    # 备份状态
    backup_state

    # 解绑 VFIO
    log_info "解绑 VFIO 设备..."
    if [ -e "/sys/bus/pci/drivers/vfio-pci/$GPU_BUS" ]; then
        echo -n "$GPU_BUS" > /sys/bus/pci/drivers/vfio-pci/unbind 2>/dev/null
        log_success "GPU 已从 VFIO 解绑"
    fi

    sleep 1

    # 加载 NVIDIA 驱动
    log_info "加载 NVIDIA 驱动..."
    modprobe nvidia
    modprobe nvidia_uvm
    modprobe nvidia_modeset
    modprobe nvidia_drm

    sleep 2

    # 验证结果
    if lsmod | grep -q "^nvidia "; then
        log_success "✓ 正常模式已启用"
        log_info "重启显示服务: sudo systemctl start display-manager"
        return 0
    else
        log_error "✗ 正常模式启用失败"
        return 1
    fi
}

# 主程序
log_info "GPU 安全热切换脚本"
log_info "日志文件: $BACKUP_DIR/hotplug.log"
echo ""

case "${1:-help}" in
    status)
        echo -e "${GREEN}=== 当前状态 ===${NC}"
        lspci -nnk -d $NVIDIA_VGA | grep "Kernel driver"
        ;;
    passthrough|pt)
        enable_passthrough
        ;;
    normal|nm)
        enable_normal
        ;;
    logs)
        log_info "查看最近日志:"
        tail -20 "$BACKUP_DIR/hotplug.log"
        ;;
    check)
        check_iommu && check_vms && check_gpu_usage
        ;;
    help|--help|-h)
        echo -e "${GREEN}GPU 安全热切换脚本${NC}"
        echo ""
        echo "用法: $0 [命令] [选项]"
        echo ""
        echo "命令:"
        echo "  status       显示当前驱动状态"
        echo "  passthrough  切换到直通模式（安全）"
        echo "  normal       切换到正常模式"
        echo "  check        运行安全检查"
        echo "  logs         查看操作日志"
        echo "  help         显示帮助信息"
        echo ""
        echo "选项:"
        echo "  --auto       自动模式，跳过交互式确认（用于 GUI）"
        echo ""
        echo "示例:"
        echo "  $0 passthrough       # 交互式切换到直通"
        echo "  $0 passthrough --auto # 自动切换到直通"
        echo "  $0 check            # 运行安全检查"
        echo ""
        ;;
    *)
        log_error "未知命令: $1"
        $0 help
        exit 1
        ;;
esac
