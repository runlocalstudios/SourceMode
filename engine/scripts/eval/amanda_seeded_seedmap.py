import json, os, sys
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
sh.save(f'C:/Users/jerem/AppData/Local/Temp/claude/C--dev-sourcemode/568fc5a3-9efa-4a3c-9e3b-beb82c705119/scratchpad/seed_{want}.jpg', quality=85)
