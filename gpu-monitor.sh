#!/bin/bash
# GPU 占用监控脚本 - 高级版
# 自动检查并显示使用 GPU 的所有进程

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 颜色标记
MARKER_CRITICAL="${RED}⚠️${NC}"
MARKER_WARNING="${YELLOW}⚡${NC}"
MARKER_INFO="${CYAN}ℹ️${NC}"
MARKER_OK="${GREEN}✓${NC}"

echo -e "${BLUE}=== GPU 占用监控 ===${NC}\n"

# 检查 nvidia-smi 是否可用
if ! command -v nvidia-smi >/dev/null 2>&1; then
    echo -e "${RED}✗ nvidia-smi 不可用${NC}"
    echo -e "${YELLOW}请确保已安装 NVIDIA 驱动${NC}"
    exit 1
fi

# 获取 GPU 使用情况摘要
echo -e "${CYAN}[1] GPU 使用摘要${NC}"
nvidia-smi --query-gpu=index,name,utilization.gpu,utilization.memory,memory.used,memory.total \
    --format=csv,noheader,nounits | while IFS=, read -r idx name gpu_util mem_util mem_used mem_total; do
    gpu_util=$(echo "$gpu_util" | tr -d ' ')
    mem_util=$(echo "$mem_util" | tr -d ' ')

    if [ "$gpu_util" -gt 80 ] || [ "$mem_util" -gt 80 ]; then
        status="${MARKER_CRITICAL}"
    elif [ "$gpu_util" -gt 30 ] || [ "$mem_util" -gt 30 ]; then
        status="${MARKER_WARNING}"
    else
        status="${MARKER_OK}"
    fi

    echo -e "  GPU $idx: ${status} ${name}"
    echo -e "    GPU 利用率: ${gpu_util}% | 内存利用率: ${mem_util}%"
    echo -e "    显存: ${mem_used} MB / ${mem_total} MB\n"
done

# 检查计算进程
echo -e "${CYAN}[2] 计算/CUDA 进程${NC}"
processes=$(nvidia-smi --query-compute-apps=pid,process_name,used_memory,used_gpu --format=csv,noheader,nounits 2>/dev/null)

if [ -z "$processes" ]; then
    echo -e "  ${GREEN}✓ 无计算进程正在使用 GPU${NC}"
else
    echo -e "  ${YELLOW}检测到以下进程:${NC}"
    echo "$processes" | while IFS=, read -r pid name mem gpu; do
        pid=$(echo "$pid" | tr -d ' ')
        name=$(echo "$name" | tr -d ' ')
        mem=$(echo "$mem" | tr -d ' ')
        gpu=$(echo "$gpu" | tr -d ' ')

        echo -e "    ${MARKER_WARNING} PID: ${CYAN}$pid${NC} | 进程: ${name}"
        echo -e "         显存: ${mem} MB | GPU ID: ${gpu}"

        # 尝试获取更多信息
        if [ -f "/proc/$pid/cmdline" ]; then
            cmdline=$(cat "/proc/$pid/cmdline" | tr '\0' ' ' | head -c 100)
            echo -e "         命令: ${cmdline}..."
        fi
        echo ""
    done
fi

# 检查图形进程（X11/Wayland）
echo -e "\n${CYAN}[3] 图形相关进程${NC}"
# 检查常见图形进程
graphical_procs=("Xorg" "X" "gnome-shell" "kwin_x11" "kwin_wayland" "plasmashell" "compton" "picom")
found_gui=false

for proc in "${graphical_procs[@]}"; do
    if pgrep -x "$proc" >/dev/null 2>&1; then
        pids=$(pgrep -x "$proc" | head -5)
        echo -e "  ${MARKER_INFO} $proc 进程: ${GREEN}运行中${NC} (PID: $pids)"
        found_gui=true
    fi
done

if [ "$found_gui" = false ]; then
    echo -e "  ${GREEN}✓ 未检测到常见图形进程${NC}"
fi

