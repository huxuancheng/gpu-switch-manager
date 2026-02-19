#!/bin/bash
# 安全热切换前置检查脚本

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== GPU 热切换安全检查 ===${NC}\n"

# 1. 检查 IOMMU
echo -e "${YELLOW}[1/7] 检查 IOMMU 状态...${NC}"
if [ -d /sys/kernel/iommu_groups ]; then
    echo -e "  ${GREEN}✓ IOMMU 已启用${NC}"
    groups=$(ls /sys/kernel/iommu_groups/ 2>/dev/null | wc -l)
    echo "  检测到 $groups 个 IOMMU 组"
else
    echo -e "  ${RED}✗ IOMMU 未启用${NC}"
    echo "  请先在 GRUB 中添加: intel_iommu=on 或 amd_iommu=on"
    exit 1
fi

# 2. 检查 VFIO 模块
echo -e "\n${YELLOW}[2/7] 检查 VFIO 模块...${NC}"
if lsmod | grep -q "^vfio"; then
    echo -e "  ${GREEN}✓ VFIO 模块已加载${NC}"
else
    echo -e "  ${YELLOW}⚠ VFIO 模块未加载（首次使用会自动加载）${NC}"
fi

# 3. 检查 GPU 驱动
echo -e "\n${YELLOW}[3/7] 检查当前 GPU 驱动...${NC}"
NVIDIA_VGA="10de:2206"
current_driver=$(lspci -nnk -d $NVIDIA_VGA 2>/dev/null | grep "Kernel driver in use" | awk '{print $5}')
if [ -n "$current_driver" ]; then
    echo -e "  当前驱动: ${GREEN}$current_driver${NC}"
else
    echo -e "  ${YELLOW}⚠ 无法确定当前驱动${NC}"
fi

# 4. 检查 GPU 使用情况
echo -e "\n${YELLOW}[4/7] 检查 GPU 使用情况...${NC}"
if command -v nvidia-smi >/dev/null 2>&1; then
    processes=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null)
    if [ -n "$processes" ]; then
        echo -e "  ${RED}⚠ 有进程正在使用 GPU:${NC}"
        nvidia-smi --query-compute-apps=pid,process_name --format=csv,noheader 2>/dev/null | head -5
        echo "  请先关闭这些进程"
    else
        echo -e "  ${GREEN}✓ 无进程占用 GPU${NC}"
    fi
else
    echo -e "  ${YELLOW}⚠ nvidia-smi 不可用${NC}"
fi

# 5. 检查虚拟机状态
echo -e "\n${YELLOW}[5/7] 检查虚拟机状态...${NC}"
if command -v virsh >/dev/null 2>&1; then
    running_vms=$(virsh list --name --state-running 2>/dev/null)
    if [ -n "$running_vms" ]; then
        echo -e "  ${RED}⚠ 有虚拟机正在运行:${NC}"
        echo "$running_vms" | head -3
        echo "  请先关闭虚拟机"
    else
        echo -e "  ${GREEN}✓ 无运行中的虚拟机${NC}"
    fi
else
    echo -e "  ${YELLOW}⚠ libvirt 未安装${NC}"
fi

# 6. 检查显示服务
echo -e "\n${YELLOW}[6/7] 检查显示服务...${NC}"
if systemctl is-active --quiet display-manager 2>/dev/null || \
   systemctl is-active --quiet gdm 2>/dev/null || \
   systemctl is-active --quiet sddm 2>/dev/null; then
    echo -e "  ${YELLOW}⚠ 显示服务正在运行${NC}"
    echo "  切换到直通模式前需要停止显示服务"
else
    echo -e "  ${GREEN}✓ 显示服务未运行${NC}"
fi

# 7. 检查关键配置文件
echo -e "\n${YELLOW}[7/7] 检查关键配置...${NC}"
grub_ok=false
if grep -q "intel_iommu=on\|amd_iommu=on" /etc/default/grub 2>/dev/null; then
    echo -e "  ${GREEN}✓ GRUB IOMMU 配置正确${NC}"
    grub_ok=true
else
    echo -e "  ${RED}✗ GRUB 缺少 IOMMU 参数${NC}"
fi

if grep -q "pcie_aspm=off" /etc/default/grub 2>/dev/null; then
    echo -e "  ${GREEN}✓ GRUB PCIe ASPM 配置正确${NC}"
else
    echo -e "  ${YELLOW}⚠ 建议添加 pcie_aspm=off 到 GRUB${NC}"
fi

echo -e "\n${BLUE}=== 检查完成 ===${NC}"

if [ "$grub_ok" = true ]; then
    echo -e "${GREEN}✓ 可以进行安全热切换${NC}"
    echo "  使用: sudo ./gpu-switch-hotplug passthrough"
else
    echo -e "${RED}✗ 需要先配置 IOMMU（需要重启）${NC}"
    exit 1
fi
