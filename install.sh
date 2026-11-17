#!/usr/bin/env bash
# Lain: QE Studio installer, for Linux and for Windows (in Git Bash, which comes with Git for Windows).
#
# Runs the README's "Install, step by step" in order: uv, the code (git clone), config.yaml (asks for
# the paths, the cluster login and the e-mail of the jobs), the ssh login, the `lain` command and, on
# Linux, the application menu entry.
#
#   curl -fsSL https://raw.githubusercontent.com/Mariano17omega/Lain/main/install.sh | bash
#   bash install.sh                      # from anywhere, or from inside a checkout
#   bash install.sh --config-only [DIR]  # only (re)write DIR/config.yaml
#   bash install.sh --plain              # plain text and typed answers, also on a terminal
#
# Run over an installation, it offers the newer version the repository has: the old folder becomes
# lain-backup-<version>, the new one takes its place and the configuration goes on working.
#
# Environment: LAIN_REPO_URL (what to clone), LAIN_DIR (the default install folder), NO_COLOR.

set -euo pipefail

# The script's own file, empty when it came through a pipe (curl ... | bash). Read here, at the top:
# inside a function a piped script's BASH_SOURCE[0] is "main".
SCRIPT_PATH=${BASH_SOURCE[0]:-}
# The user's own PATH, before this script adds uv's folder to it: what a new terminal will have.
ORIGINAL_PATH=$PATH

REPO_URL="${LAIN_REPO_URL:-https://github.com/Mariano17omega/Lain.git}"
RAW_URL="https://raw.githubusercontent.com/Mariano17omega/Lain/main/install.sh"

# The defaults of the LUCCI group. A leading ~ is kept in config.yaml: Lain expands it on this
# computer, and the cluster's shell expands the one of remote_root. DEFAULT_LOCAL_ROOT is set by
# default_local_root (the Documents folder), FALLBACK_LOCAL_ROOT when there is none to ask for.
# shellcheck disable=SC2088  # the tilde is meant to stay unexpanded
FALLBACK_LOCAL_ROOT="~/Documentos/LUCCI"
DEFAULT_LOCAL_ROOT=$FALLBACK_LOCAL_ROOT
# shellcheck disable=SC2088
DEFAULT_REMOTE_ROOT="~/LUCCI"
# shellcheck disable=SC2088
DEFAULT_KEY_PATH="~/.ssh/id_ed25519"
# shellcheck disable=SC2088
DEFAULT_CHECKOUT="${LAIN_DIR:-~/Lain}"
DEFAULT_PORT=22
DEFAULT_AUTH=key

