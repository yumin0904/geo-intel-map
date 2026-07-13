import sqlite3, sys, re, pathlib
sys.path.insert(0, '.')

# yaml 없이 파싱 (환경에 pyyaml 없음)
txt = pathlib.Path('config/importance_rules.yaml').read_text()
def iso_set(block):
    m = re.search(rf'^{block}:\s*\n(.*?)(?=\n\w|\Z)', txt, re.S | re.M)
    return set(re.findall(r'\b([A-Z]{3})\b', m.group(1))) if m else set()

STRAT = iso_set('strategic_theatre')
SECTOR = iso_set('sector_link')
FAMW = {'gdelt_geo_material_conflict_pol': 1.00, 'event_archive_region': 1.00,
        'gdelt_geo_protest': 0.45}

def importance(iso, family):
    s = 0.45 if iso in STRAT else 0.0
    s += 0.35 if iso in SECTOR else 0.0
    s += 0.20 * FAMW.get(family, 0.5)
    return round(min(s, 1.0), 2)

c = sqlite3.connect('db/intel.db')
rows = c.execute("select series_key, bucket, family, delta_pct, p_value from observation_history").fetchall()
scored = [(importance(k, f), k, b, f, d, p) for k, b, f, d, p in rows]

# ── 정답지: 우리가 아는 사건들 ──
GOLD_IMPORTANT = [('UKR','2022-02'),('MMR','2021-02'),('IRN','2022-09'),('ISR','2023-10'),
                  ('PRK','2017-09'),('TWN','2022-08'),('IRQ','2019-10'),('YEM','2015-03')]
GOLD_IRRELEVANT = [('CAN','2022-02'),('NZL','2022-02'),('CHL','2019-10'),('NIC','2018-04'),
                   ('GTM','2020-11'),('BHR','2016-01')]

def look(k, b):
    hits = [s for s in scored if s[1] == k and s[2] == b]
    return max(hits)[0] if hits else None

print("=== 정답지 채점 ===")
print("\n[중요해야 할 것]")
for k, b in GOLD_IMPORTANT:
    v = look(k, b)
    print(f"  {k} {b}  importance={v if v is not None else '(관찰 없음)'}")
print("\n[무관해야 할 것]")
for k, b in GOLD_IRRELEVANT:
    v = look(k, b)
    print(f"  {k} {b}  importance={v if v is not None else '(관찰 없음)'}")

print("\n=== 분포 ===")
from collections import Counter
cnt = Counter(s[0] for s in scored)
for v in sorted(cnt, reverse=True):
    print(f"  importance {v}: {cnt[v]:>4}건")
hi = [s for s in scored if s[0] >= 0.7]
print(f"\n  ≥0.7: {len(hi)}건 / {len(scored)}건 ({len(hi)/len(scored)*100:.0f}%)")
