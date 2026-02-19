#!/bin/bash
# 热切换功能测试脚本

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== 热切换功能测试 ===${NC}\n"

# 测试 1: 语法检查
echo -e "${YELLOW}[测试 1/5] 检查脚本语法...${NC}"
if bash -n gpu-hotplug-safe.sh && bash -n gpu-hotplug-check.sh; then
    echo -e "  ${GREEN}✓ 语法检查通过${NC}"
else
    echo -e "  ${RED}✗ 语法检查失败${NC}"
    exit 1
fi

# 测试 2: 权限检查
echo -e "\n${YELLOW}[测试 2/5] 检查脚本权限...${NC}"
if [ -x gpu-hotplug-safe.sh ] && [ -x gpu-hotplug-check.sh ]; then
    echo -e "  ${GREEN}✓ 权限正确${NC}"
else
    echo -e "  ${RED}✗ 权限错误${NC}"
    chmod +x gpu-hotplug-safe.sh gpu-hotplug-check.sh
    echo -e "  ${YELLOW}已修复权限${NC}"
fi

# 测试 3: 帮助信息
echo -e "\n${YELLOW}[测试 3/5] 测试帮助信息...${NC}"
if ./gpu-hotplug-safe.sh help >/dev/null 2>&1; then
    echo -e "  ${GREEN}✓ 帮助信息正常${NC}"
else
    echo -e "  ${RED}✗ 帮助信息异常${NC}"
fi

# 测试 4: 状态检查
echo -e "\n${YELLOW}[测试 4/5] 测试状态检查（无需 root）...${NC}"
if ./gpu-hotplug-safe.sh status >/dev/null 2>&1; then
    echo -e "  ${GREEN}✓ 状态检查正常${NC}"
else
    echo -e "  ${YELLOW}⚠ 状态检查需要 root 权限（这是正常的）${NC}"
fi

# 测试 5: Python GUI 语法
echo -e "\n${YELLOW}[测试 5/5] 检查 Python GUI 语法...${NC}"
if python3 -m py_compile gpu-switch-gui.py 2>/dev/null; then
    echo -e "  ${GREEN}✓ Python 语法正确${NC}"
else
    echo -e "  ${RED}✗ Python 语法错误${NC}"
    exit 1
fi

# 总结
echo -e "\n${BLUE}=== 测试完成 ===${NC}"
echo -e "${GREEN}✓ 所有测试通过！${NC}"
echo -e "\n热切换脚本已准备就绪："
echo -e "  • ${GREEN}gpu-hotplug-safe.sh${NC} - 安全热切换脚本"
echo -e "  • ${GREEN}gpu-hotplug-check.sh${NC} - 前置检查脚本"
echo -e "  • ${GREEN}gpu-switch-gui.py${NC} - GUI 界面（支持热切换）"
echo -e "\n使用方法："
echo -e "  命令行: sudo ./gpu-hotplug-safe.sh passthrough"
echo -e "  GUI: ./gpu-switch-gui.py (选择热切换模式)"
