#!/usr/bin/env bash
# =====================================================================
# نصب و به‌روزرسانی ربات آرشیو بله روی Ubuntu 24.04 — با یک دستور.
#
#   sudo bash /opt/balebot/src/bale-archive-bot/scripts/deploy.sh
#   sudo bash /opt/balebot/src/bale-archive-bot/scripts/deploy.sh --branch claude/merged-schema
#
# بدون --branch همان شاخه‌ای که الان نصب است به‌روز می‌شود.
# چند بار اجرا کردنش بی‌خطر است (برای به‌روزرسانی هم همین را بزنید).
# این اسکریپت هیچ دیتابیس یا جدولی نمی‌سازد و چیزی از دیتابیس را تغییر نمی‌دهد؛
# فقط پشتیبان می‌گیرد (mysqldump) و بررسی فقط‌خواندنی (preflight) انجام می‌دهد.
# =====================================================================
set -euo pipefail

# The script updates its own checkout below; run from a private copy so
# bash never reads a half-replaced file.
if [[ -z "${BALEBOT_DEPLOY_COPY:-}" && -f "$0" ]]; then
  copy="$(mktemp /tmp/balebot-deploy.XXXXXX.sh)"
  cp "$0" "$copy"
  BALEBOT_DEPLOY_COPY=1 exec bash "$copy" "$@"
fi

REPO_URL="${REPO_URL:-https://github.com/lampreymedia-coder/yadgiri.git}"
DEFAULT_BRANCH="claude/magical-tesla-sb2d7n"
# Branch: --branch <name> > BRANCH env > the branch already installed > default.
ARG_BRANCH=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch) ARG_BRANCH="${2:-}"; shift 2 ;;
    --branch=*) ARG_BRANCH="${1#--branch=}"; shift ;;
    *) echo "گزینه‌ی ناشناخته: $1 (فقط --branch <نام شاخه>)" >&2; exit 2 ;;
  esac
done
BASE=/opt/balebot
SRC="$BASE/src"
APP_DIR="$SRC/bale-archive-bot"
VENV="$BASE/venv"
DATA_DIR=/var/lib/balebot
ENV_DIR=/etc/balebot
ENV_FILE="$ENV_DIR/balebot.env"
SERVICE=balebot
MIRROR="${PIP_MIRROR:-https://mirror-pypi.runflare.com/simple}"
MIRROR_HOST="$(printf '%s' "$MIRROR" | sed -E 's#^[a-z]+://([^/:]+).*#\1#')"

INSTALLED_BRANCH=""
if [[ -d "$SRC/.git" ]]; then
  INSTALLED_BRANCH="$(git -C "$SRC" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  [[ "$INSTALLED_BRANCH" == "HEAD" ]] && INSTALLED_BRANCH=""
fi
BRANCH="${ARG_BRANCH:-${BRANCH:-${INSTALLED_BRANCH:-$DEFAULT_BRANCH}}}"
[[ "$BRANCH" =~ ^[A-Za-z0-9._/-]+$ ]] || { echo "نام شاخه معتبر نیست: $BRANCH" >&2; exit 2; }

step() { echo; echo "==> $*"; }
fail() { echo; echo "❌ $*" >&2; exit 1; }
ask() { local reply; read -r -p "$1" reply < /dev/tty; printf '%s' "$reply"; }

[[ $EUID -eq 0 ]] || fail "این اسکریپت را با root اجرا کنید:  sudo bash deploy.sh"

step "۱) نصب پیش‌نیازهای سیستم"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git ca-certificates curl sudo openssl >/dev/null
if ! command -v mysqldump >/dev/null 2>&1; then
  apt-get install -y -qq mysql-client >/dev/null || echo "⚠️ mysqldump نصب نشد؛ پشتیبان‌گیری ممکن نیست."
fi
# ffmpeg (ffprobe is in the same package) lives in Ubuntu's "universe" section.
# Errors are shown, not hidden; a missing ffmpeg stops the script further below.
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  if ! apt-get install -y ffmpeg; then
    echo "⚠️ نصب ffmpeg ناموفق بود؛ بخش universe اوبونتو فعال می‌شود و دوباره امتحان می‌شود."
    apt-get install -y software-properties-common
    add-apt-repository -y universe
    apt-get update -qq
    apt-get install -y ffmpeg || true
  fi
