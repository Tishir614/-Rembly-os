#!/usr/bin/env bash
# Rembly installer visual layer only. No flashing/storage logic lives here.

UI_STEP=0
LOGO="$ROOT/assets/logo-mark.png"

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  R=$'\033[1;31m'; P=$'\033[38;5;213m'; M=$'\033[38;5;141m'; C=$'\033[38;5;81m'
  G=$'\033[38;5;84m'; Y=$'\033[38;5;221m'; W=$'\033[1;97m'; D=$'\033[38;5;245m'
  B=$'\033[38;5;111m'; N=$'\033[0m'
else
  R= P= M= C= G= Y= W= D= B= N=
fi

ui_ascii_logo() {
  printf '%s\n' "${M}                    ╱╲        ╱╲${N}"
  printf '%s\n' "${M}                   ╱  ╲______╱  ╲${N}"
  printf '%s\n' "${P}                  ╱              ╲${N}"
  printf '%s\n' "${P}                 │     ◇    ◇     │${N}"
  printf '%s\n' "${W}                 │        ▽       │${N}"
  printf '%s\n' "${M}                  ╲    ╲____╱    ╱${N}"
  printf '%s\n' "${M}                   ╲___________╱${N}"
}

ui_logo() {
  [[ -t 1 && -f "$LOGO" ]] || { ui_ascii_logo; return; }
  if [[ -n "${WEZTERM_PANE:-}" ]] && command -v wezterm >/dev/null 2>&1; then
    wezterm imgcat --width 20 "$LOGO" 2>/dev/null && return 0
  fi
  if [[ "${TERM:-}" == *kitty* || -n "${KITTY_WINDOW_ID:-}" ]] && command -v kitty >/dev/null 2>&1; then
    kitty +kitten icat --align=center --transfer-mode=stream "$LOGO" 2>/dev/null && return 0
  fi
  if command -v chafa >/dev/null 2>&1; then
    chafa --size 24x10 --align center "$LOGO" 2>/dev/null && return 0
  fi
  ui_ascii_logo
}

ui_rule() {
  printf '%s%s%s\n' "$M" "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" "$N"
}

banner() {
  ui_logo
  printf '\n%s%*s%s\n' "$W" 43 'REMBLY OS' "$N"
  printf '%s%*s%s\n' "$C" 56 'DIRECT SMART FASTBOOT INSTALLER' "$N"
  printf '%s%*s%s\n' "$D" 55 'K37MV1_BSP  •  MT6737M  •  USB' "$N"
  printf '\n'; ui_rule
  printf '%s  ◆  АВТОМАТИЧЕСКАЯ УСТАНОВКА%s\n' "$P" "$N"
  printf '%s  Без временной загрузки: сборка, сравнение и прямая прошивка через Fastboot.%s\n' "$D" "$N"
  printf '%s  Совпадающие userdata/boot повторно не записываются.%s\n' "$D" "$N"
  ui_rule
  printf '\n%s╭─ БЕЗОПАСНАЯ ЗОНА ────────────────────────────────────────────────╮%s\n' "$B" "$N"
  printf '%s│%s  %sМогут записываться:%s userdata + boot                              %s│%s\n' "$B" "$N" "$W" "$N" "$B" "$N"
  printf '%s│%s  %sНе трогаются:%s preloader, lk, gpt, nvram, nvdata, system, vendor   %s│%s\n' "$B" "$N" "$G" "$N" "$B" "$N"
  printf '%s│%s  %sBoot:%s всегда записывается последним, только если изменился          %s│%s\n' "$B" "$N" "$G" "$N" "$B" "$N"
  printf '%s╰────────────────────────────────────────────────────────────────────╯%s\n' "$B" "$N"
}

step() {
  UI_STEP=$((UI_STEP + 1))
  printf '\n%s╭─[%02d]─%s %s%s%s\n' "$M" "$UI_STEP" "$N" "$W" "$*" "$N"
  printf '%s│%s\n' "$M" "$N"
}

ok() { printf '%s│%s  %s●%s %s\n' "$M" "$N" "$G" "$N" "$*"; }
warn() { printf '%s│%s  %s▲%s %s\n' "$M" "$N" "$Y" "$N" "$*"; }
sub() { printf '%s│%s    %s↳ %s%s\n' "$M" "$N" "$D" "$*" "$N"; }

die() {
  printf '\n%s╭─ ОШИБКА ─────────────────────────────────────────────────────────╮%s\n' "$R" "$N" >&2
  printf '%s│%s  %s✕ %s%s\n' "$R" "$N" "$R" "$*" "$N" >&2
  printf '%s╰────────────────────────────────────────────────────────────────────╯%s\n' "$R" "$N" >&2
  exit 1
}

rembly_ui_start() {
  if [[ -t 1 && "${TERM:-}" != dumb && "${REMBLY_NO_CLEAR:-0}" != 1 ]]; then
    command -v clear >/dev/null 2>&1 && clear || true
  fi
  printf '\033]0;Rembly OS • Direct Smart Installer\007' 2>/dev/null || true
  banner
}
