#!/usr/bin/env bash
# Lain: QE Studio uninstaller, for Linux and for Windows (in Git Bash, which comes with Git for Windows).
#
# Removes what install.sh put on this computer: the lain command, the application menu entry, the
# configuration, Lain's data and cache, and the folder of the program. Every path is shown before
# anything is deleted, and nothing is deleted without a yes. The simulations are never touched, and
# this script never connects to the cluster: to go back to the password login it only renames the
# ssh key on this computer, and only if asked.
#
#   curl -fsSL https://raw.githubusercontent.com/Mariano17omega/Lain/main/uninstall.sh | bash
#   bash uninstall.sh
#   bash uninstall.sh --plain   # plain text and typed answers, also on a terminal
#
# Environment: LAIN_REPO_URL (the repository an installation comes from), LAIN_DIR (the folder to
# suggest when it cannot be found), NO_COLOR.
#
# The functions this file shares with install.sh are copies, because `curl | bash` has only one
# file: tests/test_uninstall_script.py keeps them identical.

set -euo pipefail

# The script's own file, empty when it came through a pipe (curl ... | bash). Read here, at the top:
# inside a function a piped script's BASH_SOURCE[0] is "main".
SCRIPT_PATH=${BASH_SOURCE[0]:-}

REPO_URL="${LAIN_REPO_URL:-https://github.com/Mariano17omega/Lain.git}"
RAW_URL="https://raw.githubusercontent.com/Mariano17omega/Lain/main/uninstall.sh"

# shellcheck disable=SC2088  # the tilde is meant to stay unexpanded
DEFAULT_CHECKOUT="${LAIN_DIR:-~/Lain}"
# shellcheck disable=SC2088
DEFAULT_KEY_PATH="~/.ssh/id_ed25519"
DEFAULT_PORT=22
DEFAULT_AUTH=key

STEP=0
TOTAL_STEPS=4
WINDOWS=0
HOME_DIR=$HOME
HOST="" PORT="" CLUSTER_USER="" AUTH="" KEY_PATH=""

# What was found. A *_ROWS array holds pairs for panel: what it is, where it is.
DELETE_ROWS=() KEEP_ROWS=() BACKUP_ROWS=()
TOOL_DIR="" TOOL_INSTALLED=0
CHECKOUT="" REMOVE_CHECKOUT=0 CHECKOUT_KEPT=""
MENU_FILES=() FOLDERS=() DATA_ITEMS=() BACKUPS=()
DATA_DIR="" REGISTRY=0
LOCAL_ROOTS=() ROOT_UNKNOWN=0

# What was asked and what happened.
DELETE_BACKUPS=0 RENAME_KEY=0 STARTED_INSIDE=0
LOCAL_KEY="" LOCAL_PUB="" NEW_KEY="" NEW_PUB=""
RESTORE=()   # the commands that undo the key's rename
DELETED=0
LEFT=()      # what could not be deleted

REGISTRY_KEY='HKCU\Software\qe-studio'

# The look, set by detect_ui. All empty or 0 is plain ASCII: what a run without a terminal prints.
UI_ON=0        # stdout is a terminal that takes escape sequences
UI_GLYPHS=0    # and it is UTF-8: check marks, boxes, the portrait
UI_MENUS=0     # and the answers come from a terminal too: arrow-key menus
CURSOR_HIDDEN=0
C_RESET="" C_BOLD="" C_DIM="" C_CYAN="" C_TEAL="" C_GREEN="" C_YELLOW="" C_BADGE=""
E_RESET="" E_YELLOW="" E_RED="" E_WARN="" E_ERROR=""   # the same for stderr, which may be a file
G_OK="  " G_ASK="" G_SECTION="" G_ON="" G_OFF=""

# Documentation/ does not reach the public repository and `curl | bash` has only this file, so the
# portrait lives here. A string, not a heredoc: no temp file is needed to show it.
PORTRAIT='⠀⠀⠀⠀⠀⢀⣠⣤⣶⣶⣿⣿⣿⣶⣶⣤⡀⠀⠀⠀⠀
⠀⠀⠀⠀⣴⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣦⡀⠀⠀
⠀⠀⠀⣼⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣧⠀⠀
⠀⠀⢠⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡄⠀
⠀⠀⢸⣿⣿⣿⣿⣿⡏⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⠀
⠀⠀⠘⣿⣿⣟⡿⢿⣷⢸⠞⠛⢽⣾⣛⡟⣿⣿⣿⠁⠀
⠀⠀⠀⠻⣿⡟⢶⡿⡿⠀⠀⠀⠀⠹⠯⠏⢸⣿⣿⠀⠀
⠀⠀⠀⠀⠛⣾⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣼⣿⡏⠀⠀
⠀⠀⠀⠀⠀⣿⣿⣄⠀⠀⠈⠍⠀⠀⢀⣼⣿⣿⡇⠀⠀
⠀⠀⠀⠀⠀⠈⠀⠘⢉⠖⠠⠤⠤⠀⠈⡌⣿⡏⠀⠀⠀
⠀⠀⠀⠀⠀⢀⡠⠔⠊⠀⠀⠀⠀⠀⠀⠈⣿⡀⠀⠀⠀
⠀⡠⠂⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⠈⠁⠂⢄
⢰⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⣆⠀⠀⠈'

# --- output -------------------------------------------------------------------------------------

say() { printf '%s\n' "$*"; }
info() { printf '  %s\n' "$*"; }
ok() { printf '%s%s%s%s\n' "$C_GREEN" "$G_OK" "$C_RESET" "$*"; }
retry() { printf '  %s%s%s\n' "$C_YELLOW" "$*" "$C_RESET"; }
warn() { printf '%s%sWarning: %s%s\n' "$E_YELLOW" "$E_WARN" "$*" "$E_RESET" >&2; }
die() {
    printf '%s%sError: %s%s\n' "$E_RED" "$E_ERROR" "$*" "$E_RESET" >&2
    exit 1
}

step() {
    STEP=$((STEP + 1))
    printf '\n%s[%d/%d]%s %s%s%s\n' "$C_CYAN" "$STEP" "$TOTAL_STEPS" "$C_RESET" "$C_BOLD" "$*" "$C_RESET"
}

