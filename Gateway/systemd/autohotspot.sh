#!/bin/bash
set -eu
export LC_ALL=C

HOTSPOT='Aetheria-Hotspot'
log() { logger -t AETHERIA-AUTOHOTSPOT -- "$*"; }

# Never disrupt a connection that already carries traffic, including SSH.
if nmcli -t -f DEVICE,STATE device status | grep -Eq '^(eth0|wlan0):connected$'; then
    log 'Network already connected; leaving connections unchanged.'
    exit 0
fi

while IFS=: read -r uuid type; do
    [ "$type" = '802-11-wireless' ] || continue
    name=$(nmcli -g connection.id connection show uuid "$uuid")
    [ "$name" != "$HOTSPOT" ] || continue
    if nmcli --wait 10 connection up uuid "$uuid"; then
        log 'Reconnected to a saved Wi-Fi profile.'
        exit 0
    fi
done < <(nmcli -t -f UUID,TYPE connection show)

log 'No saved network reachable; starting setup hotspot.'
nmcli --wait 15 connection up id "$HOTSPOT"
