#!/bin/bash
# Розгортання PARCS-Python у Google Cloud: 1 master + 4 workers.
# Запускати з Google Cloud Shell (там уже є gcloud) з кореня репозиторію:
#   PROJECT_ID=my-parcs-project MY_IP=1.2.3.4 bash cloud/setup_gcp.sh
# MY_IP - IP твого комп'ютера (відкрий https://ifconfig.me у браузері), щоб відкрити веб-інтерфейс PARCS.
set -e

PROJECT_ID="${PROJECT_ID:?Вкажи PROJECT_ID}"
ZONE="${ZONE:-europe-central2-a}"          # Варшава, найближче до Києва
MACHINE="${MACHINE:-n1-standard-1}"        # 1 vCPU на вузол; 5 вузлів = 5 vCPU (влазить у квоту trial)
WORKERS="${WORKERS:-4}"
SHELL_IP=$(curl -s https://ifconfig.me)    # IP самого Cloud Shell (для run_benchmark.py)
SOURCES="${SHELL_IP}/32"
[ -n "$MY_IP" ] && SOURCES="${SOURCES},${MY_IP}/32"

gcloud config set project "$PROJECT_ID"
gcloud config set compute/zone "$ZONE"
gcloud services enable compute.googleapis.com

# Фаєрвол: веб-інтерфейс 8080 - тільки з наших IP (PARCS не має паролю і виконує будь-який код!);
# внутрішній трафік між вузлами (Pyro4 використовує випадкові порти) - дозволено.
gcloud compute firewall-rules create parcs-ui --network=default --direction=INGRESS \
  --action=ALLOW --rules=tcp:8080 --source-ranges="$SOURCES" --target-tags=parcs || true
gcloud compute firewall-rules create parcs-internal --network=default --direction=INGRESS \
  --action=ALLOW --rules=all --source-ranges=10.128.0.0/9 --target-tags=parcs || true

COMMON="--machine-type=$MACHINE --image-family=debian-12 --image-project=debian-cloud --tags=parcs \
  --metadata-from-file=startup-script=cloud/startup.sh"

# master
gcloud compute instances create master $COMMON --metadata=parcs-role=master
MASTER_IP=$(gcloud compute instances describe master --format='get(networkInterfaces[0].networkIP)')
MASTER_EXT=$(gcloud compute instances describe master --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

# workers
NAMES=$(for i in $(seq 1 "$WORKERS"); do printf 'worker-%d ' "$i"; done)
gcloud compute instances create $NAMES $COMMON --metadata=parcs-role=worker,parcs-master-ip="$MASTER_IP"

gcloud compute instances list
echo
echo "Master internal IP: $MASTER_IP"
echo "Веб-інтерфейс PARCS (через 3-5 хв, поки VM встановлять Python 2.7): http://$MASTER_EXT:8080"
echo "Перевірка воркерів:  curl http://$MASTER_EXT:8080/api/worker"
