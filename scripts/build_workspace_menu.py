#!/usr/bin/env python3
"""Build a local material selector around the toolkit's unchanged report pages.

Usage: python3 scripts/build_workspace_menu.py WORKSPACE
No network, no client names or content stored in this script.
"""
import base64
import hashlib
import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bs


def render(ws):
    bs.load()
    bs.guard(ws)
    sources = {p.stem:json.loads(p.read_text()) for p in (ws/'records').glob('*.json')}
    pages = []
    for section, name, path in bs.section_files(ws):
        out = ws/'out'/section/(name+'.html')
        if not out.is_file():
            raise SystemExit(f'Build the workspace first: {out.name} is missing')
        title, kinds = name.replace('-', ' ').title(), set()
        if path.suffix=='.json':
            data=json.loads(path.read_text())
            title=data.get('meta',{}).get('title',title)
            def refs(value):
                if isinstance(value,dict):
                    if value.get('source') in sources:
                        kinds.add(sources[value['source']]['kind'])
                    for v in value.values(): refs(v)
                elif isinstance(value,list):
                    for v in value: refs(v)
            refs(data)
        pages.append({'section':section,'title':title,'path':f'{section}/{name}.html','kinds':sorted(kinds)})
    pages.append({'section':'data-received','title':'Original data received','path':'data-received.html','kinds':[]})
    css=(ROOT/'design-system/workspace/source-tokens.css').read_text()
    font=base64.b64encode((ROOT/'design-system/workspace/fonts/geist.woff2').read_bytes()).decode()
    catalog=json.dumps(pages,ensure_ascii=False).replace('<','\\u003c')
    labels={'process-map':'Process maps','data-received':'Original data received','document':'Reference documents','process-map-ai-opportunity':'AI opportunities','proposal':'Proposals'}
    options=''.join(f'<option value="{key}">{label}</option>' for key,label in labels.items() if any(p['section']==key for p in pages))
    stamp=hashlib.sha256((catalog+css+font+Path(__file__).read_text()).encode()).hexdigest()
    return TEMPLATE.replace('@@THEME@@',css).replace('@@FONT@@',font).replace('@@CATALOG@@',catalog).replace('@@STAMP@@',stamp).replace('@@MATERIALS@@',options)


TEMPLATE='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="workspace-menu-build" content="@@STAMP@@"><title>Source materials</title>
<style>@@THEME@@
@font-face{font-family:Geist;src:url(data:font/woff2;base64,@@FONT@@) format('woff2');font-display:swap}
*{box-sizing:border-box}body{margin:0;background:var(--bg-page);color:var(--fg-base);font:14px Geist,system-ui,sans-serif}
header{padding:18px 24px;border-bottom:1px solid var(--border-base);background:var(--bg-surface)}h1{margin:0 0 6px;font-size:24px}p{margin:0;color:var(--fg-muted)}
nav,.filters{display:flex;gap:12px;flex-wrap:wrap;align-items:end;margin-top:16px}label{display:flex;flex-direction:column;gap:5px;font-size:12px;font-weight:600}
select,input,a{font:inherit}select,input{height:36px;border:1px solid var(--border-base);border-radius:4px;padding:0 10px;color:var(--fg-base);background:var(--bg-surface)}
#page{min-width:280px;max-width:100%}input{width:220px}a{color:var(--fg-base);padding:9px 0}a:hover{color:var(--accent)}
:focus-visible{outline:2px solid var(--accent);outline-offset:3px}select:disabled{background:var(--bg-subtle)}
#state{font-size:12px;margin-top:10px}iframe{border:0;width:100%;height:calc(100vh - 225px);min-height:480px;background:var(--bg-surface)}
[hidden]{display:none!important}@media(max-width:680px){header{padding:16px}label,select,input,#page{width:100%;min-width:0}iframe{height:70vh}.filters{gap:10px}}
</style><body><header><h1>Source materials</h1><p>Choose a material type, then filter and open a view. Citations sit beside each process map.</p>
<nav aria-label="Materials"><label>Material type<select id="material">@@MATERIALS@@</select></label></nav>
<div class="filters"><label id="source-filter">Source type<select id="kind"><option value="all">All sources</option><option value="document">Documents and diagrams</option><option value="sheet">Workbooks</option></select></label>
<label>Find a view<input id="search" type="search" placeholder="Search titles"></label><label>View<select id="page"></select></label><a id="open" target="_blank" rel="noopener">Open full page</a></div>
<p id="state" role="status" aria-live="polite"></p></header><iframe id="viewer" title="Selected source material"></iframe>
<script type="application/json" id="catalog">@@CATALOG@@</script><script>
'use strict';
const pages=JSON.parse(document.getElementById('catalog').textContent), material=document.getElementById('material'), kind=document.getElementById('kind'), search=document.getElementById('search'), select=document.getElementById('page'), frame=document.getElementById('viewer'), state=document.getElementById('state'), openLink=document.getElementById('open');
for(const option of Array.from(material.options))if(!pages.some(p=>p.section===option.value))option.remove();
function show(){const page=pages.find(p=>p.path===select.value);if(!page){frame.hidden=true;openLink.hidden=true;state.textContent='No views match these filters.';return;}frame.hidden=false;openLink.hidden=false;frame.title=page.title;frame.src=page.path;openLink.href=page.path;state.textContent=select.options.length+' views · '+page.title;const hash=new URLSearchParams({material:material.value,kind:kind.value,page:page.path,q:search.value});history.replaceState(null,'','#'+hash);}
function filter(preferred){const old=preferred||select.value;const available=pages.filter(p=>p.section===material.value&&(kind.value==='all'||material.value!=='process-map'||p.kinds.includes(kind.value))&&p.title.toLowerCase().includes(search.value.toLowerCase()));select.replaceChildren(...available.map(p=>{const o=document.createElement('option');o.value=p.path;o.textContent=p.title;return o;}));select.disabled=!available.length;if(available.some(p=>p.path===old))select.value=old;document.getElementById('source-filter').hidden=material.value!=='process-map';show();}
material.addEventListener('change',()=>{search.value='';kind.value='all';filter();});kind.addEventListener('change',()=>filter());search.addEventListener('input',()=>filter());select.addEventListener('change',show);
const params=new URLSearchParams(location.hash.slice(1));if(Array.from(material.options).some(o=>o.value===params.get('material')))material.value=params.get('material');if(['all','document','sheet'].includes(params.get('kind')))kind.value=params.get('kind');search.value=params.get('q')||'';filter(params.get('page'));
</script></body></html>'''


if __name__=='__main__':
    if len(sys.argv)!=2: raise SystemExit(__doc__)
    ws=Path(sys.argv[1]).resolve()
    out=ws/'out/index.html'
    if not (ws/'out/data-received.html').is_file(): raise SystemExit('Run bs.py build first')
    first=render(ws)
    assert first==render(ws), 'menu build is not deterministic'
    out.write_text(first)
    print('Built local material menu:',out)
