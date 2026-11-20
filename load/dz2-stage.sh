#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mode=${1:?Укажите mixed или heavy}
rate=${2:?Укажите частоту}
duration=${3:-30}
vus=${VUS:-$((rate > 20 ? rate : 20))}
run=${RUN:-$(date +%Y%m%d-%H%M%S-%N)}
out="${OUT_ROOT:-results/dz2}/$run-$mode-$rate"
[[ "$mode" == mixed || "$mode" == heavy ]] || exit 2
if [[ "$mode" == mixed && ${PROFILE:-0} == 1 ]]; then echo 'Профиль снимайте в режиме heavy' >&2; exit 2; fi
mkdir -p "$(dirname "$out")"
mkdir "$out"
app=$(docker compose ps -q api)
db=$(docker compose ps -q db)
[[ -n "$app" && -n "$db" ]] || { echo 'Сначала запустите api и db'; exit 2; }
image=${K6_IMAGE:-grafana/k6:0.55.0}
base=${BASE:-http://127.0.0.1:8082}
# Keep the reset scoped to the service named by this compose project.
docker compose exec -T api python -m scripts.data seed --size work > "$out/seed.json"
docker compose exec -T db psql -X -v ON_ERROR_STOP=1 -U denis_kuleshin -d denis_kuleshin \
  -c 'ANALYZE denis_kuleshin.users, denis_kuleshin.categories, denis_kuleshin.tickets, denis_kuleshin.comments' > "$out/analyze.txt"
git rev-parse HEAD > "$out/commit.txt"
started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
python3 -u load/dz2-monitor.py "$app" "$db" "$out" > "$out/monitor.log" 2>&1 &
monitor=$!
trap 'kill -TERM "$monitor" 2>/dev/null || true; wait "$monitor" 2>/dev/null || true' EXIT
sleep 3
printf 'k6_start_utc\t%s\n' "$(date -u +%FT%T.%3NZ)" > "$out/markers.tsv"
profile_pid=''
if [[ ${PROFILE:-0} == 1 ]]; then
  (
    set -e
    sleep 5
    printf 'pyspy_start_utc\t%s\n' "$(date -u +%FT%T.%3NZ)" >> "$out/markers.tsv"
    docker run --rm --pid="container:$app" --cap-add=SYS_PTRACE \
      -v "$(realpath "$out"):/out" denis_kuleshin-pyspy:0.4.1 \
      record --pid 1 --duration 15 --rate 99 --format speedscope --output /out/profile.json
    printf 'pyspy_end_utc\t%s\n' "$(date -u +%FT%T.%3NZ)" >> "$out/markers.tsv"
  ) > "$out/pyspy.log" 2>&1 &
  profile_pid=$!
fi
set +e
docker run --rm --network host --user "$(id -u):$(id -g)" \
  -e "MODE=$mode" -e "RATE=$rate" -e "SECONDS=$duration" -e "VUS=$vus" -e "BASE=$base" \
  -e "TEST_USER=${TEST_USER:-demo_staff}" -e "TEST_PASSWORD=${TEST_PASSWORD:-demo}" \
  -v "$(realpath load/dz2.js):/script.js:ro" -v "$(realpath "$out"):/out" \
  "$image" run --quiet --no-color /script.js 2>&1 | tee "$out/k6.log"
rc=${PIPESTATUS[0]}
set -e
printf 'k6_end_utc\t%s\n' "$(date -u +%FT%T.%3NZ)" >> "$out/markers.tsv"
if [[ -n "$profile_pid" ]]; then
  if ! wait "$profile_pid"; then echo "Профилировщик: см. $out/pyspy.log" >&2; fi
fi
docker compose logs --no-color --since "$started" api db > "$out/service.log"
printf '%s\n' "$rc" > "$out/k6-exit.txt"
printf '%s\n' "Результат: $out"
[[ $rc == 0 || $rc == 99 ]] && [[ -s "$out/row.csv" ]] || exit 2
