#!/bin/bash
# GPU 进程清理脚本
# 帮助用户安全地关闭占用 GPU 的应用

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 检查 root 权限
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}错误: 请使用 sudo 运行此脚本${NC}"
    echo -e "${YELLOW}使用: sudo $0${NC}"
    exit 1
fi

# 检查命令行参数
AUTO_MODE=false
QUICK_ONLY=false

case "$1" in
    cleanup-quick)
        AUTO_MODE=true
        QUICK_ONLY=true
        ;;
    cleanup-full)
        AUTO_MODE=true
        QUICK_ONLY=false
        ;;
esac

if [ "$AUTO_MODE" = false ]; then
    echo -e "${BLUE}=== GPU 进程清理工具 ===${NC}\n"
fi

# 显示菜单
show_menu() {
    echo -e "${CYAN}请选择要执行的操作:${NC}"
    echo ""
    echo "  1) 显示占用 GPU 的进程"
    echo "  2) 关闭所有计算/CUDA 进程"
    echo "  3) 关闭浏览器进程"
    echo "  4) 停止显示服务"
    echo "  5) 强制释放 /dev/nvidia 设备"
    echo "  6) 全部清理（推荐用于热切换）"
    echo "  7) 重启显示服务"
    echo "  0) 退出"
    echo ""
}

# 1. 显示占用 GPU 的进程
show_gpu_processes() {
    echo -e "${BLUE}=== GPU 占用进程 ===${NC}\n"

    if command -v nvidia-smi >/dev/null 2>&1; then
        echo -e "${CYAN}[计算/CUDA 进程]${NC}"
        processes=$(nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader 2>/dev/null)
        if [ -z "$processes" ]; then
            echo -e "  ${GREEN}✓ 无计算进程${NC}"
        else
            echo "$processes" | while IFS=, read -r pid name mem; do
                echo -e "  ${YELLOW}PID: $pid | 进程: $name | 显存: ${mem} MB${NC}"
                if [ -f "/proc/$pid/cmdline" ]; then
                    cmdline=$(cat "/proc/$pid/cmdline" | tr '\0' ' ' | head -c 80)
                    echo -e "     命令: $cmdline..."
                fi
            done
        fi
    fi

    echo -e "\n${CYAN}[图形进程]${NC}"
    graphical_procs=("Xorg" "X" "gnome-shell" "kwin_x11" "kwin_wayland" "plasmashell" "compton" "picom")
    for proc in "${graphical_procs[@]}"; do
        if pgrep -x "$proc" >/dev/null 2>&1; then
            pids=$(pgrep -x "$proc" | tr '\n' ' ')
            echo -e "  ${YELLOW}$proc (PID: $pids)${NC}"
        fi
    done

    echo -e "\n${CYAN}[浏览器进程]${NC}"
    browsers=("chrome" "chromium" "firefox")
    for browser in "${browsers[@]}"; do
        if pgrep -f "$browser" >/dev/null 2>&1; then
            count=$(pgrep -f "$browser" | wc -l)
            echo -e "  ${YELLOW}$browser ($count 个进程)${NC}"
        fi
    done

    echo -e "\n${CYAN}[设备文件占用]${NC}"
    if [ -e /dev/nvidia0 ]; then
        device_users=$(lsof /dev/nvidia* 2>/dev/null | grep -v COMMAND | head -5 || true)
        if [ -n "$device_users" ]; then
            echo "$device_users" | while read -r command pid user fd type device size node name; do
                echo -e "  ${YELLOW}$command (PID: $pid) - $name${NC}"
            done
        else
            echo -e "  ${GREEN}✓ 无设备占用${NC}"
        fi
    fi
    echo ""
}

