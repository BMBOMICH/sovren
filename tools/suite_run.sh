#!/bin/bash
# one-press suite runner. always leaves ONE clean run and a DONE file.
cd /home/user/sovren
chmod +x sovren sovren-dbg 2>/dev/null
chmod +x compilers/linux/compiler compilers/windows/compiler compilers/apple/macos/compiler compilers/apple/ios/compiler compilers/android/compiler compilers/android/shared-object/compiler 2>/dev/null
for p in $(ps aux | grep -E "/tmp/battery$" | grep -v grep | awk '{print $2}'); do kill -9 $p 2>/dev/null; done
sleep 1
rm -f /tmp/battery.done /tmp/battery_ts.log
./sovren tests/fast.sov -o /tmp/battery 2>/tmp/battery.err || { echo "BUILD-FAIL $(cat /tmp/battery.err)" > /tmp/battery.done; exit 1; }
( setsid nohup /tmp/battery > /tmp/battery_ts.log 2>&1 && date +"%k:%M:%S FINISHED" >> /tmp/battery_ts.log && tail -4 /tmp/battery_ts.log > /tmp/battery.done & )
echo "single run live; results in /tmp/battery.done when green"
# unsafe ratchet: raw-access count must never exceed baseline
if [ -f /home/user/sovrenos/tools/unsafe_baseline.txt ]; then
    base=$(cat /home/user/sovrenos/tools/unsafe_baseline.txt)
    cur=$(python3 /home/user/sovrenos/tools/unsafe_scan.py 2>/dev/null | grep -m1 "Total raw-access" | grep -oE "[0-9]+")
    if [ -n "$cur" ] && [ "$cur" -gt "$base" ]; then
        echo "RATCHET-FAIL: unsafe sites grew $base -> $cur" >&2
        echo "ratchet fail $base -> $cur" > /tmp/battery.done
        exit 1
    fi
    echo "ratchet ok ($cur <= $base)"
fi

