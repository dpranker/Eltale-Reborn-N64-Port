#!/bin/sh
# Starts ares on a ROM with the gdb server waiting for a client, then runs a gdb script against it. Exits
# with gdb's status. Stops only the ares it started. Uses settings under build/, so the user's stay
# untouched, and its own port, so another ares can stay open.
# usage: tests/run_ares.sh <rom> <script.gdb> <timeout seconds> [ares args...]
rom="$1"; script="$2"; limit="$3"; shift 3
dir="$(cd "$(dirname "$0")/.." && pwd)/build/ares"
port=9124
mkdir -p "$dir/saves"
: > "$dir/settings.bml"
ares --settings-file "$dir/settings.bml" --system "Nintendo 64" --no-file-prompt \
    --setting DebugServer/Enabled=true --setting DebugServer/Port=$port --setting DebugServer/UseIPv4=true \
    --setting Boot/AwaitGDBClient=true --setting Audio/Driver=None --setting Input/Defocus=Allow \
    --setting "Paths/Saves=$dir/saves/" "$@" "$rom" > "$dir/ares.log" 2>&1 &
ares_pid=$!
trap 'kill "$ares_pid" 2>/dev/null' EXIT

tries=0
until ss -ltn | grep -q ":$port "; do
    tries=$((tries + 1))
    if [ "$tries" -gt 100 ]; then echo "ares didn't open port $port"; exit 2; fi
    sleep 0.2
done
timeout --foreground --signal=INT --kill-after=15 "$limit" gdb -q -batch -ex "set \$port = $port" -x "$script"
status=$?
[ "$status" = 124 ] && echo "TIMEOUT after ${limit}s: $script"
exit "$status"