fi
echo "✅ انجام شد"

step "۲) کاربر لینوکسی balebot"
if id -u balebot >/dev/null 2>&1; then
  echo "✅ از قبل وجود دارد"
else
  useradd --system --home-dir "$DATA_DIR" --no-create-home --shell /usr/sbin/nologin balebot
  echo "✅ ساخته شد"
fi
install -d -o balebot -g balebot -m 750 "$DATA_DIR" "$DATA_DIR/media"
install -d -o balebot -g balebot -m 700 "$ENV_DIR"
install -d -m 755 "$BASE"

if [[ -n "$INSTALLED_BRANCH" && "$INSTALLED_BRANCH" != "$BRANCH" ]]; then
  echo "↪ تغییر شاخه: $INSTALLED_BRANCH → $BRANCH"
fi
step "۳) آوردن کد از شاخه‌ی $BRANCH"
if [[ -d "$SRC/.git" ]]; then
  git -C "$SRC" fetch -q --depth 1 origin "$BRANCH"
  git -C "$SRC" checkout -q -B "$BRANCH" FETCH_HEAD
  git -C "$SRC" reset -q --hard FETCH_HEAD
elif [[ -e "$SRC" ]]; then
  fail "پوشه‌ی $SRC هست ولی مخزن git نیست. آن را جابه‌جا کنید و دوباره اجرا کنید."
else
  git clone -q --depth 1 --branch "$BRANCH" "$REPO_URL" "$SRC"
fi
[[ -f "$APP_DIR/requirements.txt" ]] || fail "پوشه‌ی bale-archive-bot در کد پیدا نشد."
echo "✅ نسخه: $(git -C "$SRC" log -1 --oneline)"

# This script runs from a copy made BEFORE the code above was updated. If the
# update brought a newer deploy.sh, start over with it once — otherwise new
# steps (like installing ffmpeg) would only run on the next deploy.
if [[ -z "${BALEBOT_DEPLOY_RELOADED:-}" ]] && ! cmp -s "$0" "$APP_DIR/scripts/deploy.sh"; then
  echo "↻ deploy.sh تازه شد؛ از اول با نسخه‌ی جدید اجرا می‌شود."
  fresh="$(mktemp /tmp/balebot-deploy.XXXXXX.sh)"
  cp "$APP_DIR/scripts/deploy.sh" "$fresh"
  BALEBOT_DEPLOY_COPY=1 BALEBOT_DEPLOY_RELOADED=1 exec bash "$fresh" --branch "$BRANCH"
fi

step "۴) محیط پایتون و بسته‌ها (از آینه‌ی $MIRROR_HOST)"
[[ -x "$VENV/bin/python" ]] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --disable-pip-version-check \
  --index-url "$MIRROR" --trusted-host "$MIRROR_HOST" -r "$APP_DIR/requirements.txt" \
  || fail "نصب بسته‌ها از آینه‌ی $MIRROR_HOST ناموفق بود. اینترنت سرور را بررسی کنید و دوباره اجرا کنید."
echo "✅ بسته‌ها نصب شدند"

step "۵) فایل تنظیمات $ENV_FILE"
if [[ -f "$ENV_FILE" ]]; then
  echo "✅ از قبل وجود دارد؛ دست نخورد."
else
  token="$(ask 'توکن ربات بله: ')"
  [[ -n "$token" ]] || fail "توکن خالی است."
  read -r -s -p "رمز کاربر دیتابیس balebot (روی صفحه دیده نمی‌شود): " dbpass < /dev/tty
  echo
  [[ -n "$dbpass" ]] || fail "رمز خالی است."
  admin_id="$(ask 'شناسه‌ی عددی ادمین در بله: ')"
  [[ "$admin_id" =~ ^[0-9]+$ ]] || fail "شناسه‌ی ادمین باید فقط عدد باشد."
  encoded="$(printf '%s' "$dbpass" | python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.stdin.read(), safe=""))')"
  unset dbpass
  # Prefer the local socket (account 'balebot'@'localhost'); fall back to TCP.
  socket=/var/run/mysqld/mysqld.sock
  if sudo -u balebot test -w "$socket"; then
    db_url="mysql+aiomysql://balebot:${encoded}@localhost/Bale_Archive?charset=utf8mb4&unix_socket=$socket"
  else
    db_url="mysql+aiomysql://balebot:${encoded}@127.0.0.1:3306/Bale_Archive?charset=utf8mb4"
  fi
  tmp="$(mktemp)"
  chmod 600 "$tmp"
  cat > "$tmp" <<EOF
