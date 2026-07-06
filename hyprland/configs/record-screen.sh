#!/usr/bin/env bash
set -u

PID_FILE="${XDG_RUNTIME_DIR:-/tmp}/hypr-screen-recording.pid"
OUTPUT_DIR="$HOME/Videos/Screencasts"

notify() {
  notify-send "$1"
}

if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
    kill -INT "$pid" 2>/dev/null || true
    rm -f "$PID_FILE"
    notify "Grabación terminada"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

if ! command -v wf-recorder >/dev/null 2>&1; then
  notify "Instala wf-recorder para grabar pantalla"
  exit 1
fi

if ! command -v slurp >/dev/null 2>&1; then
  notify "Instala slurp para seleccionar área"
  exit 1
fi

if ! command -v rofi >/dev/null 2>&1; then
  notify "Instala rofi para elegir el modo de grabación"
  exit 1
fi

choice="$(printf 'Área\nPantalla completa\nCancelar\n' | rofi -dmenu -p 'Grabar')"

case "$choice" in
  "Área")
    geometry="$(slurp 2>/dev/null || true)"
    [[ -n "$geometry" ]] || exit 0
    args=(-g "$geometry")
    ;;
  "Pantalla completa")
    args=()
    ;;
  *)
    exit 0
    ;;
esac

mkdir -p "$OUTPUT_DIR"
output="$OUTPUT_DIR/recording-$(date +%Y%m%d-%H%M%S).mp4"

for seconds in 3 2 1; do
  notify "Grabación inicia en $seconds"
  sleep 1
done

wf-recorder "${args[@]}" -f "$output" >/tmp/hypr-screen-recording.log 2>&1 &
pid=$!
echo "$pid" > "$PID_FILE"

notify "Grabación iniciada"
