"""
cam_merge.py — merge per-group RE/cam_map/<A-H>.json (SE-first camera mapping) into
RE/cam_map/cam_se_dx9_map.json and check consistency. Plain Python:
    python RE/scripts/cam_merge.py <se_cam_features.json>

Checks:
  * every SE function in the feature dump appears in exactly one group's `methods`
  * DX9 functions claimed (high/medium) by >1 SE method — legit for ICF folds, otherwise a conflict
  * address fields are hex strings or null (the dumps are machine input)
"""
import json, glob, os, re, sys, collections

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'cam_map')
HEX = re.compile(r'^0x[0-9A-Fa-f]+$')
groups = {os.path.basename(p)[:-5]: json.load(open(p, encoding='utf-8'))
          for p in sorted(glob.glob(os.path.join(ROOT, '[A-H].json')))}

rows, by_se, by_dx = [], collections.defaultdict(list), collections.defaultdict(list)
bad_addr = []
for g, d in groups.items():
    for m in d.get('methods', []):
        m = dict(m, group=g)
        rows.append(m)
        for k in ('se_ea', 'dx9_ea'):
            if m.get(k) is not None and not HEX.match(str(m[k])):
                bad_addr.append((g, k, m[k]))
        if m.get('se_ea'):
            by_se[m['se_ea'].lower()].append(g)
        if m.get('dx9_ea') and m.get('confidence') in ('high', 'medium'):
            by_dx[m['dx9_ea'].lower()].append((g, m['se_name'], m['confidence']))

missing_se = []
if len(sys.argv) > 1:
    se = json.load(open(sys.argv[1]))['funcs']
    missing_se = sorted(set(k.lower() for k in se) - set(by_se))
dup_se = {k: v for k, v in by_se.items() if len(v) > 1}
multi_dx = {k: v for k, v in by_dx.items() if len(v) > 1}

stats = collections.Counter()
for r in rows:
    stats[r.get('confidence') or 'none'] += 1
    stats['act_' + (r.get('action') or 'none')] += 1
per_group = {g: dict(collections.Counter(m.get('confidence') or 'none' for m in d.get('methods', [])))
             for g, d in groups.items()}

out = {'groups': sorted(groups), 'classes': {}, 'methods': rows,
       'dx9_only': [dict(x, group=g) for g, d in groups.items() for x in d.get('dx9_only', [])],
       'notes': {g: d.get('notes', '') for g, d in groups.items()},
       'checks': {'missing_se': missing_se, 'dup_se': dup_se, 'multi_se_per_dx9': multi_dx,
                  'bad_addr': bad_addr}}
for g, d in groups.items():
    for c, v in d.get('classes', {}).items():
        out['classes'].setdefault(c, []).append(dict(v, group=g))
json.dump(out, open(os.path.join(ROOT, 'cam_se_dx9_map.json'), 'w', encoding='utf-8'), indent=1)

print('groups', sorted(groups), 'rows', len(rows))
print('totals', dict(stats))
for g, c in per_group.items():
    print(' ', g, c)
print('missing_se', len(missing_se), 'dup_se', len(dup_se), 'multi_se_per_dx9', len(multi_dx), 'bad_addr', len(bad_addr))
for k, v in list(multi_dx.items())[:60]:
    print('  MULTI', k, v)
for b in bad_addr[:20]:
    print('  BADADDR', b)
