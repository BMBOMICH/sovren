#!/bin/bash
cd /home/user/sovren-work
A=$1; B=$2; N=${3:-15}
rm -f /tmp/ma.txt /tmp/mb.txt
for i in $(seq 1 $N); do
  for pair in "a:$A" "b:$B"; do
    tag=${pair%%:*}; bin=${pair#*:}
    s=$(date +%s%N)
    ./$bin compilers/linux/compiler.sov -o /tmp/meas_out >/dev/null 2>&1
    e=$(date +%s%N)
    echo $(( (e-s)/1000000 )) >> /tmp/m$tag.txt
  done
done
python3 /tmp/mstat.py
