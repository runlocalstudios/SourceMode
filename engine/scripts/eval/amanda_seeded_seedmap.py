import json, os, sys
from pathlib import Path

from PIL import Image, ImageDraw
m = json.load(open('outputs/lora-datasets/amanda_seeded_v2/manifest.json'))[:67]
s = {os.path.basename(r['file'].replace(chr(92), '/')): r for r in json.load(open('outputs/loragen_local/amanda/scores.json'))}
by = {}
for r in m:
    by.setdefault(s[os.path.basename(r['original'].replace(chr(92), '/'))]['hair'], []).append(r['file'][:-4])
for k, v in by.items(): print(k, len(v), ' '.join(x[4:] for x in v))
want = sys.argv[1]
files = by[want]
tw, th, cols = 260, 260, 7
rows = (len(files) + cols - 1) // cols
sh = Image.new('RGB', (cols * tw, rows * (th + 18)), 'white'); d = ImageDraw.Draw(sh)
for i, f in enumerate(files):
    im = Image.open(f'outputs/lora-datasets/amanda_seeded_v2/image_src/{f}.png'); w, h = im.size
    im = im.crop((0, 0, w, w)).resize((tw, th))
    x, y = (i % cols) * tw, (i // cols) * (th + 18); sh.paste(im, (x, y)); d.text((x + 3, y + th + 2), f, fill='black')
# outputs/qc/, not a session scratchpad: this wrote into a temp directory from a
# different Claude session again, so the sheet landed somewhere unfindable or the
# save threw.
out = Path(f'outputs/qc/seed_{want}.jpg')
out.parent.mkdir(parents=True, exist_ok=True)
sh.save(out, quality=85)
print('sheet:', out)
