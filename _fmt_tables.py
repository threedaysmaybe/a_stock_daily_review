import glob, re, os

for fn in sorted(glob.glob('pages/*.py')):
    with open(fn, 'r', encoding='utf-8') as f:
        c = f.read()
    
    name = os.path.basename(fn)
    changed = False
    
    if 'from utils.formatters import fmt_dataframe' not in c:
        c = c.replace('import config as cfg', 'import config as cfg\nfrom utils.formatters import fmt_dataframe')
        changed = True
    
    new_c = re.sub(r'st\.dataframe\((\w+)', r'st.dataframe(fmt_dataframe(\1)', c)
    if new_c != c:
        c = new_c
        changed = True
    
    if changed:
        with open(fn, 'w', encoding='utf-8') as f:
            f.write(c)
        print(f'OK: {name}')

print('done')
