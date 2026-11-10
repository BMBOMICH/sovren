import statistics as st
for tag,name in (('a','A'),('b','B')):
    v=[int(x) for x in open(f'/tmp/m{tag}.txt')]
    s=sorted(v)
    print(f"{name}: n={len(v)} min={s[0]} p25={s[len(s)//4]} med={st.median(s):.0f} mean={st.mean(s):.1f}")
