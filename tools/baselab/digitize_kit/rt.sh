#!/bin/sh
# rt.sh: render 16 overlay tiles of current buildings (+pad hints) for the Blueprint image
S="C:/Users/jarod/AppData/Local/Temp/claude/C--Users-jarod-AppData-Roaming-Claude-scratch-workspaces-f0a725c7-0a20-4b95-9a1a-a6a6dea5666b-97ba9717-5dea-4079-960d-1b84207c407d-scratch-2026-10-15-6523e4/b9aa4227-2025-48e8-b106-6957b35d5ea9/scratchpad"
cat "$S/digitize/bp_b.txt" "$S/digitize/bp_pads.txt" > "$S/digitize/bp_comb.txt"
cd /c/Users/jarod/Documents/clash-lab && .venv/Scripts/python -I "$S/ovt.py" "$S/digitize/img/bp-TH16_ranked.jpg" 1361.7 -138.4 29.118 21.822 "$S/digitize/t" 4 4 ${1:--} "$S/digitize/bp_comb.txt"
