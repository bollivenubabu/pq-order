import json

all_rows = []
for fname in ['schedule_IV.json', 'schedule_V.json', 'schedule_VI.json', 'schedule_VII.json']:
    with open(fname, encoding='utf-8') as f:
        all_rows.extend(json.load(f))

# Written as executable JS (not fetched as JSON) so the tool works when index.html is opened
# directly via file:// with no server: a <script src> tag loads local files fine in all
# browsers, whereas fetch()/XHR of a local file is blocked by CORS in Chrome/Edge, and a
# <script src> pointing at a file actually served/typed as application/json gets silently
# blocked by MIME-type enforcement -- hence the .js extension and this JS-literal wrapper.
with open('data.js', 'w', encoding='utf-8') as f:
    f.write('var PQ_DATA = ')
    json.dump(all_rows, f, ensure_ascii=False, separators=(',', ':'))
    f.write(';')

print(f'Wrote data.js: {len(all_rows)} rows')