# 2. 关闭计算/CUDA 进程
kill_compute_processes() {
    echo -e "${YELLOW}正在关闭计算/CUDA 进程...${NC}"

    if command -v nvidia-smi >/dev/null 2>&1; then
        pids=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null)
        if [ -n "$pids" ]; then
            echo "$pids" | while read -r pid; do
                pid=$(echo "$pid" | tr -d ' ')
                if [ -n "$pid" ]; then
                    kill -15 "$pid" 2>/dev/null
                    sleep 1
                    # 如果还在运行，强制杀死
                    if kill -0 "$pid" 2>/dev/null; then
                        kill -9 "$pid" 2>/dev/null
                        echo -e "  ${RED}已强制终止 PID $pid${NC}"
                    else
                        echo -e "  ${GREEN}已终止 PID $pid${NC}"
                    fi
                fi
            done
        else
            echo -e "  ${GREEN}无计算进程需要关闭${NC}"
        fi
    else
        echo -e "  ${YELLOW}nvidia-smi 不可用${NC}"
    fi

    # 杀死 NVIDIA 持久化守护进程
    if pgrep nvidia-persistenced >/dev/null 2>&1; then
        killall -9 nvidia-persistenced 2>/dev/null
        echo -e "  ${GREEN}已停止 nvidia-persistenced${NC}"
    fi

    if pgrep nvidia-smi >/dev/null 2>&1; then
        killall -9 nvidia-smi 2>/dev/null
        echo -e "  ${GREEN}已停止 nvidia-smi${NC}"
    fi

    echo ""
}

# 3. 关闭浏览器进程
kill_browsers() {
    echo -e "${YELLOW}正在关闭浏览器进程...${NC}"

    browsers=("chrome" "chromium" "firefox" "firefox-bin")
    for browser in "${browsers[@]}"; do
        if pgrep -f "$browser" >/dev/null 2>&1; then
            count=$(pgrep -f "$browser" | wc -l)
            killall -15 "$browser" 2>/dev/null
            sleep 2
            if pgrep -f "$browser" >/dev/null 2>&1; then
                killall -9 "$browser" 2>/dev/null
                echo -e "  ${GREEN}已强制关闭 $browser ($count 个进程)${NC}"
            else
                echo -e "  ${GREEN}已关闭 $browser ($count 个进程)${NC}"
            fi
        fi
    done
    echo ""
}

# 4. 停止显示服务
stop_display() {
    echo -e "${YELLOW}正在停止显示服务...${NC}"

    if systemctl is-active --quiet display-manager 2>/dev/null; then
        systemctl stop display-manager
        echo -e "  ${GREEN}已停止 display-manager${NC}"
    elif systemctl is-active --quiet gdm 2>/dev/null; then
        systemctl stop gdm
        echo -e "  ${GREEN}已停止 gdm${NC}"
    elif systemctl is-active --quiet sddm 2>/dev/null; then
        systemctl stop sddm
        echo -e "  ${GREEN}已停止 sddm${NC}"
    elif systemctl is-active --quiet lightdm 2>/dev/null; then
        systemctl stop lightdm
        echo -e "  ${GREEN}已停止 lightdm${NC}"
    else
        echo -e "  ${YELLOW}未找到运行中的显示服务${NC}"
    fi
    echo ""
}

# 5. 强制释放设备
force_release_device() {
    echo -e "${YELLOW}正在释放 /dev/nvidia 设备...${NC}"

    if [ -e /dev/nvidia0 ]; then
        fuser -k /dev/nvidia* 2>/dev/null
        echo -e "  ${GREEN}已强制释放 /dev/nvidia 设备${NC}"
    else
        echo -e "  ${YELLOW}/dev/nvidia0 不存在${NC}"
    fi
    echo ""
}