section() {
    printf '\n%s%s%s%s%s\n' "$C_TEAL" "$G_SECTION" "$C_BOLD" "$*" "$C_RESET"
}

# detect_ui: turns on what this terminal can show. Called once fd 3 is open. Escape sequences are
# written directly: tput is not on every Git Bash.
detect_ui() {
    if ((PLAIN)) || [[ ! -t 1 || ${TERM:-dumb} == dumb ]]; then
        return 0
    fi
    UI_ON=1
    G_ON=">" G_OFF=" "
    if [[ -t 3 ]]; then
        UI_MENUS=1
    fi
    case ${LC_ALL:-${LC_CTYPE:-${LANG:-}}} in
        *[Uu][Tt][Ff]-8* | *[Uu][Tt][Ff]8*)
            UI_GLYPHS=1
            G_OK="  ✔ " G_ASK="  ◇ " G_SECTION="  ─ " G_ON="●" G_OFF="○"
            if [[ -t 2 ]]; then
                E_WARN="  ▲ " E_ERROR="  ✖ "
            fi
            ;;
    esac
    if [[ -n ${NO_COLOR:-} ]]; then
        return 0
    fi
    C_RESET=$'\033[0m' C_BOLD=$'\033[1m'
    local red
    if [[ ${TERM:-} == *256color* || -n ${COLORTERM:-} ]]; then
        C_DIM=$'\033[38;5;242m' C_CYAN=$'\033[38;5;51m' C_TEAL=$'\033[38;5;37m'
        C_GREEN=$'\033[38;5;82m' C_YELLOW=$'\033[38;5;220m' red=$'\033[38;5;196m'
        C_BADGE=$'\033[48;5;37m\033[38;5;232m\033[1m'
    else
        C_DIM=$'\033[90m' C_CYAN=$'\033[36m' C_TEAL=$'\033[36m'
        C_GREEN=$'\033[32m' C_YELLOW=$'\033[33m' red=$'\033[31m'
        C_BADGE=$'\033[46m\033[30m\033[1m'
    fi
    if [[ -t 2 ]]; then
        E_RESET=$C_RESET E_YELLOW=$C_YELLOW E_RED=$red
    fi
}

hide_cursor() {
    printf '\033[?25l'
    CURSOR_HIDDEN=1
}

show_cursor() {
    if ((CURSOR_HIDDEN)); then
        printf '\033[?25h'
        CURSOR_HIDDEN=0
    fi
}

