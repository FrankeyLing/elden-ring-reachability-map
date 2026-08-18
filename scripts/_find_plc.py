import json

fmg = json.load(open('data/v1/entities/official-fmg-bilingual-index.json', encoding='utf-8'))
def fmg_base(name):
    return name.replace('\\', '/').split('/')[-1]

for probe_zh in ['望影露台', '影を仰ぐ', '隐匿之地', '幽影城', '物种保藏库', '墓穴']:
    hits = [r for r in fmg['records'] if probe_zh in r['text'] and fmg_base(r['fmg']) == 'PlaceName.fmg']
    print("'%s': %s" % (probe_zh, [(r['language'], r['id'], r['text'][:30]) for r in hits[:4]]))
for probe_en in ['Scaduview', 'Hinterland', 'Shadow Keep', 'Specimen Storehouse']:
    hits = [r for r in fmg['records'] if probe_en.lower() in r['text'].lower() and fmg_base(r['fmg']) == 'PlaceName.fmg']
    print("'%s': %s" % (probe_en, [(r['language'], r['id'], r['text'][:30]) for r in hits[:4]]))
