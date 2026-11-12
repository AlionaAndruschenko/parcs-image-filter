#!/bin/bash
# Видалити всі VM і правила фаєрволу після здачі (щоб не списувались гроші).
WORKERS="${WORKERS:-4}"
NAMES=$(for i in $(seq 1 "$WORKERS"); do printf 'worker-%d ' "$i"; done)
gcloud compute instances delete master $NAMES --quiet
gcloud compute firewall-rules delete parcs-ui parcs-internal --quiet