# What core/config.py accepts as jobs.myemail (_EMAIL): one @ with text on both sides, and nothing
# that would break MYEMAIL="..." in a job script.
EMAIL_RE='^[^[:space:]@'\''"`$\\]+@[^[:space:]@'\''"`$\\]+$'

# What ssh-copy-id does, for the systems without it (Git Bash on Windows): the key from stdin goes
# into authorized_keys after a newline, so it never joins a last line that has none (sshd skips
# blank lines). Plain enough for any login shell, csh included; no single quote, as it is shown
# between single quotes.
# shellcheck disable=SC2088  # the cluster's shell expands the tilde
REMOTE_ADD_KEY='umask 077; mkdir -p ~/.ssh && echo >> ~/.ssh/authorized_keys && cat >> ~/.ssh/authorized_keys'

STEP=0
TOTAL_STEPS=7
WINDOWS=0
HOME_DIR=$HOME
CHECKOUT=""
TMP_CONFIG=""
PENDING=()   # commands of the steps the user skipped, shown at the end
NEW_TERMINAL=0

# The answers.
LOCAL_ROOT="" REMOTE_ROOT="" XCRYSDEN="" DATA=""
HOST="" PORT="" CLUSTER_USER="" AUTH="" KEY_PATH="" EMAIL=""
CREATE_LOCAL_ROOT=0

# The update (offer_update).
UPDATED=0 UPDATE_DECLINED=0 KEPT_SETUP=0 STARTED_INSIDE=0
UPDATE_FROM="" UPDATE_TO="" UPDATE_BACKUP=""
UPDATE_TMP=""                  # the temp folder next to the installation, with the new version
SWAP_TARGET="" SWAP_BACKUP=""  # set only while the installation is renamed and the new one is not in place

# The look, set by detect_ui. All empty or 0 is plain ASCII: what a run without a terminal prints.
PLAIN=0        # --plain
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
pending() { PENDING+=("$*"); }

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

banner() {
    local platform=Linux version="" here cols
    if ((WINDOWS)); then
        platform="Windows, Git Bash"
    fi
    if ((!UI_ON)); then
        say "Lain: QE Studio installer ($platform)"
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
    printf ' %s Lain: QE Studio %s %s%sinstaller (%s)%s\n' \
        "$C_BADGE" "$C_RESET" "$C_DIM" "$version" "$platform" "$C_RESET"
    if ((UI_GLYPHS)); then
        printf '%s%s%s\n' "$C_DIM" "$(repeat ─ $((cols - 2)))" "$C_RESET"
    fi
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

usage() {
    cat <<EOF
Lain: QE Studio installer (Linux, and Windows in Git Bash).

Usage:
  curl -fsSL $RAW_URL | bash
  bash install.sh                      install: uv, git clone, config.yaml, ssh, the lain command
  bash install.sh --config-only [DIR]  only (re)write DIR/config.yaml (default: this checkout)
  bash install.sh --plain              plain text and typed answers, also on a terminal
  bash install.sh --help

Environment:
  LAIN_REPO_URL  repository to clone (default: $REPO_URL)
  LAIN_DIR       default install folder (default: ~/Lain)
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
  curl -fsSL $RAW_URL -o install.sh && bash install.sh"
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

# ask_required VAR "Question" [DEFAULT]: asks again until there is an answer.
ask_required() {
    while true; do
        ask "$@"
        [[ -n ${!1} ]] && return 0
        retry "This one is required."
    done
}

# ask_full_path VAR "Question" [DEFAULT]: asks again until the answer is a full path (full_path_ok).
ask_full_path() {
    while true; do
        ask_required "$@"
        full_path_ok "${!1}" && return 0
        retry "$FULL_PATH_HINT"
    done
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

# default_local_root: LUCCI in the user's Documents folder, with ~ for the home folder:
# ~/Documentos/LUCCI on a Portuguese Linux desktop, ~/Documents/LUCCI on an English one and on
# Windows (where "Documentos" is only the name Explorer shows for Documents).
default_local_root() {
    local docs=""
    if ((WINDOWS)); then
        # shellcheck disable=SC2088
        DEFAULT_LOCAL_ROOT="~/Documents/LUCCI"
        return 0
    fi
    if has xdg-user-dir; then
        docs=$(xdg-user-dir DOCUMENTS </dev/null 2>/dev/null || true)
        docs=${docs%/}
    fi
    # xdg-user-dir prints the home folder itself when no Documents folder is set.
    if [[ -z $docs || $docs != /* || $docs == "$HOME_DIR" ]]; then
        DEFAULT_LOCAL_ROOT=$FALLBACK_LOCAL_ROOT
    elif [[ $docs == "$HOME_DIR"/* ]]; then
        # shellcheck disable=SC2088
        DEFAULT_LOCAL_ROOT="~/${docs#"$HOME_DIR"/}/LUCCI"
    else
        DEFAULT_LOCAL_ROOT="$docs/LUCCI"
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

FULL_PATH_HINT="Give the full path: it starts with / or ~ (or a drive letter on Windows), with no \$VARIABLE."

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

# native_path PATH: the path as Lain reads it from config.yaml or uv takes it as an argument. On
# Windows /c/Users/me becomes C:/Users/me; a leading ~ stays for Lain to expand.
native_path() {
    if ((WINDOWS)) && [[ -n $1 && $1 != \~ && $1 != \~/* ]]; then
        cygpath -m "$1"
    else
        printf '%s' "$1"
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

# --- config.yaml --------------------------------------------------------------------------------

# yaml_str VALUE: VALUE as a double-quoted YAML string (sed, the same on every platform).
yaml_str() {
    printf '"%s"' "$(printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')"
}

# set_key FILE SECTION KEY VALUE: the `  KEY:` line of the top-level SECTION becomes `  KEY: VALUE`.
# Without that line, the new one goes right after a commented `  # KEY:` (how config.example.yaml
# ships jobs.myemail). Every other line stays as it was, CR LF endings included. The value reaches
# awk through the environment, where backslashes are not escapes.
set_key() {
    local file=$1 tmp status=0
    tmp=$(mktemp "$file.XXXXXX")
    SECTION=$2 KEY=$3 VALUE=$4 awk '
        { line[NR] = $0 }
        END {
            target = 0; comment = 0; section = ""
            for (i = 1; i <= NR; i++) {
                text = line[i]; sub(/\r$/, "", text)
                if (text ~ /^[A-Za-z_][A-Za-z0-9_]*:/) {
                    section = text; sub(/:.*/, "", section); continue
                }
                if (section != ENVIRON["SECTION"]) continue
                if (!target && index(text, "  " ENVIRON["KEY"] ":") == 1) target = i
                if (!comment && index(text, "  # " ENVIRON["KEY"] ":") == 1) comment = i
            }
            if (!target && !comment) exit 3
            new = "  " ENVIRON["KEY"] ": " ENVIRON["VALUE"]
            for (i = 1; i <= NR; i++) {
                eol = (line[i] ~ /\r$/) ? "\r" : ""
                if (i == target) { print new eol; continue }
                print line[i]
                if (!target && i == comment) print new eol
            }
        }' "$file" >"$tmp" || status=$?
    if ((status != 0)); then
        rm -f -- "$tmp"
        die "could not set $2.$3 in $file (no \"$3:\" line under \"$2:\")."
    fi
    mv -f -- "$tmp" "$file"
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

# unique_name PATH: PATH, or PATH_2, PATH_3... the first one that does not exist.
unique_name() {
    local candidate=$1 n=2
    while [[ -e $candidate ]]; do
        candidate="${1}_$n"
        n=$((n + 1))
    done
    printf '%s' "$candidate"
}

cleanup() {
    show_cursor
    if [[ -n $TMP_CONFIG && -e $TMP_CONFIG ]]; then
        rm -f -- "$TMP_CONFIG"
    fi
    # Stopped between the two renames: the old installation goes back to its name.
    if [[ -n $SWAP_BACKUP && -e $SWAP_BACKUP && ! -e $SWAP_TARGET ]]; then
        mv -- "$SWAP_BACKUP" "$SWAP_TARGET" || warn "your installation is now $SWAP_BACKUP: rename it to $SWAP_TARGET."
    fi
    if [[ -n $UPDATE_TMP && -e $UPDATE_TMP ]]; then
        rm -rf -- "$UPDATE_TMP"
    fi
}

# Ctrl+C or a kill: the EXIT trap (cleanup) still runs after this.
interrupted() {
    show_cursor
    printf '\n%sInstallation interrupted.%s\n' "$C_YELLOW" "$C_RESET"
    exit 130
}

# xcrysden_ok PATH: what core/files/xcrysden.py:locate accepts, the install folder holding the
# executable `xcrysden` or the executable itself.
xcrysden_ok() {
    local path
    path=$(local_path "$1")
    if [[ -d $path ]]; then
        [[ -f $path/xcrysden && -x $path/xcrysden ]]
    else
        [[ -f $path && -x $path ]]
    fi
}

detect_xcrysden() {
    if [[ -n ${XCRYSDEN_TOPDIR:-} ]] && xcrysden_ok "$XCRYSDEN_TOPDIR"; then
        printf '%s' "$XCRYSDEN_TOPDIR"
    elif has xcrysden; then
        command -v xcrysden
    fi
}

ask_paths() {
    section "Folders (paths)"
    ask_full_path LOCAL_ROOT "Local folder of your simulations (paths.local_root)" "$DEFAULT_LOCAL_ROOT"
    local local_root
    local_root=$(local_path "$LOCAL_ROOT")
    CREATE_LOCAL_ROOT=0
    if [[ ! -d $local_root ]]; then
        if ask_yes_no "  $local_root does not exist. Create it?" y; then
            CREATE_LOCAL_ROOT=1
        else
            info "Lain will warn that the local folder is missing until it exists."
        fi
    fi

    ask_required REMOTE_ROOT "The same folder on the cluster (paths.remote_root)" "$DEFAULT_REMOTE_ROOT"

    local found
    found=$(detect_xcrysden || true)
    if [[ -n $found ]]; then
        ok "XCrySDen found: $found"
    else
        info "XCrySDen was not found (XCRYSDEN_TOPDIR is not set and 'xcrysden' is not on PATH)."
        info "Type its install folder (the one holding the 'xcrysden' script) or the script itself."
    fi
    while true; do
        ask XCRYSDEN "XCrySDen (paths.xcrysden_path; Enter or 'none': leave it blank)" "$found"
        if [[ -z $XCRYSDEN || ${XCRYSDEN,,} == none ]]; then
            XCRYSDEN=""
            warn "paths.xcrysden_path is blank: \"Open with XCrySDen\" stays disabled until you set it."
            break
        fi
        if ! full_path_ok "$XCRYSDEN"; then
            retry "$FULL_PATH_HINT"
            continue
        fi
        xcrysden_ok "$XCRYSDEN" && break
        retry "There is no executable 'xcrysden' at $XCRYSDEN. Try again, or type 'none' to leave it blank."
    done

    ask DATA "Folder for Lain's own data, relative to config.yaml (paths.data; Enter: the system's default)"
}

ask_cluster() {
    section "Cluster login (cluster)"
    while true; do
        ask_required HOST "Host (cluster.host)"
        [[ $HOST =~ ^[A-Za-z0-9._:%-]+$ && $HOST != -* ]] && break
        retry "A host name or address has no spaces, no @ and does not start with '-'."
    done
    while true; do
        ask PORT "Port (cluster.port)" "$DEFAULT_PORT"
        if [[ $PORT =~ ^[0-9]{1,5}$ ]] && ((10#$PORT >= 1 && 10#$PORT <= 65535)); then
            PORT=$((10#$PORT))
            break
        fi
        retry "The port is a number from 1 to 65535."
    done
    while true; do
        ask_required CLUSTER_USER "User (cluster.user)"
        [[ $CLUSTER_USER =~ ^[A-Za-z0-9._][A-Za-z0-9._-]*$ ]] && break
        retry "A user name has only letters, digits, '.', '_' and '-'."
    done
    if ((UI_MENUS)); then
        local methods=(key password) picked
        select_menu picked "Login with an ssh key or a password (cluster.auth)" 0 "${methods[@]}"
        AUTH=${methods[picked]}
    else
        while true; do
            ask AUTH "Login with an ssh key or a password (cluster.auth: key or password)" "$DEFAULT_AUTH"
            AUTH=${AUTH,,}
            [[ $AUTH == key || $AUTH == password ]] && break
            retry "Answer key or password."
        done
    fi
    if [[ $AUTH == key ]]; then
        ask_full_path KEY_PATH "SSH private key (cluster.key_path)" "$DEFAULT_KEY_PATH"
    else
        KEY_PATH=""
        info "Lain reads the password from the environment variable QE_STUDIO_SSH_PASSWORD"
        info "(cluster.password_env). It is never asked here nor written to config.yaml."
    fi
}

ask_email() {
    section "Jobs (jobs)"
    while true; do
        ask EMAIL "E-mail the cluster notifies when a job starts and ends (jobs.myemail; Enter: skip)"
        [[ -z $EMAIL || $EMAIL =~ $EMAIL_RE ]] && break
        retry "That is not an e-mail address (one @, no spaces or quotes)."
    done
}

write_config() {
    local file=$1
    set_key "$file" paths local_root "$(yaml_str "$(native_path "$LOCAL_ROOT")")"
    set_key "$file" paths remote_root "$(yaml_str "$REMOTE_ROOT")"
    set_key "$file" paths xcrysden_path "$(yaml_str "$(native_path "$XCRYSDEN")")"
    set_key "$file" paths data "$(yaml_str "$(native_path "$DATA")")"
    set_key "$file" cluster host "$(yaml_str "$HOST")"
    set_key "$file" cluster port "$PORT"
    set_key "$file" cluster user "$(yaml_str "$CLUSTER_USER")"
    set_key "$file" cluster auth "$AUTH"
    if [[ $AUTH == key ]]; then
        set_key "$file" cluster key_path "$(yaml_str "$(native_path "$KEY_PATH")")"
    fi
    if [[ -n $EMAIL ]]; then
        set_key "$file" jobs myemail "$(yaml_str "$EMAIL")"
    fi
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

configure() {
    local dir=$1
    local config="$dir/config.yaml" example="$dir/config.example.yaml"
    step "The configuration (config.yaml)"
    [[ -f $example ]] || die "$example was not found."
    if ((UPDATED)) && [[ -e $config || -e $(user_config_dir)/config.yaml ]]; then
        ok "Your configuration was kept."
        KEPT_SETUP=1
        return 0
    fi
    if [[ -e $config ]]; then
        info "$config already exists."
        if ! ask_yes_no "Reconfigure it? (the current file is kept as a backup)" n; then
            info "Kept as it is."
            read_cluster_from "$config"
            return 0
        fi
    fi

    ask_paths
    ask_cluster
    ask_email

    # Written whole: a copy of the example is edited, then takes the place of config.yaml at once.
    TMP_CONFIG=$(mktemp "$dir/.config.yaml.XXXXXX")
    cp -- "$example" "$TMP_CONFIG"
    write_config "$TMP_CONFIG"
    if [[ -e $config ]]; then
        local backup
        backup=$(unique_name "$config.bak")
        cp -p -- "$config" "$backup"
        info "The previous config.yaml is now $backup"
    fi
    mv -f -- "$TMP_CONFIG" "$config"
    TMP_CONFIG=""
    if ((CREATE_LOCAL_ROOT)); then
        mkdir -p -- "$(local_path "$LOCAL_ROOT")"
        ok "Created $(local_path "$LOCAL_ROOT")"
    fi

    say ""
    ok "Wrote $config (cp config.example.yaml config.yaml, then these keys):"
    local rows=(
        paths.local_root "$LOCAL_ROOT"
        paths.remote_root "$REMOTE_ROOT"
        paths.xcrysden_path "${XCRYSDEN:-(blank)}"
        paths.data "${DATA:-(blank: the system default)}"
        cluster "$CLUSTER_USER@$HOST, port $PORT, auth $AUTH"
    )
    if [[ $AUTH == key ]]; then
        rows+=(cluster.key_path "$KEY_PATH")
    fi
    rows+=(jobs.myemail "${EMAIL:-(not set)}")
    panel "config.yaml" "${rows[@]}"
}

# --- the other steps ----------------------------------------------------------------------------

check_prereqs() {
    step "The programs Lain needs"
    if has git; then
        ok "git: $(command -v git)"
    elif [[ -n $(script_checkout) ]]; then
        info "git: not found (not needed: this script runs from a Lain folder)."
    elif ((WINDOWS)); then
        die "git was not found. Install Git for Windows (https://git-scm.com/download/win) and run this script in Git Bash."
    else
        die "git was not found. Install it first (Debian/Ubuntu: sudo apt install git)."
    fi
    if has ssh; then
        ok "ssh: $(command -v ssh)"
    else
        warn "ssh was not found: Lain needs it to reach the cluster (Debian/Ubuntu: sudo apt install openssh-client)."
    fi
    if has rsync; then
        ok "rsync: $(command -v rsync)"
    elif ((WINDOWS)); then
        warn "rsync was not found: Lain needs it to sync with the cluster, and Git Bash does not ship it (MSYS2 or cwRsync provide one)."
    else
        warn "rsync was not found: Lain needs it to sync with the cluster (Debian/Ubuntu: sudo apt install rsync)."
    fi
}

ensure_uv() {
    step "uv, the Python environment manager"
    add_to_path "$HOME_DIR/.local/bin"
    if has uv; then
        ok "uv: $(command -v uv) ($(uv --version </dev/null))"
        return 0
    fi
    ask_yes_no "uv was not found. Install it now (https://docs.astral.sh/uv/)?" y ||
        die "Lain needs uv. Install it and run this script again."
    if ((WINDOWS)); then
        powershell -NoProfile -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex" </dev/null ||
            die "the uv installer failed (see above). Install uv by hand (https://docs.astral.sh/uv/) and run this script again."
    else
        has curl || die "curl was not found: install it (Debian/Ubuntu: sudo apt install curl) or install uv by hand."
        curl -LsSf https://astral.sh/uv/install.sh | sh ||
            die "the uv installer failed (see above). Install uv by hand (https://docs.astral.sh/uv/) and run this script again."
    fi
    add_to_path "$HOME_DIR/.local/bin"
    hash -r
    has uv || die "uv was installed but is not on PATH. Open a new terminal and run this script again."
    ok "uv: $(command -v uv)"
    NEW_TERMINAL=1
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

# --- update -------------------------------------------------------------------------------------

# project_version DIR: the version in DIR/pyproject.toml, empty when there is none.
project_version() {
    sed -n '/^version = "/{s/^version = "\([^"]*\)".*/\1/p;q;}' "$1/pyproject.toml" 2>/dev/null || true
}

version_ok() { [[ $1 =~ ^[0-9]+(\.[0-9]+)*$ ]]; }

# version_newer A B: whether A is a later version than B, number by number (1.0.10 is after 1.0.9).
version_newer() {
    local a b i count x y
    IFS=. read -r -a a <<<"$1"
    IFS=. read -r -a b <<<"$2"
    count=${#a[@]}
    if ((${#b[@]} > count)); then count=${#b[@]}; fi
    for ((i = 0; i < count; i++)); do
        x=$((10#${a[i]:-0}))
        y=$((10#${b[i]:-0}))
        if ((x > y)); then return 0; fi
        if ((x < y)); then return 1; fi
    done
    return 1
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

# copy_item SOURCE TARGET: nothing of the installation has changed yet when this fails.
copy_item() {
    cp -Rp -- "$1" "$2" || die "could not copy $1. Nothing was changed."
}

# copy_config_backup DIR NEW SAVED: copies the configuration of the installation in DIR to the folder
# SAVED. What lives inside DIR also goes to NEW, the new version; what lives outside stays where it
# is, for the new version to go on using it.
copy_config_backup() {
    local dir=$1 new=$2 saved=$3 file folder settings relative
    mkdir -m 700 -- "$saved" || die "could not create $saved. Nothing was changed."
    for file in "$dir"/config.yaml "$dir"/config.yaml.bak*; do
        if [[ -f $file ]]; then
            copy_item "$file" "$saved/"
            copy_item "$file" "$new/"
        fi
    done

    settings=$(user_config_dir)
    if [[ -d $settings ]]; then
        copy_item "$settings" "$saved/settings"
    fi

    folder=$(data_folder "$dir")
    if [[ -z $folder ]]; then
        warn "paths.data has a variable: its folder stays where it is, without a copy in the backup."
        return 0
    fi
    [[ -d $folder ]] || return 0
    folder=$(cd -- "$folder" && pwd)
    case $dir/ in
        "$folder"/*)
            warn "paths.data holds the whole installation: its files stay in the backup only."
            return 0
            ;;
    esac
    copy_item "$folder" "$saved/data"
    rm -rf -- "$saved/data/lain.lock" "$saved/data/cache"
    case $folder/ in
        "$dir"/*)
            relative=${folder#"$dir"/}
            mkdir -p -- "$new/$relative" || die "could not create $new/$relative. Nothing was changed."
            copy_item "$folder/." "$new/$relative"
            rm -rf -- "${new:?}/$relative/lain.lock" "${new:?}/$relative/cache"
            ;;
    esac
}

# swap_folders DIR NEW BACKUP: DIR becomes BACKUP and NEW takes its place. A failure on the way
# leaves DIR as it was (cleanup renames it back).
swap_folders() {
    local dir=$1 new=$2 backup=$3 hint="Close every program using it and run this from another folder."
    # Windows does not rename a folder a process is in, and this script may be one.
    case $(pwd -P)/ in
        "$(cd -- "$dir" && pwd -P)"/*)
            STARTED_INSIDE=1
            cd -- "$(dirname -- "$dir")"
            ;;
    esac
    SWAP_TARGET=$dir
    SWAP_BACKUP=$backup
    mv -- "$dir" "$backup" || die "could not rename $dir. Nothing was changed. $hint"
    mv -- "$new" "$dir" || die "could not put the new version in $dir. Your installation stays as it was. $hint"
    SWAP_TARGET="" SWAP_BACKUP=""
}

discard_update() {
    rm -rf -- "$UPDATE_TMP"
    UPDATE_TMP=""
}

# offer_update DIR: when the repository has a later version than the installation in DIR, asks
# and replaces it. The new version is downloaded first, so that a failure touches nothing. Only an
# installation of REPO_URL: a clone of another repository is someone's work, not an install.
offer_update() {
    local dir=$1 installed latest backup origin output new saved
    has git || return 0
    installed=$(project_version "$dir")
    version_ok "$installed" || return 0
    if [[ -d $dir/.git ]]; then
        origin=$(git -C "$dir" remote get-url origin </dev/null 2>/dev/null || true)
        if ! same_repo "$origin" "$REPO_URL"; then
            info "This folder is a clone of another repository: not looking for updates."
            return 0
        fi
    fi

    info "Looking for a newer version (installed: $installed)."
    if ! UPDATE_TMP=$(mktemp -d "$(dirname -- "$dir")/.lain-update.XXXXXX"); then
        UPDATE_TMP=""
        warn "could not create a temp folder next to $dir: going on with version $installed."
        return 0
    fi
    new="$UPDATE_TMP/new"
    saved="$UPDATE_TMP/config-backup"
    if ! output=$(GIT_TERMINAL_PROMPT=0 git clone -- "$REPO_URL" "$new" </dev/null 2>&1); then
        warn "could not look for updates (${output##*$'\n'}): going on with version $installed."
        discard_update
        return 0
    fi
    latest=$(project_version "$new")
    if ! is_lain_checkout "$new" || ! version_ok "$latest"; then
        warn "could not read the version in $REPO_URL: going on with version $installed."
        discard_update
        return 0
    fi
    if ! version_newer "$latest" "$installed"; then
        ok "Lain is up to date (version $installed)."
        discard_update
        return 0
    fi

    backup=$(unique_name "$(dirname -- "$dir")/lain-backup-$installed")
    if [[ -d $dir/.git && -n $(git -C "$dir" status --porcelain </dev/null 2>/dev/null || true) ]]; then
        warn "this folder has uncommitted changes: they stay in the backup, not in the new version."
    fi
    local data
    data=$(data_folder "$dir")
    if [[ -n $data && -e $data/lain.lock ]]; then
        warn "Lain seems to be open: close it before updating."
    fi
    if ! ask_yes_no "Lain $latest is available (installed: $installed). Update? This folder is kept as $backup" y; then
        UPDATE_DECLINED=1
        discard_update
        return 0
    fi

    copy_config_backup "$dir" "$new" "$saved"
    swap_folders "$dir" "$new" "$backup"
    # After the swap: the update is done even if this last copy fails, and the backup has config.yaml.
    mv -- "$saved" "$(unique_name "$backup/config-backup")" ||
        warn "could not save the configuration's copy in $backup."
    discard_update
    UPDATED=1 UPDATE_FROM=$installed UPDATE_TO=$latest UPDATE_BACKUP=$backup
    ok "Updated to version $latest. The previous one is in $backup"
}

get_code() {
    step "The code"
    local here dir
    here=$(script_checkout)
    if [[ -n $here ]]; then
        CHECKOUT=$here
        info "Using the checkout this script is in: $CHECKOUT"
        offer_update "$CHECKOUT"
        return 0
    fi
    ask_required dir "Folder to install Lain into" "$DEFAULT_CHECKOUT"
    dir=$(local_path "$dir")
    if is_lain_checkout "$dir"; then
        dir=$(cd -- "$dir" && pwd)
        info "Lain is already in $dir."
        offer_update "$dir"
        if ((!UPDATED && !UPDATE_DECLINED)) && [[ -d $dir/.git ]] && ask_yes_no "Update it (git pull --ff-only)?" y; then
            git -C "$dir" pull --ff-only <&3 ||
                warn "git pull failed: going on with the code as it is (update it later with git pull)."
        fi
    elif [[ -e $dir && -n $(ls -A -- "$dir" 2>/dev/null) ]]; then
        die "$dir already exists and is not a Lain checkout. Choose another folder."
    else
        info "git clone $REPO_URL $dir"
        git clone -- "$REPO_URL" "$dir" <&3 || die "git clone failed (see above)."
    fi
    CHECKOUT=$(cd "$dir" && pwd)
}

copy_key() {
    local pub=$1 login=$2
    if has ssh-copy-id; then
        ssh-copy-id -i "$pub" -p "$PORT" "$login" <&3
    else
        ssh -p "$PORT" "$login" "$REMOTE_ADD_KEY" <"$pub"
    fi
}

setup_ssh() {
    step "The ssh login to the cluster"
    if ((KEPT_SETUP)); then
        info "Not changed by the update: skipped."
        return 0
    fi
    if [[ -z $HOST || -z $CLUSTER_USER ]]; then
        info "No cluster in config.yaml: skipped."
        return 0
    fi
    if ! has ssh; then
        warn "ssh was not found: skipped."
        return 0
    fi
    local login="$CLUSTER_USER@$HOST"
    info "Lain refuses unknown host keys: the first login below makes ssh trust the cluster's key."
    info "Each step asks first."

    if [[ $AUTH != key ]]; then
        local test_cmd="ssh -p $PORT $login true"
        if ask_yes_no "Log in once now ($test_cmd; asks for your password)?" n; then
            if ssh -p "$PORT" "$login" true <&3; then
                ok "The login works."
            else
                warn "The login failed."
                pending "$test_cmd"
            fi
        else
            pending "$test_cmd"
        fi
        return 0
    fi

    local key pub key_shown
    key=$(local_path "$KEY_PATH")
    pub="$key.pub"
    key_shown=$(shell_quote "$key")
    if [[ ! -f $key ]]; then
        if ask_yes_no "There is no key at $key. Create one (ssh-keygen -t ed25519)?" n; then
            # shellcheck disable=SC2174  # only the key's own folder (~/.ssh) needs to be private
            mkdir -p -m 700 -- "$(dirname -- "$key")"
            ssh-keygen -t ed25519 -f "$key" <&3 || warn "ssh-keygen failed."
        else
            pending "ssh-keygen -t ed25519 -f $key_shown"
        fi
    fi

    local copy_cmd
    if has ssh-copy-id; then
        copy_cmd="ssh-copy-id -i $key_shown.pub -p $PORT $login"
    else
        copy_cmd="ssh -p $PORT $login '$REMOTE_ADD_KEY' < $key_shown.pub"
    fi
    if [[ ! -f $pub ]]; then
        pending "$copy_cmd"
    elif ask_yes_no "Copy the public key to the cluster ($copy_cmd; asks for your cluster password)?" n; then
        copy_key "$pub" "$login" || {
            warn "Copying the key failed."
            pending "$copy_cmd"
        }
    else
        pending "$copy_cmd"
    fi

    # IdentitiesOnly, as Lain uses it: only this key counts, not another one ssh-agent holds.
    local test_cmd="ssh -p $PORT -i $key_shown -o IdentitiesOnly=yes $login true"
    if [[ ! -f $key ]]; then
        pending "$test_cmd"
    elif ask_yes_no "Test the login with the key now ($test_cmd)?" n; then
        if ssh -p "$PORT" -i "$key" -o IdentitiesOnly=yes -o PreferredAuthentications=publickey \
            "$login" true <&3; then
            ok "The login works without a password."
            info "A key with a passphrase must be loaded in ssh-agent (ssh-add) before Lain uses it."
        else
            warn "The login with the key failed: copy the key first; a key with a passphrase needs ssh-agent."
            pending "$test_cmd"
        fi
    else
        pending "$test_cmd"
    fi
}

install_tool() {
    step "The lain command"
    info "uv tool install --editable --force $CHECKOUT"
    uv tool install --editable --force "$(native_path "$CHECKOUT")" </dev/null ||
        die "uv tool install failed (see above). Run it again: uv tool install --editable --force $(shell_quote "$CHECKOUT")"
    local bin
    bin=$(uv tool dir --bin </dev/null) || bin=""
    if ((WINDOWS)) && [[ -n $bin ]]; then
        bin=$(cygpath -u "$bin")
    fi
    if [[ -n $bin ]]; then
        add_to_path "$bin"
    fi
    hash -r
    if has lain; then
        ok "lain: $(command -v lain)"
    fi
    # This script's PATH has uv's folders (ensure_uv added one): what counts is the user's own.
    if [[ -z $bin ]] || ! on_path "$bin" "$ORIGINAL_PATH"; then
        local where=$bin
        [[ -n $where ]] || where="the folder of uv's tools"
        info "Adding $where to your PATH (uv tool update-shell)."
        uv tool update-shell </dev/null || warn "Add $where to your PATH by hand."
        NEW_TERMINAL=1
    fi
}

desktop_entry() {
    step "The application menu"
    if ((KEPT_SETUP)); then
        info "Not changed by the update: skipped."
        return 0
    fi
    if ((WINDOWS)); then
        info "Skipped: the menu entry is for Linux desktops."
        return 0
    fi
    if ask_yes_no "Add Lain to the application menu, with its icon?" n; then
        uv run --no-project python "$CHECKOUT/scripts/install_desktop.py" </dev/null ||
            warn "The menu entry was not installed."
    else
        pending "cd $(shell_quote "$CHECKOUT") && uv run --no-project python scripts/install_desktop.py"
    fi
}

summary() {
    local config=$1
    say ""
    ok "${C_BOLD}Done.${C_RESET}"
    local rows=("Configuration:" "$config")
    if [[ $MODE == full ]]; then
        rows+=("Lain:" "$CHECKOUT")
        if ((NEW_TERMINAL)); then
            rows+=("Start it:" "lain   (open a new terminal first, so PATH has it)")
        else
            rows+=("Start it:" "lain")
        fi
        if ((UPDATED)); then
            rows+=("Updated:" "$UPDATE_FROM -> $UPDATE_TO" "Backup:" "$UPDATE_BACKUP")
        fi
    fi
    panel "Summary" "${rows[@]}"
    if ((STARTED_INSIDE)); then
        info "This terminal is still in the old folder, now the backup. Go to the new one: cd $(shell_quote "$CHECKOUT")"
    fi
    if ((${#PENDING[@]})); then
        section "Steps you skipped, to run when you want:"
        local cmd
        for cmd in "${PENDING[@]}"; do
            info "${C_TEAL}$cmd${C_RESET}"
        done
    fi
    say ""
    local dir=${CHECKOUT:-$CONFIG_DIR}
    if [[ -f $dir/install.sh ]]; then
        say "To change the answers later: bash $(shell_quote "$dir/install.sh") --config-only"
    else
        say "To change the answers later: bash install.sh --config-only $(shell_quote "$dir")"
    fi
}

# --- main ---------------------------------------------------------------------------------------

MODE=full
CONFIG_DIR=""

main() {
    while (($#)); do
        case $1 in
            --config-only)
                MODE=config
                if [[ -n ${2:-} && $2 != -* ]]; then
                    CONFIG_DIR=$2
                    shift
                fi
                ;;
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
    default_local_root
    setup_input
    detect_ui
    banner
    if ((!WINDOWS && EUID == 0)); then
        warn "this runs as root (sudo?): uv, Lain and its settings would be installed for root, not for you."
        ask_yes_no "Go on as root anyway?" n || die "run it again as your own user, without sudo."
    fi

    if [[ $MODE == config ]]; then
        TOTAL_STEPS=1
        if [[ -z $CONFIG_DIR ]]; then
            CONFIG_DIR=$(script_checkout)
            [[ -n $CONFIG_DIR ]] || die "give the Lain folder: install.sh --config-only DIR"
        fi
        local dir
        dir=$(local_path "$CONFIG_DIR")
        [[ -d $dir ]] || die "$CONFIG_DIR is not a folder."
        CONFIG_DIR=$(cd "$dir" && pwd)
        configure "$CONFIG_DIR"
        summary "$CONFIG_DIR/config.yaml"
        return 0
    fi

    check_prereqs
    ensure_uv
    get_code
    configure "$CHECKOUT"
    setup_ssh
    install_tool
    desktop_entry
    summary "$CHECKOUT/config.yaml"
}

main "$@"