# term_cols: the terminal's width, 80 when it does not say.
term_cols() {
    local size cols
    size=$(stty size <&3 2>/dev/null || true)
    cols=${size##* }
    if [[ $cols =~ ^[0-9]+$ ]] && ((cols > 0)); then
        printf '%s' "$cols"
    else
        printf '80'
    fi
}

# repeat TEXT N: TEXT, N times.
repeat() {
    local line
    printf -v line '%*s' "$2" ''
    printf '%s' "${line// /$1}"
}

# panel TITLE KEY VALUE [KEY VALUE]...: the rows in a box. A box that would not fit the terminal
# loses its right side, so that a long path is neither cut nor breaks the frame. Without glyphs,
# only the rows.
panel() {
    local title=$1 key_width=0 value_width=0 i
    shift
    local rows=("$@")
    for ((i = 0; i < ${#rows[@]}; i += 2)); do
        if ((${#rows[i]} > key_width)); then key_width=${#rows[i]}; fi
        if ((${#rows[i + 1]} > value_width)); then value_width=${#rows[i + 1]}; fi
    done
    if ((!UI_GLYPHS)); then
        for ((i = 0; i < ${#rows[@]}; i += 2)); do
            printf '  %-*s  %s\n' "$key_width" "${rows[i]}" "${rows[i + 1]}"
        done
        return 0
    fi

    local inner=$((key_width + 2 + value_width)) right=1 pad
    if ((inner < ${#title} + 2)); then inner=$((${#title} + 2)); fi
    if ((inner + 8 > $(term_cols))); then right=0; fi

    if ((right)); then
        printf '  %s╭─ %s%s%s%s %s╮%s\n' "$C_DIM" "$C_RESET" "$C_BOLD" "$title" "$C_DIM" \
            "$(repeat ─ $((inner + 1 - ${#title})))" "$C_RESET"
    else
        printf '  %s╭─ %s%s%s%s\n' "$C_DIM" "$C_RESET" "$C_BOLD" "$title" "$C_RESET"
    fi
    for ((i = 0; i < ${#rows[@]}; i += 2)); do
        printf '  %s│%s  %s%-*s%s  %s%s%s' "$C_DIM" "$C_RESET" "$C_DIM" "$key_width" "${rows[i]}" \
            "$C_RESET" "$C_TEAL" "${rows[i + 1]}" "$C_RESET"
        if ((right)); then
            pad=$((inner - key_width - 2 - ${#rows[i + 1]} + 2))
            printf '%*s%s│%s' "$pad" '' "$C_DIM" "$C_RESET"
        fi
        printf '\n'
    done
    if ((right)); then
        printf '  %s╰%s╯%s\n' "$C_DIM" "$(repeat ─ $((inner + 4)))" "$C_RESET"
    else
        printf '  %s╰─%s\n' "$C_DIM" "$C_RESET"
    fi
}

banner() {
    local platform=Linux version="" here cols
    if ((WINDOWS)); then
        platform="Windows, Git Bash"
    fi
    if ((!UI_ON)); then
        say "Lain: QE Studio uninstaller ($platform)"
        return 0
    fi
    here=$(script_checkout)
    if [[ -n $here ]]; then
        version=$(project_version "$here")
        if [[ -n $version ]]; then version="v$version  "; fi
    fi
    cols=$(term_cols)
    ((cols <= 63)) || cols=63
    say ""
    if ((UI_GLYPHS)); then
        printf '%s%s%s%s\n\n' "$C_CYAN" "$C_BOLD" "$PORTRAIT" "$C_RESET"
        printf '%s%s%s\n' "$C_DIM" "$(repeat ─ $((cols - 2)))" "$C_RESET"
    fi
    printf ' %s Lain: QE Studio %s %s%suninstaller (%s)%s\n' \
        "$C_BADGE" "$C_RESET" "$C_DIM" "$version" "$platform" "$C_RESET"
    if ((UI_GLYPHS)); then
        printf '%s%s%s\n' "$C_DIM" "$(repeat ─ $((cols - 2)))" "$C_RESET"
    fi
}

# titled_panel TITLE ROW...: panel, whose title shows only in a box; plain text gets it as a line.
titled_panel() {
    if ((UI_GLYPHS)); then
        say ""
    else
        section "$1:"
    fi
    panel "$@"
}

usage() {
    cat <<EOF
Lain: QE Studio uninstaller (Linux, and Windows in Git Bash).

Usage:
  curl -fsSL $RAW_URL | bash
  bash uninstall.sh          list what would be deleted, ask, then delete it
  bash uninstall.sh --plain  plain text and typed answers, also on a terminal
  bash uninstall.sh --help

Your simulations (paths.local_root) are never touched.

Environment:
  LAIN_REPO_URL  repository an installation comes from (default: $REPO_URL)
  LAIN_DIR       folder to suggest when Lain cannot be found (default: ~/Lain)
  NO_COLOR       when set, no colors
EOF
}

# --- input --------------------------------------------------------------------------------------

# Answers are read from fd 3. When the script itself came through a pipe (curl ... | bash), stdin is
# the rest of the script, so the questions go to the terminal; otherwise to stdin.
setup_input() {
    if [[ -n $SCRIPT_PATH ]]; then
        exec 3<&0
    elif (exec 3</dev/tty) 2>/dev/null; then
        exec 3</dev/tty
    else
        die "there is no terminal to ask the questions on. Download the script and run it:
  curl -fsSL $RAW_URL -o uninstall.sh && bash uninstall.sh"
    fi
}

# read_answer VAR: one line from fd 3, without the CR a Windows terminal may add and without the
# blanks around it. Dies when the input ends, so a question is never asked forever.
read_answer() {
    local __line
    if ! IFS= read -r -u 3 __line && [[ -z $__line ]]; then  # a last line without a newline counts
        printf '\n'
        die "the input ended before every question was answered."
    fi
    __line=${__line%$'\r'}
    __line="${__line#"${__line%%[![:space:]]*}"}"
    __line="${__line%"${__line##*[![:space:]]}"}"
    printf -v "$1" '%s' "$__line"
}

# prompt_start "Question": the question, without a line end.
prompt_start() {
    printf '%s%s%s%s%s%s' "$C_GREEN" "$G_ASK" "$C_RESET" "$C_BOLD" "$1" "$C_RESET"
}

# select_menu VAR "Question" DEFAULT OPTION...: VAR becomes the index of the option picked with the
# arrows and Enter, or with its first letter; DEFAULT is the index it starts on. Reads single keys
# from fd 3, so only when UI_MENUS is on. Only the option lines are redrawn: a long question may
# take more lines than it seems, and is written once.
select_menu() {
    local __var=$1 __question=$2 __selected=$3 __key __rest __first __i __count __done=0
    shift 3
    local __options=("$@")
    __count=${#__options[@]}
    prompt_start "${__question#"${__question%%[![:space:]]*}"}"
    printf '\n'
    hide_cursor
    while true; do
        for ((__i = 0; __i < __count; __i++)); do
            if ((__i == __selected)); then
                printf '    %s%s%s %s%s%s\n' "$C_GREEN" "$G_ON" "$C_RESET" "$C_BOLD" "${__options[__i]}" "$C_RESET"
            else
                printf '    %s%s %s%s\n' "$C_DIM" "$G_OFF" "${__options[__i]}" "$C_RESET"
            fi
        done
        if ! IFS= read -rsn1 -u 3 __key; then
            show_cursor
            die "the input ended before every question was answered."
        fi
        case $__key in
            '' | $'\r' | $'\n') __done=1 ;;
            $'\033')
                __rest=""
                IFS= read -rsn2 -t 0.1 -u 3 __rest || true
                case $__rest in
                    '[A' | OA) if ((__selected > 0)); then __selected=$((__selected - 1)); fi ;;
                    '[B' | OB) if ((__selected < __count - 1)); then __selected=$((__selected + 1)); fi ;;
                esac
                ;;
            *)
                for ((__i = 0; __i < __count; __i++)); do
                    __first=${__options[__i]:0:1}
                    if [[ ${__key,,} == "${__first,,}" ]]; then
                        __selected=$__i
                        __done=1
                    fi
                done
                ;;
        esac
        printf '\033[%dA\033[J' "$__count"
        if ((__done)); then break; fi
    done
    printf '    %s%s%s %s%s%s\n' "$C_GREEN" "$G_ON" "$C_RESET" "$C_BOLD" "${__options[__selected]}" "$C_RESET"
    show_cursor
    printf -v "$__var" '%s' "$__selected"
}

# ask VAR "Question" [DEFAULT]: Enter keeps DEFAULT.
ask() {
    local __var=$1 __question=$2 __default=${3-} __answer
    prompt_start "$__question"
    if [[ -n $__default ]]; then
        printf ' [%s%s%s]: ' "$C_TEAL" "$__default" "$C_RESET"
    else
        printf ': '
    fi
    read_answer __answer
    printf -v "$__var" '%s' "${__answer:-$__default}"
}

# ask_yes_no "Question" y|n: true for yes; Enter takes the default.
ask_yes_no() {
    local question=$1 default=$2 hint answer
    if ((UI_MENUS)); then
        local start=1
        if [[ $default == y ]]; then start=0; fi
        select_menu answer "$question" "$start" Yes No
        return "$answer"
    fi
    if [[ $default == y ]]; then hint="Y/n"; else hint="y/N"; fi
    while true; do
        prompt_start "$question"
        printf ' [%s]: ' "$hint"
        read_answer answer
        answer=${answer:-$default}
        case ${answer,,} in
            y | yes) return 0 ;;
            n | no) return 1 ;;
            *) retry "Please answer y or n." ;;
        esac
    done
}

# --- platform -----------------------------------------------------------------------------------

detect_platform() {
    case "$(uname -s)" in
        MINGW* | MSYS* | CYGWIN*) WINDOWS=1 ;;
        *) WINDOWS=0 ;;
    esac
    # Lain (Python's expanduser) takes ~ from USERPROFILE on Windows, not from Git Bash's HOME.
    if ((WINDOWS)) && [[ -n ${USERPROFILE:-} ]]; then
        HOME_DIR=$(cygpath -u "$USERPROFILE")
    else
        HOME_DIR=$HOME
    fi
}

# expand_home PATH: a leading ~ made the home folder, as Lain will make it.
expand_home() {
    case $1 in
        \~) printf '%s' "$HOME_DIR" ;;
        \~/*) printf '%s/%s' "$HOME_DIR" "${1#\~/}" ;;
        *) printf '%s' "$1" ;;
    esac
}

# full_path_ok PATH: a path Lain finds from any folder. Lain expands ~ and $VARIABLES, but takes a
# relative path from the folder it runs in (only paths.data is relative to config.yaml), so these
# answers start with / or ~ (or a drive letter on Windows) and have no $ for this script to miss.
full_path_ok() {
    local drive='^[A-Za-z]:[\/]'
    [[ $1 != *'$'* ]] || return 1
    case $1 in
        /* | \~ | \~/*) return 0 ;;
    esac
    ((WINDOWS)) && [[ $1 =~ $drive ]]
}

# local_path PATH: the path this script can test and create (a Windows C:\ path becomes /c/...).
local_path() {
    local path
    path=$(expand_home "$1")
    if ((WINDOWS)) && [[ -n $path ]]; then
        cygpath -u "$path"
    else
        printf '%s' "$path"
    fi
}

# on_path DIR LIST: whether DIR is one of the folders of LIST, a PATH value.
on_path() {
    case ":$2:" in
        *":$1:"* | *":$1/:"*) return 0 ;;
        *) return 1 ;;
    esac
}

add_to_path() {
    on_path "$1" "$PATH" || export PATH="$1:$PATH"
}

has() { command -v "$1" >/dev/null 2>&1; }

# shell_quote WORD: WORD as one word of a shell command shown to the user.
shell_quote() { printf '%q' "$1"; }

# unique_name PATH: PATH, or PATH_2, PATH_3... the first one that does not exist.
unique_name() {
    local candidate=$1 n=2
    while [[ -e $candidate ]]; do
        candidate="${1}_$n"
        n=$((n + 1))
    done
    printf '%s' "$candidate"
}

# get_key FILE SECTION KEY: the value of `  KEY:` under SECTION, without its quotes or comment.
get_key() {
    SECTION=$2 KEY=$3 awk '
        { sub(/\r$/, "") }
        /^[A-Za-z_][A-Za-z0-9_]*:/ { section = $0; sub(/:.*/, "", section); next }
        section == ENVIRON["SECTION"] && index($0, "  " ENVIRON["KEY"] ":") == 1 {
            value = substr($0, length(ENVIRON["KEY"]) + 4)
            sub(/^[ \t]+/, "", value)
            if (value ~ /^"/) { value = substr(value, 2); sub(/"[ \t]*(#.*)?$/, "", value) }
            else if (value ~ /^\047/) { value = substr(value, 2); sub(/\047[ \t]*(#.*)?$/, "", value) }
            else { sub(/[ \t]+#.*$/, "", value); sub(/[ \t]+$/, "", value) }
            print value; exit
        }' "$1"
}

# Takes the cluster login of a config.yaml the user kept, for the ssh step.
read_cluster_from() {
    HOST=$(get_key "$1" cluster host)
    PORT=$(get_key "$1" cluster port)
    CLUSTER_USER=$(get_key "$1" cluster user)
    AUTH=$(get_key "$1" cluster auth)
    KEY_PATH=$(get_key "$1" cluster key_path)
    PORT=${PORT:-$DEFAULT_PORT}
    AUTH=${AUTH:-$DEFAULT_AUTH}
    if [[ -n $HOST && $AUTH == key && -z $KEY_PATH ]]; then
        KEY_PATH=$DEFAULT_KEY_PATH
        info "config.yaml has no cluster.key_path: the ssh step uses ssh's default key, $KEY_PATH."
    fi
}

is_lain_checkout() {
    [[ -f $1/pyproject.toml && -f $1/config.example.yaml ]] && grep -q '^name = "lain"' "$1/pyproject.toml"
}

# The checkout this script is in, if it runs from one.
script_checkout() {
    [[ -n $SCRIPT_PATH ]] || return 0
    local dir
    dir=$(cd "$(dirname -- "$SCRIPT_PATH")" && pwd)
    if is_lain_checkout "$dir"; then
        printf '%s' "$dir"
    fi
}

# project_version DIR: the version in DIR/pyproject.toml, empty when there is none.
project_version() {
    sed -n '/^version = "/{s/^version = "\([^"]*\)".*/\1/p;q;}' "$1/pyproject.toml" 2>/dev/null || true
}

# repo_id URL: URL without what differs between an https and an ssh address of the same repository.
repo_id() {
    local url=${1%/}
    url=${url%.git}
    url=${url#ssh://}
    url=${url#https://}
    url=${url#http://}
    url=${url#git@}
    url=${url/://}
    printf '%s' "${url,,}"
}

same_repo() { [[ $(repo_id "$1") == "$(repo_id "$2")" ]]; }

# user_config_dir, system_data_dir: where core/config.py:user_config_path and
# core/appdirs.py:default_data_dir keep Lain's files.
user_config_dir() {
    if ((WINDOWS)); then
        if [[ -n ${APPDATA:-} ]]; then
            printf '%s/qe-studio' "$(cygpath -u "$APPDATA")"
        else
            printf '%s/AppData/Roaming/qe-studio' "$HOME_DIR"
        fi
    else
        printf '%s/qe-studio' "${XDG_CONFIG_HOME:-$HOME_DIR/.config}"
    fi
}

system_data_dir() {
    if ((WINDOWS)); then
        if [[ -n ${LOCALAPPDATA:-} ]]; then
            printf '%s/qe-studio' "$(cygpath -u "$LOCALAPPDATA")"
        else
            printf '%s/AppData/Local/qe-studio' "$HOME_DIR"
        fi
    else
        printf '%s/qe-studio' "${XDG_DATA_HOME:-$HOME_DIR/.local/share}"
    fi
}

# data_folder DIR: Lain's data folder for the installation in DIR (paths.data, relative to its
# config.yaml, or the system's). Empty when paths.data has a $VARIABLE, which only Lain expands.
data_folder() {
    local config="$1/config.yaml" value="" drive='^[A-Za-z]:[\/]'
    if [[ ! -f $config ]]; then
        config="$(user_config_dir)/config.yaml"
    fi
    if [[ -f $config ]]; then
        value=$(get_key "$config" paths data)
    fi
    if [[ -z $value ]]; then
        system_data_dir
    elif [[ $value == *'$'* ]]; then
        return 0
    elif [[ $value == /* || $value == \~ || $value == \~/* ]] || { ((WINDOWS)) && [[ $value =~ $drive ]]; }; then
        local_path "$value"
    else
        printf '%s/%s' "$(dirname -- "$config")" "$value"
    fi
}

# shellcheck disable=SC2329  # run by the trap in main
cleanup() {
    show_cursor
}

# Ctrl+C or a kill: the EXIT trap (cleanup) still runs after this.
# shellcheck disable=SC2329  # run by the trap in main
interrupted() {
    show_cursor
    printf '\n%sUninstall interrupted.%s\n' "$C_YELLOW" "$C_RESET"
    exit 130
}

# real_path PATH: PATH with its links resolved, when it exists.
real_path() {
    if [[ -d $1 ]]; then
        (cd -- "$1" && pwd -P)
    else
        printf '%s' "${1%/}"
    fi
}

# is_inside PARENT PATH: whether PATH is PARENT or something in it.
is_inside() {
    case $2/ in
        "$1"/*) return 0 ;;
    esac
    return 1
}

# holds_root FOLDER: whether one of the simulation folders is FOLDER or inside it.
holds_root() {
    local root
    for root in ${LOCAL_ROOTS[@]+"${LOCAL_ROOTS[@]}"}; do
        if is_inside "$1" "$root"; then return 0; fi
    done
    return 1
}

# is_lain_data NAME: a file or folder Lain itself writes in a paths.data folder. Only these leave
# one: that folder is the user's choice and may hold anything else.
is_lain_data() {
    case $1 in
        settings.ini | settings.ini.lock | lain.log | lain.log.* | lain.crash | lain.lock | lain.lock.*) return 0 ;;
        submitted_jobs.log | roots | folders.json | grids.json | compounds.json | navigation.json) return 0 ;;
        .*.tmp) return 0 ;;
    esac
    return 1
}

only_lain_data() {
    local item
    for item in "$1"/* "$1"/.[!.]*; do
        if [[ -e $item ]] && ! is_lain_data "${item##*/}"; then return 1; fi
    done
    return 0
}

# lain_leftover DIR PATH: whether PATH, listed by git as untracked or ignored in DIR, is something
# Lain or its tools made. Anything else is the user's.
lain_leftover() {
    local dir=$1 path=$2 data
    case $path in
        config.yaml | config.yaml.bak* | .config.yaml.*) return 0 ;;
        config-backup)
            if [[ ${dir##*/} == lain-backup-* ]]; then return 0; fi
            ;;
    esac
    case ${path##*/} in
        .venv | __pycache__ | *.egg-info | .pytest_cache | .ruff_cache | .mypy_cache | .hypothesis) return 0 ;;
    esac
    data=$(data_folder "$dir")
    if [[ -n $data && -d $data && $(real_path "$data") == "$(real_path "$dir")/$path" ]] && only_lain_data "$data"; then
        return 0
    fi
    return 1
}

# keep_reason DIR: why the folder DIR must not be deleted; nothing when it can be.
keep_reason() {
    local dir=$1 output origin line foreign=() shown
    if ! is_lain_checkout "$dir"; then
        printf 'it is not a Lain folder'
        return 0
    fi
    if [[ ! -d $dir/.git ]] || ! has git; then
        printf 'without git there is no way to tell your files from the program'
        return 0
    fi
    origin=$(git -C "$dir" remote get-url origin </dev/null 2>/dev/null || true)
    if ! same_repo "$origin" "$REPO_URL"; then
        printf 'it is a clone of another repository'
        return 0
    fi
    if ((ROOT_UNKNOWN)); then
        printf 'paths.local_root is relative or has a variable, so it may be inside'
        return 0
    fi
    if holds_root "$(real_path "$dir")"; then
        printf 'your simulations (paths.local_root) are inside it'
        return 0
    fi
    if ! output=$(git -C "$dir" status --porcelain --ignored </dev/null 2>/dev/null); then
        printf 'git could not read it'
        return 0
    fi
    # --ignored too: .gitignore covers patterns such as *.log, which may be the user's own files.
    while IFS= read -r line; do
        if [[ -z $line ]]; then continue; fi
        case ${line:0:2} in
            '!!' | '??')
                local path=${line:3}
                path=${path%/}
                if ! lain_leftover "$dir" "$path"; then foreign+=("$path"); fi
                ;;
            *) foreign+=("${line:3}") ;;
        esac
    done <<<"$output"
    if ((${#foreign[@]})); then
        shown=${foreign[*]:0:5}
        printf 'it has files that are not part of the program: %s' "$shown"
        if ((${#foreign[@]} > 5)); then printf ' and %d more' $((${#foreign[@]} - 5)); fi
        return 0
    fi
    if [[ -n $(git -C "$dir" log --branches --not --remotes -1 --format=%h </dev/null 2>/dev/null || true) ]]; then
        printf 'it has local commits that exist nowhere else'
    fi
}

# --- what is installed --------------------------------------------------------------------------

# uv_tools_dir: the folder of uv's tools, which holds the environment of the lain command.
uv_tools_dir() {
    local dir=""
    if has uv; then
        dir=$(uv tool dir </dev/null 2>/dev/null || true)
    fi
    if [[ -n $dir ]]; then
        local_path "$dir"
    elif [[ -n ${UV_TOOL_DIR:-} ]]; then
        local_path "$UV_TOOL_DIR"
    elif ((WINDOWS)) && [[ -n ${APPDATA:-} ]]; then
        printf '%s/uv/tools' "$(cygpath -u "$APPDATA")"
    else
        printf '%s/uv/tools' "${XDG_DATA_HOME:-$HOME_DIR/.local/share}"
    fi
}

find_program() {
    local receipt line
    TOOL_DIR="$(uv_tools_dir)/lain"
    receipt="$TOOL_DIR/uv-receipt.toml"
    if [[ ! -f $receipt ]]; then
        info "The lain command is not installed with uv."
        return 0
    fi
    if ! has uv; then
        warn "uv was not found: the lain command stays, as only uv can remove it."
        KEEP_ROWS+=("Program" "$TOOL_DIR (uv was not found)")
        return 0
    fi
    TOOL_INSTALLED=1
    ok "Program: $TOOL_DIR"
    DELETE_ROWS+=("Program" "$TOOL_DIR")
    while IFS= read -r line; do
        if [[ -n $line ]]; then
            DELETE_ROWS+=("Command" "$(local_path "${line//\\\\/\\}")")
        fi
    done < <(sed -n "s/.*install-path = [\"']\([^\"']*\)[\"'].*/\1/p" "$receipt")
}

find_checkout() {
    local path="" answer receipt="$TOOL_DIR/uv-receipt.toml"
    if [[ -f $receipt ]]; then
        path=$(sed -n "/editable = [\"']/{s/.*editable = [\"']\([^\"']*\)[\"'].*/\1/p;q;}" "$receipt")
        if [[ -n $path ]]; then
            path=$(local_path "${path//\\\\/\\}")
        fi
    fi
    if [[ -z $path ]] || ! is_lain_checkout "$path"; then
        path=$(script_checkout)
    fi
    if [[ -z $path ]]; then
        ask answer "Folder Lain is installed in" "$DEFAULT_CHECKOUT"
        path=$(local_path "$answer")
    fi
    if is_lain_checkout "$path"; then
        CHECKOUT=$(cd -- "$path" && pwd)
        ok "Program folder: $CHECKOUT"
    else
        info "There is no Lain folder at $path."
    fi
}

# add_root VALUE: a paths.local_root read from a config.yaml. One that cannot be located (relative,
# or with a variable only Lain expands) is remembered as unknown.
add_root() {
    if [[ -z $1 ]]; then return 0; fi
    if full_path_ok "$1"; then
        LOCAL_ROOTS+=("$(real_path "$(local_path "$1")")")
        KEEP_ROWS+=("Simulations" "$1")
    else
        ROOT_UNKNOWN=1
        KEEP_ROWS+=("Simulations" "$1 (paths.local_root)")
    fi
}

read_configuration() {
    local file config=""
    for file in "${CHECKOUT:+$CHECKOUT/config.yaml}" "$(user_config_dir)/config.yaml"; do
        if [[ -z $file || ! -f $file ]]; then continue; fi
        if [[ -z $config ]]; then config=$file; fi
        add_root "$(get_key "$file" paths local_root)"
    done
    if [[ -n $config ]]; then
        read_cluster_from "$config"
    fi
}

find_menu() {
    if ((WINDOWS)); then return 0; fi
    local base=${XDG_DATA_HOME:-$HOME_DIR/.local/share} desktop icon
    desktop="$base/applications/lain.desktop"
    # Only a launcher of this program: another application could have the same file name.
    if [[ ! -f $desktop ]] || ! grep -q '^Exec=lain$' "$desktop"; then
        return 0
    fi
    MENU_FILES+=("$desktop")
    DELETE_ROWS+=("Menu entry" "$desktop")
    for icon in "$base"/icons/hicolor/*/apps/lain.png; do
        if [[ -f $icon ]]; then
            MENU_FILES+=("$icon")
            DELETE_ROWS+=("Menu icon" "$icon")
        fi
    done
}

# add_folder KIND PATH: one of the folders named after the application, deleted whole.
add_folder() {
    if [[ ! -d $2 ]]; then return 0; fi
    if holds_root "$(real_path "$2")"; then
        KEEP_ROWS+=("$1" "$2 (your simulations are inside it)")
        return 0
    fi
    FOLDERS+=("$2")
    DELETE_ROWS+=("$1" "$2")
}

find_registry() {
    if ((WINDOWS)) && has reg && MSYS2_ARG_CONV_EXCL='*' reg query "$REGISTRY_KEY" >/dev/null 2>&1 </dev/null; then
        REGISTRY=1
        DELETE_ROWS+=("Settings" "$REGISTRY_KEY (Windows registry)")
    fi
}

# find_custom_data: a paths.data folder other than the system's, of which only Lain's files go.
find_custom_data() {
    local folder item
    folder=$(data_folder "${CHECKOUT:-/}")
    if [[ -z $folder ]]; then
        KEEP_ROWS+=("Lain's data" "paths.data has a variable: delete that folder yourself")
        return 0
    fi
    if [[ ! -d $folder ]]; then return 0; fi
    folder=$(real_path "$folder")
    if [[ $folder == "$(real_path "$(system_data_dir)")" ]]; then return 0; fi
    for item in "$folder"/* "$folder"/.[!.]*; do
        if [[ -e $item ]] && is_lain_data "${item##*/}"; then
            DATA_ITEMS+=("$item")
            DELETE_ROWS+=("Lain's data" "$item")
        fi
    done
    DATA_DIR=$folder
}

decide_checkout() {
    if [[ -z $CHECKOUT ]]; then return 0; fi
    local file
    CHECKOUT_KEPT=$(keep_reason "$CHECKOUT")
    if [[ -n $CHECKOUT_KEPT ]]; then
        KEEP_ROWS+=("Program folder" "$CHECKOUT ($CHECKOUT_KEPT)")
        return 0
    fi
    for file in "$CHECKOUT"/config.yaml "$CHECKOUT"/config.yaml.bak*; do
        if [[ -f $file ]]; then
            DELETE_ROWS+=("Configuration" "$file")
        fi
    done
    DELETE_ROWS+=("Program folder" "$CHECKOUT")
    REMOVE_CHECKOUT=1
}

find_backups() {
    local parent=$HOME_DIR backup reason
    if [[ -n $CHECKOUT ]]; then
        parent=$(dirname -- "$CHECKOUT")
    fi
    for backup in "$parent"/lain-backup-*; do
        if [[ ! -d $backup ]]; then continue; fi
        reason=$(keep_reason "$backup")
        if [[ -n $reason ]]; then
            KEEP_ROWS+=("Backup" "$backup ($reason)")
        else
            BACKUPS+=("$backup")
            BACKUP_ROWS+=("Backup" "$backup")
        fi
    done
}

# cache_folder: core/appdirs.py:cache_dir. On Windows it is inside the data folder.
cache_folder() {
    if ((!WINDOWS)); then
        printf '%s/qe-studio' "${XDG_CACHE_HOME:-$HOME_DIR/.cache}"
    fi
}

discover() {
    step "What is installed"
    add_to_path "$HOME_DIR/.local/bin"
    find_program
    find_checkout
    read_configuration
    find_menu
    add_folder "Settings" "$(user_config_dir)"
    find_registry
    add_folder "Lain's data" "$(system_data_dir)"
    find_custom_data
    local cache
    cache=$(cache_folder)
    if [[ -n $cache ]]; then
        add_folder "Cache" "$cache"
    fi
    decide_checkout
    find_backups
    KEEP_ROWS+=(
        "Simulation data" "the .lain/ and plots/ folders inside your simulations"
        "uv" "the uv program and the PATH line it added"
    )
    if [[ -n ${QE_STUDIO_CONFIG:-} ]]; then
        KEEP_ROWS+=("Other config" "$QE_STUDIO_CONFIG (QE_STUDIO_CONFIG)")
    fi
}

# --- the ssh key --------------------------------------------------------------------------------

# can_rename_key: whether Lain logs in with a key that is on this computer.
can_rename_key() {
    [[ -n $HOST && -n $CLUSTER_USER && $AUTH == key && -n $KEY_PATH ]] || return 1
    LOCAL_KEY=$(local_path "$KEY_PATH")
    LOCAL_PUB="$LOCAL_KEY.pub"
    [[ -f $LOCAL_KEY ]]
}

# explain_key: what the rename does and does not do, before the question. A key is renamed and
# never deleted: nothing records whether install.sh made it, and it may serve other services. The
# cluster is production, so its authorized_keys stays as it is.
explain_key() {
    NEW_KEY=$(unique_name "$LOCAL_KEY.lain-disabled")
    NEW_PUB=$(unique_name "$LOCAL_PUB.lain-disabled")
    section "Going back to the password login (optional)"
    info "Lain logs in to the cluster with an ssh key, which has two halves:"
    info "  - the private key, on this computer: $LOCAL_KEY"
    info "  - its public key, in ~/.ssh/authorized_keys on the cluster ($CLUSTER_USER@$HOST)"
    info "While both are in use, ssh logs in without a password."
    say ""
    info "This script never connects to the cluster and changes nothing on it."
    info "If you answer yes, it only renames the key on this computer:"
    info "  $LOCAL_KEY  ->  $NEW_KEY"
    if [[ -f $LOCAL_PUB ]]; then
        info "  $LOCAL_PUB  ->  $NEW_PUB"
    fi
    info "and takes it out of ssh-agent, if it is loaded there. Nothing is deleted."
    info "ssh no longer finds the key, so it asks for your cluster password again."
    say ""
    info "Before answering yes:"
    info "  - Be sure you know your cluster password. If it does not work, rename the key back to log in."
    info "  - Anything else that uses this key (GitHub, other servers) stops working until you rename it back."
    info "  - The public key stays on the cluster, without effect while the private key is out of use."
    info "  - If another key of yours is also authorized on the cluster, ssh may still log in without a password."
}

rename_key() {
    step "The ssh key"
    if ((!RENAME_KEY)); then
        info "Skipped: the key stays as it is."
        return 0
    fi
    # While ssh-agent holds the key, ssh goes on using it. It needs the .pub, so before the rename.
    if has ssh-add; then
        ssh-add -d "$LOCAL_KEY" </dev/null >/dev/null 2>&1 || true
    fi
    if ! mv -- "$LOCAL_KEY" "$NEW_KEY"; then
        warn "could not rename $LOCAL_KEY: the key login stays as it is."
        return 0
    fi
    ok "Renamed $LOCAL_KEY to $NEW_KEY"
    RESTORE+=("mv $(shell_quote "$NEW_KEY") $(shell_quote "$LOCAL_KEY")")
    if [[ -f $LOCAL_PUB ]]; then
        if mv -- "$LOCAL_PUB" "$NEW_PUB"; then
            ok "Renamed $LOCAL_PUB to $NEW_PUB"
            RESTORE+=("mv $(shell_quote "$NEW_PUB") $(shell_quote "$LOCAL_PUB")")
        else
            warn "could not rename $LOCAL_PUB. The private key is what counts, so ssh still asks for the password."
        fi
    fi
}

# --- confirmation and removal -------------------------------------------------------------------

confirm() {
    step "Confirmation"
    if ((${#DELETE_ROWS[@]} == 0 && ${#BACKUPS[@]} == 0)); then
        info "Nothing of Lain was found to delete."
        if ((${#KEEP_ROWS[@]})); then
            titled_panel "Will not be touched" "${KEEP_ROWS[@]}"
        fi
        exit 0
    fi
    local ssh_row="$HOME_DIR/.ssh"
    if can_rename_key; then
        ssh_row="$HOME_DIR/.ssh (you can choose below to rename the key Lain uses, never to delete it)"
    fi
    if ((${#DELETE_ROWS[@]})); then
        titled_panel "Will be deleted" "${DELETE_ROWS[@]}"
    fi
    titled_panel "Will not be touched" "${KEEP_ROWS[@]}" "SSH keys" "$ssh_row" \
        "Cluster" "this script never connects to it"
    local data
    data=$(data_folder "${CHECKOUT:-/}")
    if [[ -e $(system_data_dir)/lain.lock || (-n $data && -e $data/lain.lock) ]]; then
        warn "Lain seems to be open: close it before going on."
    fi
    say ""
    if ! ask_yes_no "Delete everything listed above?" n; then
        say ""
        ok "Nothing was changed."
        exit 0
    fi

    if ((${#BACKUPS[@]})); then
        titled_panel "Backups of older versions" "${BACKUP_ROWS[@]}"
        if ask_yes_no "Also delete these backups? They hold older copies of your configuration." n; then
            DELETE_BACKUPS=1
        fi
    fi

    if can_rename_key; then
        explain_key
        say ""
        if ask_yes_no "Rename this key, so that ssh asks for your password again?" n; then
            RENAME_KEY=1
        fi
    fi
}

# remove_tree PATH: deletes PATH, never a relative path, the root or the home folder.
remove_tree() {
    local real
    if [[ $1 != /* ]]; then return 1; fi
    real=$(real_path "$1")
    if [[ $real == / || $real == "$(real_path "$HOME_DIR")" ]]; then return 1; fi
    rm -rf -- "$1"
    [[ ! -e $1 && ! -L $1 ]]
}

# remove_item PATH: deletes PATH and says so; a failure is told and the rest goes on.
remove_item() {
    if remove_tree "$1"; then
        ok "Deleted $1"
        DELETED=$((DELETED + 1))
    else
        warn "could not delete $1."
        LEFT+=("$1")
    fi
}

refresh_menu() {
    local command
    for command in update-desktop-database "kbuildsycoca6 --noincremental" "kbuildsycoca5 --noincremental"; do
        if has "${command%% *}"; then
            # shellcheck disable=SC2086  # the words of the command
            $command </dev/null >/dev/null 2>&1 || true
        fi
    done
}

remove_all() {
    step "Removing"
    local item
    if ((TOOL_INSTALLED)); then
        if uv tool uninstall lain </dev/null; then
            ok "Deleted the lain command ($TOOL_DIR)"
            DELETED=$((DELETED + 1))
        else
            warn "uv could not remove the lain command."
            LEFT+=("$TOOL_DIR")
        fi
    fi
    if ((${#MENU_FILES[@]})); then
        for item in "${MENU_FILES[@]}"; do remove_item "$item"; done
        refresh_menu
    fi
    if ((REGISTRY)); then
        if MSYS2_ARG_CONV_EXCL='*' reg delete "$REGISTRY_KEY" /f >/dev/null 2>&1 </dev/null; then
            ok "Deleted $REGISTRY_KEY"
            DELETED=$((DELETED + 1))
        else
            warn "could not delete $REGISTRY_KEY from the Windows registry."
            LEFT+=("$REGISTRY_KEY")
        fi
    fi
    if ((${#FOLDERS[@]})); then
        for item in "${FOLDERS[@]}"; do remove_item "$item"; done
    fi
    if ((${#DATA_ITEMS[@]})); then
        for item in "${DATA_ITEMS[@]}"; do remove_item "$item"; done
        # Only an empty folder goes: anything else in it is the user's.
        if [[ $DATA_DIR != "$(real_path "$HOME_DIR")" ]]; then
            rmdir -- "$DATA_DIR" 2>/dev/null || true
        fi
    fi
    if ((DELETE_BACKUPS)); then
        for item in "${BACKUPS[@]}"; do remove_item "$item"; done
    fi
    if ((REMOVE_CHECKOUT)); then
        # Windows does not delete a folder a process is in, and this script may be one.
        if is_inside "$(real_path "$CHECKOUT")" "$(pwd -P)"; then
            STARTED_INSIDE=1
            cd -- "$(dirname -- "$CHECKOUT")"
        fi
        remove_item "$CHECKOUT"
    fi
}

summary() {
    local item
    say ""
    ok "${C_BOLD}Done.${C_RESET}"
    local rows=("Deleted:" "$DELETED items")
    if [[ -n $CHECKOUT_KEPT ]]; then
        rows+=("Folder kept:" "$CHECKOUT")
    fi
    if ((${#RESTORE[@]})); then
        rows+=("Local key:" "renamed to $NEW_KEY")
    fi
    panel "Summary" "${rows[@]}"
    if ((${#RESTORE[@]})); then
        section "The ssh key"
        info "Test the password login: ${C_TEAL}ssh -p $PORT $CLUSTER_USER@$HOST${C_RESET}"
        info "To use the key again, rename it back:"
        for item in "${RESTORE[@]}"; do info "${C_TEAL}$item${C_RESET}"; done
    fi
    if ((${#LEFT[@]})); then
        section "Could not be deleted (close what is using it and delete it by hand):"
        for item in "${LEFT[@]}"; do info "$item"; done
    fi
    if ((STARTED_INSIDE)); then
        info "This terminal was in the folder just deleted: go to another one, such as cd ~"
    fi
}

# --- main ---------------------------------------------------------------------------------------

PLAIN=0

main() {
    while (($#)); do
        case $1 in
            --plain) PLAIN=1 ;;
            -h | --help)
                usage
                exit 0
                ;;
            *) die "unknown option: $1 (see --help)" ;;
        esac
        shift
    done

    trap cleanup EXIT
    trap interrupted INT TERM
    detect_platform
    setup_input
    detect_ui
    banner
    if ((!WINDOWS && EUID == 0)); then
        warn "this runs as root (sudo?): it would look for Lain in root's folders, not in yours."
        ask_yes_no "Go on as root anyway?" n || die "run it again as your own user, without sudo."
    fi

    discover
    confirm
    rename_key
    remove_all
    summary
    # Here and not after main: this file may be gone by now, as it can live in the folder it deletes.
    exit 0
}

main "$@"
