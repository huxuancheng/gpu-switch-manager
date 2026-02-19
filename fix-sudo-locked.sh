#!/bin/bash
# Sudo 被锁一键修复脚本

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Sudo 被锁修复工具 ===${NC}\n"

# 检查是否以 root 身份运行
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}✗ 此脚本需要 root 权限运行${NC}"
    echo -e "${YELLOW}请使用: sudo bash $0${NC}"
    exit 1
fi

USERNAME=${SUDO_USER:-$(whoami)}
echo -e "修复用户: ${GREEN}${USERNAME}${NC}\n"

# 1. 将用户添加到 sudo 组
echo -e "${BLUE}[1/4] 添加用户到 sudo 组...${NC}"
if groups "$USERNAME" | grep -q "\bsudo\b"; then
    echo -e "  ${GREEN}✓ 用户已在 sudo 组${NC}"
else
    usermod -aG sudo "$USERNAME"
    echo -e "  ${GREEN}✓ 已添加到 sudo 组${NC}"
fi
echo ""

# 2. 配置 sudo 超时时间
echo -e "${BLUE}[2/4] 配置 sudo 超时时间...${NC}"
SUDOERS_D="/etc/sudoers.d"
TIMEOUT_FILE="$SUDOERS_D/sudo_timeout"

if [ ! -d "$SUDOERS_D" ]; then
    mkdir -p "$SUDOERS_D"
    chmod 755 "$SUDOERS_D"
fi

# 检查是否已存在配置
if [ -f "$TIMEOUT_FILE" ]; then
    echo -e "  ${YELLOW}⚠ 配置已存在，正在备份...${NC}"
    cp "$TIMEOUT_FILE" "${TIMEOUT_FILE}.bak.$(date +%Y%m%d%H%M%S)"
fi

# 创建新的超时配置（30分钟）
cat > "$TIMEOUT_FILE" << 'EOF'
# Sudo 超时配置 - 自动生成
Defaults timestamp_timeout=30
Defaults !tty_tickets
EOF

chmod 0440 "$TIMEOUT_FILE"
echo -e "  ${GREEN}✓ 已配置 sudo 超时为 30 分钟${NC}"
echo ""

# 3. 创建 Polkit 规则（允许 GUI 程序免密）
echo -e "${BLUE}[3/4] 配置 Polkit 规则...${NC}"
POLKIT_DIR="/etc/polkit-1/rules.d"
POLKIT_FILE="$POLKIT_DIR/99-gpu-manager.rules"

if [ ! -d "$POLKIT_DIR" ]; then
    echo -e "  ${YELLOW}⚠ Polkit 规则目录不存在，跳过${NC}"
else
    cat > "$POLKIT_FILE" << EOF
// Polkit 规则 - 允许 GPU 管理工具免密运行
polkit.addRule(function(action, subject) {
    if (subject.user == "${USERNAME}" &&
        (action.id.startsWith("org.freedesktop.policykit.exec") ||
         action.id.indexOf("gpu") !== -1)) {
        return polkit.Result.YES;
    }
});
EOF
    chmod 644 "$POLKIT_FILE"
    echo -e "  ${GREEN}✓ 已创建 Polkit 规则${NC}"
fi
echo ""

# 4. 清除可能的账户锁定
echo -e "${BLUE}[4/4] 重置可能的账户锁定...${NC}"
if command -v faillog >/dev/null 2>&1; then
    faillog -u "$USERNAME" -r 2>/dev/null && echo -e "  ${GREEN}✓ 已重置失败登录计数${NC}" || echo -e "  ${YELLOW}⚠ 无需重置${NC}"
fi

if command -v pam_tally2 >/dev/null 2>&1; then
    pam_tally2 --user "$USERNAME" --reset 2>/dev/null && echo -e "  ${GREEN}✓ 已重置 PAM 失败计数${NC}" || echo -e "  ${YELLOW}⚠ 无需重置${NC}"
fi
echo ""

# 完成
echo -e "${GREEN}=== 修复完成 ===${NC}\n"
echo -e "${BLUE}下一步操作:${NC}"
echo -e "  1. ${YELLOW}注销并重新登录${NC}（使 sudo 组生效）"
echo -e "  2. 测试 sudo: ${GREEN}sudo -v${NC}"
echo -e "  3. 测试 GUI 提权: ${GREEN}运行 GPU 控制面板${NC}"
echo ""
echo -e "${BLUE}配置说明:${NC}"
echo -e "  • Sudo 超时时间: ${GREEN}30 分钟${NC}"
echo -e "  • 用户已添加到: ${GREEN}sudo 组${NC}"
echo -e "  • Polkit 规则: ${GREEN}已配置${NC}"
echo ""