# 6. 全部清理
full_cleanup() {
    echo -e "${RED}执行完整清理...${NC}\n"

    echo -e "${YELLOW}[1/5] 关闭计算/CUDA 进程${NC}"
    kill_compute_processes

    echo -e "${YELLOW}[2/5] 关闭浏览器进程${NC}"
    kill_browsers

    echo -e "${YELLOW}[3/5] 停止显示服务${NC}"
    stop_display

    echo -e "${YELLOW}[4/5] 释放 GPU 设备${NC}"
    force_release_device

    echo -e "${YELLOW}[5/5] 等待设备释放...${NC}"
    sleep 3

    echo -e "\n${GREEN}✓ 清理完成！${NC}"
    echo -e "${BLUE}现在可以安全地执行热切换了${NC}\n"
}

# 7. 重启显示服务
restart_display() {
    echo -e "${YELLOW}正在重启显示服务...${NC}"

    # 确保显示服务已停止
    systemctl stop display-manager gdm sddm lightdm 2>/dev/null || true

    sleep 2

    # 启动显示服务
    systemctl start display-manager 2>/dev/null || \
    systemctl start gdm 2>/dev/null || \
    systemctl start sddm 2>/dev/null || \
    systemctl start lightdm 2>/dev/null || \
    echo -e "  ${YELLOW}无法自动启动显示服务，请手动启动${NC}"

    if [ $? -eq 0 ]; then
        echo -e "  ${GREEN}显示服务已重启${NC}"
    fi
    echo ""
}

# 主循环
while true; do
    show_menu
    read -p "请输入选项 [0-7]: " choice
    echo ""

    case $choice in
        1)
            show_gpu_processes
            read -p "按 Enter 继续..."
            ;;
        2)
            kill_compute_processes
            echo -e "${GREEN}计算进程已关闭${NC}"
            read -p "按 Enter 继续..."
            ;;
        3)
            echo -e "${YELLOW}警告: 这将关闭所有浏览器进程！${NC}"
            read -p "确认继续? (yes/no): " confirm
            if [ "$confirm" = "yes" ]; then
                kill_browsers
            fi
            if [ "$AUTO_MODE" = false ]; then
                read -p "按 Enter 继续..."
            fi
            ;;
        4)
            echo -e "${RED}警告: 停止显示服务将导致图形界面关闭！${NC}"
            read -p "确认继续? (yes/no): " confirm
            if [ "$confirm" = "yes" ]; then
                stop_display
            fi
            if [ "$AUTO_MODE" = false ]; then
                read -p "按 Enter 继续..."
            fi
            ;;
        5)
            force_release_device
            echo -e "${GREEN}设备已释放${NC}"
            if [ "$AUTO_MODE" = false ]; then
                read -p "按 Enter 继续..."
            fi
            ;;
        6)
            echo -e "${RED}警告: 这将关闭所有 GPU 相关进程！${NC}"
            echo -e "${RED}显示服务也会停止！${NC}"
            read -p "确认继续? (yes/no): " confirm
            if [ "$confirm" = "yes" ]; then
                full_cleanup
            fi
            if [ "$AUTO_MODE" = false ]; then
                read -p "按 Enter 继续..."
            fi
            ;;
        7)
            restart_display
            if [ "$AUTO_MODE" = false ]; then
                read -p "按 Enter 继续..."
            fi
            ;;
        0)
            if [ "$AUTO_MODE" = false ]; then
                echo -e "${GREEN}退出${NC}"
            fi
            exit 0
            ;;
        *)
            echo -e "${RED}无效选项，请重新选择${NC}"
            if [ "$AUTO_MODE" = false ]; then
                read -p "按 Enter 继续..."
            fi
            ;;
    esac
done

# 自动模式入口
if [ "$AUTO_MODE" = true ]; then
    echo -e "${BLUE}=== GPU 进程清理 ===${NC}\n"

    if [ "$QUICK_ONLY" = true ]; then
        echo -e "${YELLOW}[快速清理]${NC}"
        kill_compute_processes
        kill_browsers
        echo -e "${GREEN}✓ 快速清理完成${NC}"
    else
        echo -e "${YELLOW}[完整清理]${NC}"
        full_cleanup
    fi

    echo ""
    exit 0
fi
