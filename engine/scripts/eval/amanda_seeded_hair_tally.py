import json, collections, re, os
m = json.load(open('outputs/lora-datasets/amanda_seeded_v2/manifest.json'))
s = {os.path.basename(r['file'].replace(chr(92), '/')): r for r in json.load(open('outputs/loragen_local/amanda/scores.json'))}
c = collections.Counter()
for r in m[:67]:
    cap = open(f"outputs/lora-datasets/amanda_seeded_v2/image_src/{r['file'][:-4]}.txt", encoding='utf-8').read()
    h = re.search(r"her hair[^,]*", cap)
    seed = s[os.path.basename(r['original'].replace(chr(92), '/'))]['hair']
    c[(seed, h.group(0) if h else None)] += 1
for k, v in sorted(c.items()): print(v, k)
