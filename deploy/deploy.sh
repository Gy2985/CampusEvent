#!/usr/bin/env bash
# CampusEvent 一键部署脚本（Ubuntu 22.04 / Debian 12，root 或有 sudo 的账号执行）
#
# 用法：
#   sudo bash deploy.sh              # 默认从 Gitee 拉代码，监听 80 端口
#   PORT=8000 sudo -E bash deploy.sh # 换端口
#   REPO=https://github.com/Gy2985/CampusEvent.git sudo -E bash deploy.sh  # 换仓库源
#
# 脚本做的事：装 python3-venv/git → 拉代码 → 建虚拟环境装依赖 → 写 systemd 单元 →
# 启动并设为开机自启 → 打印访问地址与自检结果。可重复执行（幂等）。
set -euo pipefail

REPO=${REPO:-https://gitee.com/gong--yu/CampusEvent.git}
DIR=${DIR:-/opt/CampusEvent}
PORT=${PORT:-80}
SERVICE=${SERVICE:-campus-event}
SUDO=""
if [ "$(id -u)" -ne 0 ]; then SUDO="sudo"; fi

echo "==> 1/6 安装基础依赖"
export DEBIAN_FRONTEND=noninteractive
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq git python3-venv python3-pip curl >/dev/null

echo "==> 2/6 拉取代码到 $DIR"
if [ -d "$DIR/.git" ]; then
  $SUDO git -C "$DIR" fetch --all -q && $SUDO git -C "$DIR" reset --hard origin/main -q
else
  $SUDO rm -rf "$DIR"
  $SUDO git clone -q "$REPO" "$DIR"
fi

echo "==> 3/6 建虚拟环境并安装依赖"
if [ ! -x "$DIR/.venv/bin/python" ]; then
  $SUDO python3 -m venv "$DIR/.venv"
fi
$SUDO "$DIR/.venv/bin/pip" install -q --disable-pip-version-check -r "$DIR/requirements.txt"

echo "==> 4/6 首次启动自动建库（演示账号 S001/S002/S003、A001）"
$SUDO env DATABASE_PATH="$DIR/data/campus_event.db" "$DIR/.venv/bin/python" -c \
  "from campus_event import create_app; create_app(); print('database ready')"

echo "==> 5/6 写 systemd 服务 $SERVICE"
$SUDO tee "/etc/systemd/system/$SERVICE.service" >/dev/null <<UNIT
[Unit]
Description=CampusEvent 校园活动报名与管理系统
After=network.target

[Service]
Type=simple
WorkingDirectory=$DIR
Environment=PYTHONUNBUFFERED=1
Environment=DATABASE_PATH=$DIR/data/campus_event.db
Environment=SECRET_KEY=$(head -c 32 /dev/urandom | base64 | tr -d '\n')
ExecStart=$DIR/.venv/bin/gunicorn -w 2 -b 0.0.0.0:$PORT --timeout 60 app:app
Restart=always
RestartSec=3
User=root

[Install]
WantedBy=multi-user.target
UNIT
$SUDO systemctl daemon-reload
$SUDO systemctl enable -q "$SERVICE"
$SUDO systemctl restart "$SERVICE"
sleep 2

echo "==> 6/6 自检"
IP=$(curl -s --max-time 5 https://api.ipify.org || echo "服务器公网IP")
for i in 1 2 3 4 5; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/login" || true)
  [ "$code" = "200" ] && break
  sleep 2
done
echo "本地 /login 返回: ${code:-unknown}"
$SUDO systemctl --no-pager status "$SERVICE" | head -5 || true
echo
echo "访问地址：http://$IP$( [ "$PORT" = "80" ] && echo "" || echo ":$PORT" )"
echo "演示账号：S001 / S002 / S003（学生），A001（管理员），登录页无需密码"
echo "查看日志：journalctl -u $SERVICE -f    重启：systemctl restart $SERVICE"