# 检查 /dev/nvidia 设备占用
echo -e "\n${CYAN}[4] 设备文件占用${NC}"
if [ -e /dev/nvidia0 ]; then
    device_users=$(sudo lsof /dev/nvidia* 2>/dev/null | grep -v COMMAND || true)
    if [ -n "$device_users" ]; then
        echo -e "  ${YELLOW}以下进程正在访问 /dev/nvidia:*${NC}"
        echo "$device_users" | while read -r command pid user fd type device size node name; do
            if [ "$command" != "COMMAND" ]; then
                echo -e "    ${MARKER_WARNING} $command (PID: $pid, 用户: $user) - $name"
            fi
        done
    else
        echo -e "  ${GREEN}✓ 无进程访问 /dev/nvidia:*${NC}"
    fi
else
    echo -e "  ${YELLOW}⚠ /dev/nvidia0 不存在 (NVIDIA 驱动可能未加载)${NC}"
fi

# 检查浏览器进程（常见 GPU 使用者）
echo -e "\n${CYAN}[5] 浏览器进程（可能使用 GPU 加速）${NC}"
browser_procs=("chrome" "chromium" "firefox" "firefox-bin")
browser_found=false

for browser in "${browser_procs[@]}"; do
    if pgrep -f "$browser" >/dev/null 2>&1; then
        count=$(pgrep -f "$browser" | wc -l)
        echo -e "  ${MARKER_INFO} $browser: ${GREEN}运行中${NC} ($count 个进程)"
        browser_found=true
    fi
done

if [ "$browser_found" = false ]; then
    echo -e "  ${GREEN}✓ 未检测到浏览器进程${NC}"
fi

# 检查游戏进程
echo -e "\n${CYAN}[6] 游戏进程${NC}"
game_procs=("steam" "steamwebhelper" "Lutris" "heroic" "minecraft" "prerelease" "wow.exe" "csgo_linux64")
game_found=false

for game in "${game_procs[@]}"; do
    if pgrep -if "$game" >/dev/null 2>&1; then
        pids=$(pgrep -if "$game" | head -3)
        echo -e "  ${MARKER_CRITICAL} 检测到: $game (PID: $pids)"
        game_found=true
    fi
done

if [ "$game_found" = false ]; then
    echo -e "  ${GREEN}✓ 未检测到游戏进程${NC}"
fi

# 生成摘要和建议
echo -e "\n${BLUE}=== 监控摘要 ===${NC}"

# 统计总进程数
total_procs=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | wc -l)
if [ "$total_procs" -gt 0 ]; then
    echo -e "${MARKER_WARNING} 共发现 $total_procs 个进程使用 GPU"
    echo -e "${YELLOW}建议:${NC}"
    echo -e "  1. 关闭使用 GPU 的应用"
    echo -e "  2. 关闭浏览器硬件加速"
    echo -e "  3. 退出游戏和其他 GPU 程序"
    echo -e "  4. 停止显示服务: sudo systemctl stop display-manager"
else
    echo -e "${GREEN}${MARKER_OK} GPU 空闲，可以进行热切换${NC}"
fi

echo -e "\n${CYAN}快速停止命令:${NC}"
echo -e "  停止 NVIDIA 进程: ${YELLOW}sudo killall -9 nvidia-smi nvidia-persistenced${NC}"
echo -e "  强制释放设备: ${YELLOW}sudo fuser -k /dev/nvidia*${NC}"
echo -e "  停止显示服务: ${YELLOW}sudo systemctl stop display-manager${NC}"

# 导出 JSON 格式（供程序使用）
if [ "$1" = "--json" ]; then
    echo -e "\n${BLUE}=== JSON 格式输出 ===${NC}"
    echo "{"
    echo "  \"gpu_processes\": $(nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits 2>/dev/null | wc -l),"
    echo "  \"device_access\": $([ -n "$device_users" ] && echo "true" || echo "false"),"
    echo "  \"gui_running\": $([ "$found_gui" = true ] && echo "true" || echo "false"),"
    echo "  \"browsers_running\": $([ "$browser_found" = true ] && echo "true" || echo "false"),"
    echo "  \"games_running\": $([ "$game_found" = true ] && echo "true" || echo "false")"
    echo "}"
fi
