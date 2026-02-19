#!/bin/bash
# GPU 手动切换指引（无需 root）

echo "=== GPU 当前状态 ==="

# 显示驱动信息
echo -e "\n当前驱动:"
lspci -nnk -d 10de:2206 | grep "Kernel driver" | sed 's/^/  /'

# 显示模块状态
echo -e "\n加载的模块:"
lsmod | grep -E "^nvidia |^vfio" | awk '{print "  " $1}' || echo "  (无)"

# 显示 IOMMU 状态
echo -e "\nIOMMU 状态:"
if [ -d /sys/kernel/iommu_groups ]; then
    echo "  ✓ 已启用 (热切换可用)"
else
    echo "  ✗ 未启用 (需要重启)"
fi

echo -e "\n=== 手动切换命令 ==="

echo -e "\n[切换到直通模式]"
echo "  需要运行:"
echo "    sudo modprobe -r nvidia_drm nvidia_modeset nvidia_uvm nvidia"
echo "    sudo echo '0000:02:00.0' > /sys/bus/pci/drivers/nvidia/unbind"
echo "    sudo echo '0000:02:00.0' > /sys/bus/pci/drivers/vfio-pci/bind"
echo ""
echo "  验证:"
echo "    lspci -nnk -d 10de:2206 | grep vfio-pci"

echo -e "\n[切换到正常模式]"
echo "  需要运行:"
echo "    sudo echo '0000:02:00.0' > /sys/bus/pci/drivers/vfio-pci/unbind"
echo "    sudo echo '0000:02:00.0' > /sys/bus/pci/drivers/nvidia/bind"
echo "    sudo modprobe nvidia nvidia_uvm nvidia_modeset nvidia_drm"
echo ""
echo "  验证:"
echo "    lsmod | grep nvidia"

echo -e "\n[故障排除]"
echo "  如果切换失败，尝试:"
echo "    sudo rmmod vfio_pci vfio vfio_iommu_type1"
echo "    sudo modprobe vfio_pci ids=10de:2206,10de:1a86"
echo "    sudo modprobe vfio vfio_iommu_type1"

echo ""