# تنظیمات ربات آرشیو — فقط کاربر balebot می‌تواند این فایل را بخواند (600).
BALE_BOT_TOKEN="$token"
DATABASE_URL="$db_url"
ADMIN_USER_IDS=$admin_id
# شناسه‌ی عددی گروه آرشیو (پشتیبان داخل بله)؛ اگر ندارید خالی بماند.
ARCHIVE_CHAT_ID=
RUN_MODE=polling
DATA_DIR=$DATA_DIR
HTTP_HOST=127.0.0.1
HTTP_PORT=8000
TZ=Asia/Tehran
EOF
  install -o balebot -g balebot -m 600 "$tmp" "$ENV_FILE"
  rm -f "$tmp"
  echo "✅ ساخته شد"
fi
# Secret for signed file links: created once, appended; other lines untouched.
if ! grep -q '^MEDIA_LINK_SECRET=.\+' "$ENV_FILE"; then
  [[ -z "$(tail -c1 "$ENV_FILE")" ]] || echo >> "$ENV_FILE"
  echo "MEDIA_LINK_SECRET=$(openssl rand -hex 32)" >> "$ENV_FILE"
  echo "✅ MEDIA_LINK_SECRET ساخته و به انتهای فایل اضافه شد."
fi
chown balebot:balebot "$ENV_FILE"
chmod 600 "$ENV_FILE"

step "۶) پشتیبان از دیتابیس Bale_Archive"
if ! bash "$APP_DIR/scripts/backup.sh"; then
  answer="$(ask 'پشتیبان گرفته نشد. بدون پشتیبان ادامه بدهم؟ (y/n): ')"
  [[ "$answer" == "y" ]] || fail "متوقف شد. اول مشکل پشتیبان را حل کنید."
fi

step "۷) بررسی دیتابیس (preflight، فقط خواندن)"
if ! (cd "$APP_DIR" && sudo -u balebot env BALEBOT_ENV_FILE="$ENV_FILE" PYTHONUTF8=1 TZ=Asia/Tehran \
      "$VENV/bin/python" scripts/preflight.py); then
  echo
  echo "❌ دیتابیس هنوز آماده نیست. دستورهای بالا را این‌طور اجرا کنید:"
  echo "     sudo mysql Bale_Archive"
  echo "   (دستورها را آنجا بچسبانید، بعد exit)"
  echo "   سپس دوباره همین اسکریپت را بزنید:  sudo bash $APP_DIR/scripts/deploy.sh"
  if systemctl is-active -q "$SERVICE" 2>/dev/null; then
    echo "   (سرویس قبلی هنوز روشن است و دست نخورد.)"
  fi
  exit 1
fi

step "۸) ffmpeg/ffprobe و پورت لینک فایل‌ها"
if [[ -z "$(command -v ffmpeg)" || -z "$(command -v ffprobe)" ]]; then
  fail "ffmpeg یا ffprobe نصب نیست (which ffmpeg / which ffprobe خالی است). خروجی apt بالا را ببینید یا دستی بزنید: sudo apt-get install -y ffmpeg"
fi
echo "✅ $(command -v ffmpeg)  $(command -v ffprobe)"
# Open the public file-link port. ufw is not switched on or off here.
if command -v ufw >/dev/null 2>&1; then
  ufw allow 8090/tcp || echo "⚠️ ufw allow 8090/tcp ناموفق بود."
fi

step "۹) سرویس systemd"
install -m 644 "$APP_DIR/deploy/balebot.service" "/etc/systemd/system/$SERVICE.service"
systemctl daemon-reload
systemctl enable -q "$SERVICE"
systemctl restart "$SERVICE"
sleep 6
systemctl --no-pager --lines=12 status "$SERVICE" || true
echo
if curl -fsS "http://127.0.0.1:8000/healthz"; then
  echo
  echo "✅ ربات روشن است. لاگ زنده:  sudo journalctl -u $SERVICE -f"
else
  echo
  echo "⚠️ صفحه‌ی سلامت هنوز جواب نداد. چند ثانیه بعد ببینید:  sudo journalctl -u $SERVICE -n 50"
fi
