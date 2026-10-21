#!/bin/sh
# win.sh BUILDINGS WALLS : render 20 screen windows for the CC image
S="C:/Users/jarod/AppData/Local/Temp/claude/C--Users-jarod-AppData-Roaming-Claude-scratch-workspaces-f0a725c7-0a20-4b95-9a1a-a6a6dea5666b-97ba9717-5dea-4079-960d-1b84207c407d-scratch-2026-10-15-6523e4/b9aa4227-2025-48e8-b106-6957b35d5ea9/scratchpad"
cd /c/Users/jarod/Documents/clash-lab
for sy in 150 370 590 780; do for sx in 330 610 890 1170 1450; do
  t=$(.venv/Scripts/python -I -c "cx,top,a,b=926.8,8.0,15.896,12.0; u=($sx-cx)/a; v=($sy-top)/b; print(round((u+v)/2,1), round((v-u)/2,1))")
  .venv/Scripts/python -I "$S/ztw.py" "$S/digitize/img/cc102126.jpg" 926.8 8.0 15.896 12.0 ${2:--} ${1:--} "$S/digitize/w_${sy}_${sx}.jpg" $t 9.5 2.6
done; done
