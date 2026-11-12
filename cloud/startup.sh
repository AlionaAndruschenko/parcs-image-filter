#!/bin/bash
# Startup-скрипт для VM у Google Cloud (Debian 12). Один скрипт для master і workers.
# Роль і IP master-а беруться з метаданих VM:
#   parcs-role=master            або   parcs-role=worker
#   parcs-master-ip=10.x.x.x     (лише для worker - внутрішній IP master-а)
# Для локального тесту можна передати аргументами:  sudo bash startup.sh worker 10.0.0.2
#
# Чому не docker-образ hummer12007/parcs-node + create-with-container (як у методичці):
#   з 31.07.2026 Google вимкнув container startup agent, create-with-container більше не працює.
# Тому ставимо Python 2.7 через conda-forge (micromamba) і запускаємо PARCS напряму.
set -e

MD="http://metadata.google.internal/computeMetadata/v1/instance/attributes"
ROLE="${1:-$(curl -sf -H 'Metadata-Flavor: Google' $MD/parcs-role || echo worker)}"
MASTER_IP="${2:-$(curl -sf -H 'Metadata-Flavor: Google' $MD/parcs-master-ip || true)}"
BASE="${PARCS_BASE:-/opt/parcs}"
LOG="$BASE/parcs.log"
mkdir -p "$BASE"
cd "$BASE"

# 1) Python 2.7 через micromamba (тільки при першому запуску)
if [ ! -x "$BASE/py27/bin/python" ]; then
  command -v bzip2 >/dev/null || (apt-get update -y && apt-get install -y bzip2 git curl)
  command -v git   >/dev/null || (apt-get update -y && apt-get install -y git)
  curl -sSL https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-linux-64.tar.bz2 \
    | tar -xj bin/micromamba
  MAMBA_ROOT_PREFIX="$BASE/mamba" ./bin/micromamba create -y -q -p "$BASE/py27" -c conda-forge python=2.7 pip
fi

# 2) PARCS-Python + перевірені версії бібліотек
if [ ! -d "$BASE/parcs-python" ]; then
  git clone -q https://github.com/Hummer12007/parcs-python "$BASE/parcs-python"
fi
# (той самий список, що й у cloud/requirements-py27.txt)
cat > "$BASE/requirements-py27.txt" <<'EOF'
Pyro4==4.82
serpent==1.28
selectors34==1.2
six==1.17.0
netifaces==0.11.0
py-cpuinfo==4.0.0
Flask==1.1.4
Werkzeug==1.0.1
Jinja2==2.11.3
MarkupSafe==1.1.1
itsdangerous==1.1.0
click==7.1.2
requests==2.27.1
urllib3==1.26.20
idna==2.10
chardet==4.0.0
certifi==2019.11.28
EOF
"$BASE/py27/bin/pip" install -q --disable-pip-version-check -r "$BASE/requirements-py27.txt"

# 3) Конфіг вузла
SELF_IP=$(hostname -I | awk '{print $1}')
if [ "$ROLE" = "master" ]; then
  printf '[Node]\nmaster=True\nport=8080\n' > "$BASE/parcs.config"
else
  printf '[Node]\nhost=%s\nip=%s\nmaster=False\n\n[Master Node]\nhost=%s\nip=%s\nport=8080\n' \
    "$SELF_IP" "$SELF_IP" "$MASTER_IP" "$MASTER_IP" > "$BASE/parcs.config"
fi

# 4) Запуск (перезапускаємо, якщо вже працює)
pkill -f "start.py -config $BASE/parcs.config" || true
cd "$BASE/parcs-python"
nohup "$BASE/py27/bin/python" start.py -config "$BASE/parcs.config" > "$LOG" 2>&1 &
echo "PARCS $ROLE started on $SELF_IP (master: ${MASTER_IP:-self}). Log: $LOG"
