#!/bin/sh
# Lightweight Prometheus-style metrics emitter for docker stats.
set -eu

INTERVAL="${STATS_INTERVAL:-30}"
TARGET_CONTAINERS="${TARGET_CONTAINERS:-fundus-img-xtract-web fundus-img-xtract-db fundus-img-xtract-cache}"
LOG_FILE="${LOG_FILE:-/logs/container-stats.log}"
LOG_MAX_BYTES="${LOG_MAX_BYTES:-52428800}" # 50MB default
LOG_MAX_FILES="${LOG_MAX_FILES:-7}"

# Trim optional surrounding quotes
TARGET_CONTAINERS="${TARGET_CONTAINERS%\"}"
TARGET_CONTAINERS="${TARGET_CONTAINERS#\"}"

touch "${LOG_FILE}"
chmod 0640 "${LOG_FILE}" || true

rotate_log() {
  size=$(stat -c%s "${LOG_FILE}" 2>/dev/null || echo 0)
  if [ "${size}" -ge "${LOG_MAX_BYTES}" ]; then
    ts=$(date -Iseconds | tr ':' '_')
    rotated="${LOG_FILE}.${ts}"
    mv "${LOG_FILE}" "${rotated}" 2>/dev/null || return
    gzip -f "${rotated}" || true
    touch "${LOG_FILE}"
    chmod 0640 "${LOG_FILE}" || true
    ls -1t "${LOG_FILE}".* 2>/dev/null | tail -n +$((LOG_MAX_FILES + 1)) | xargs -r rm -f --
  fi
}

to_bytes() {
  python3 - "$1" <<'PY'
import sys
val = sys.argv[1]
units = {
    "GiB": 2**30,
    "MiB": 2**20,
    "KiB": 2**10,
    "GB": 10**9,
    "MB": 10**6,
    "KB": 10**3,
    "kB": 10**3,
    "B": 1,
}
for suffix, mul in units.items():
    if val.endswith(suffix):
        num = float(val[:-len(suffix)] or "0")
        print(int(num * mul))
        break
else:
    print(int(float(val or "0")))
PY
}

while true; do
  rotate_log
  if [ ! -S /var/run/docker.sock ]; then
    echo "$(date -Iseconds) docker.sock not available" >> "${LOG_FILE}"
    sleep "${INTERVAL}"
    continue
  fi

  ts_rfc=$(date -Iseconds)
  ts_epoch=$(date +%s)

  set -- ${TARGET_CONTAINERS}
  if [ "$#" -eq 0 ]; then
    echo "${ts_rfc} no containers configured" >> "${LOG_FILE}"
    sleep "${INTERVAL}"
    continue
  fi

  stats_output=$(docker stats --no-stream --format "{{.Name}}|{{.MemUsage}}|{{.CPUPerc}}|{{.NetIO}}" "$@" 2>&1) || {
    echo "${ts_rfc} docker stats error: ${stats_output}" >> "${LOG_FILE}"
    sleep "${INTERVAL}"
    continue
  }

  echo "# ${ts_rfc}" >> "${LOG_FILE}"
  echo "${stats_output}" | while IFS="|" read -r name mem cpu net; do
    [ -z "${name}" ] && continue
    case "${name}" in
      \#*) continue ;;
    esac
    [ -z "${mem}" ] && continue
    mem_cur=${mem%%/*}; mem_cur=${mem_cur% }; mem_cur=${mem_cur% }
    mem_lim=${mem#*/ }; mem_lim=${mem_lim# }
    cpu_perc=${cpu%%%}
    net_in=${net%%/*}; net_in=${net_in% }; net_out=${net#*/ }; net_out=${net_out# }

    mem_cur_bytes=$(to_bytes "${mem_cur}")
    mem_lim_bytes=$(to_bytes "${mem_lim}")
    net_in_bytes=$(to_bytes "${net_in}")
    net_out_bytes=$(to_bytes "${net_out}")

    echo "container_memory_usage_bytes{container=\"${name}\"} ${mem_cur_bytes} ${ts_epoch}"
    echo "container_memory_limit_bytes{container=\"${name}\"} ${mem_lim_bytes} ${ts_epoch}"
    echo "container_cpu_usage_percent{container=\"${name}\"} ${cpu_perc} ${ts_epoch}"
    echo "container_network_receive_bytes{container=\"${name}\"} ${net_in_bytes} ${ts_epoch}"
    echo "container_network_transmit_bytes{container=\"${name}\"} ${net_out_bytes} ${ts_epoch}"
  done >> "${LOG_FILE}"

  echo "" >> "${LOG_FILE}"
  sleep "${INTERVAL}"
done
