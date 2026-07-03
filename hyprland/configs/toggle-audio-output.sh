#!/usr/bin/env bash
set -euo pipefail

# Toggle the default audio output between connected sinks.
# Kept inside ~/.config/hypr so it can be migrated with the Hyprland config.

PREFERRED_HEADPHONES="alsa_output.usb-C-Media_Electronics_Inc._HV-2008U-00.analog-stereo"
DEFAULT_VOLUME="80%"

notify() {
  if command -v notify-send >/dev/null 2>&1; then
    notify-send "Audio" "$1"
  fi
}

if ! command -v pactl >/dev/null 2>&1; then
  notify "pactl no está disponible"
  exit 1
fi

current_sink="$(pactl get-default-sink 2>/dev/null || true)"
mapfile -t sinks < <(pactl list short sinks | awk '{print $2}')

if ((${#sinks[@]} == 0)); then
  notify "No hay salidas de audio disponibles"
  exit 1
fi

sink_exists() {
  local target="$1"
  local sink
  for sink in "${sinks[@]}"; do
    [[ "$sink" == "$target" ]] && return 0
  done
  return 1
}

next_sink=""

# If headphones are connected and they are not already active, prefer them.
if [[ "$current_sink" != "$PREFERRED_HEADPHONES" ]] && sink_exists "$PREFERRED_HEADPHONES"; then
  next_sink="$PREFERRED_HEADPHONES"
else
  # Otherwise rotate to the next connected sink.
  for sink in "${sinks[@]}"; do
    if [[ "$sink" != "$current_sink" ]]; then
      next_sink="$sink"
      break
    fi
  done
fi

if [[ -z "$next_sink" ]]; then
  notify "Solo hay una salida conectada"
  exit 0
fi

pactl set-default-sink "$next_sink"
pactl set-sink-mute "$next_sink" 0
pactl set-sink-volume "$next_sink" "$DEFAULT_VOLUME"

while read -r input _; do
  [[ -n "${input:-}" ]] || continue
  pactl move-sink-input "$input" "$next_sink" 2>/dev/null || true
  pactl set-sink-input-mute "$input" 0 2>/dev/null || true
done < <(pactl list short sink-inputs)

case "$next_sink" in
  *HV-2008U*) label="Auriculares HV-2008U" ;;
  *hdmi*) label="HDMI" ;;
  *) label="$next_sink" ;;
esac

notify "Salida cambiada a: $label"
