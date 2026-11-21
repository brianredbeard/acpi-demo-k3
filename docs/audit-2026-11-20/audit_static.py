#!/usr/bin/env python3
"""Offline evidence extractor. Candidate equivalence is never a compliance PASS.
FDT parser preserves every property; ASL scanner supports this expanded static DSDT,
not arbitrary AML. Use ACPICA for namespace resolution and method execution.
"""
import argparse,csv,hashlib,json,re,struct
from pathlib import Path

def fdt(data):
    h=struct.unpack_from('>10I',data)
    if h[0]!=0xd00dfeed or h[1]>len(data): raise ValueError('invalid FDT header')
    off,strings=h[2],h[3]; stack=[]; nodes=[]
    def word(i): return struct.unpack_from('>I',data,i)[0]
    while off<h[2]+h[9]:
        tag=word(off);off+=4
        if tag==1:
            end=data.index(0,off);name=data[off:end].decode();off=(end+4)&~3
            path=(stack[-1]['path'].rstrip('/')+'/' if stack else '/')+name
            n={'path':path,'parent':stack[-1]['path'] if stack else None,'properties':{}}
            nodes.append(n);stack.append(n)
        elif tag==2: stack.pop()
        elif tag==3:
            size,nameoff=struct.unpack_from('>II',data,off);off+=8
            a=strings+nameoff;b=data.index(0,a);name=data[a:b].decode();val=data[off:off+size];off=(off+size+3)&~3
            prop={'hex':val.hex()}
            if val and val[-1]==0 and any(x>=32 for x in val) and all(x==0 or 32<=x<127 for x in val): prop['strings']=val[:-1].decode().split('\0')
            if len(val)%4==0: prop['cells']=list(struct.unpack('>'+str(len(val)//4)+'I',val))
            stack[-1]['properties'][name]=prop
        elif tag==4: pass
        elif tag==9: break
        else: raise ValueError('invalid token '+str(tag))
    bypath={n['path']:n for n in nodes}
    for n in nodes:
        p=n['properties']; parent=bypath.get(n['parent']); status=p.get('status',{}).get('strings',['okay'])[0]
        n['effective_status']=status if not parent or parent['effective_status']=='okay' else 'ancestor-disabled'
        n['reg_tuples']=[]
        if parent and 'reg' in p:
            pp=parent['properties'];ac=pp.get('#address-cells',{}).get('cells',[2])[0];sc=pp.get('#size-cells',{}).get('cells',[1])[0]
            cells=p['reg'].get('cells',[])
            if ac+sc and len(cells)%(ac+sc)==0:
                for i in range(0,len(cells),ac+sc):
                    def join(c):
                        v=0
                        for x in c:v=v*2**32+x
                        return v
                    n['reg_tuples'].append([join(cells[i:i+ac]),join(cells[i+ac:i+ac+sc])])
    return nodes

def asl_devices(text):
    text=re.sub(r'/\*.*?\*/|//[^\n]*','',text,flags=re.S);found=[]
    for m in re.finditer(r'\bDevice\s*\(\s*(\w+)\s*\)\s*\{',text):
        depth=1;i=m.end(); quoted=False
        while depth and i<len(text):
            c=text[i]
            if c=='"':quoted=not quoted
            if not quoted:depth+=(c=='{')-(c=='}')
            i+=1
        found.append({'name':m[1],'start':m.start(),'end':i,'body':text[m.end():i-1]})
    for d in found:
        parents=[x for x in found if x['start']<d['start']<x['end']]
        d['path']='\\_SB.'+'.'.join(x['name'] for x in parents+[d])
        body=d['body']
        # Exclude descendant resources from each parent's own resources.
        for x in sorted([x for x in found if d['start']<x['start']<d['end']],key=lambda x:x['start'],reverse=True):
            body=body.replace(text[x['start']:x['end']],'')
        d['body']=body
        def name(n):
            m=re.search(r'Name\s*\(\s*'+n+r'\s*,\s*([^\)]+)\)',body);return m[1].strip() if m else ''
        d['hid']=name('_HID');d['uid']=name('_UID');d['cca']=name('_CCA')
        d['mmio']=[]
        for m in re.finditer(r'QWordMemory\s*\((.*?)\)',body,re.S):
            args=[a.strip() for a in m[1].split(',')]
            try:d['mmio'].append({'base':int(args[7],0),'end':int(args[8],0),'length':int(args[10],0),'kind':args[0]})
            except (ValueError,IndexError):pass
        d['gsis']=[int(x.strip(),0) for m in re.finditer(r'Interrupt\s*\([^)]*\)\s*\{([^}]+)',body) for x in m[1].split(',') if x.strip()]
    for d in found:
        d.pop('start');d.pop('end')
    return found

def table(data):
    if len(data)<36:raise ValueError('table header truncated')
    sig=data[:4].decode('ascii');length=struct.unpack_from('<I',data,4)[0]
    if length<36 or length>len(data):raise ValueError('table length out of bounds')
    if sum(data[:length])&255:raise ValueError('checksum mismatch')
    if sig=='APIC':
        if length<44:raise ValueError('MADT fixed header truncated')
        off=44
        while off<length:
            if off+2>length:raise ValueError('MADT header truncated')
            size=data[off+1]
            if size<2 or off+size>length:raise ValueError('MADT subtable out of bounds')
            off+=size
    return {'signature':sig,'length':length,'revision':data[8],'sha256':hashlib.sha256(data).hexdigest()}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--evidence',type=Path,default=Path(__file__).parent/'evidence');args=ap.parse_args();out=args.evidence.parent
    devices=asl_devices((args.evidence/'canonical-dsdt.asl').read_text());(out/'acpi-inventory.json').write_text(json.dumps(devices,indent=2)+'\n')
    checks=[];rows=[]
    def add(kind,status,evidence):checks.append({'check':kind,'status':status,'evidence':evidence})
    ids={}
    for d in devices:
        key=(d['hid'],d['uid'])
        if d['hid'] and key in ids:add('duplicate HID/UID requires PRP0001 compatible review','BLOCKED',ids[key]+' '+d['path'])
        ids[key]=d['path']
        for r in d['mmio']:
            if r['end']-r['base']+1!=r['length']:add('MMIO length','FAIL',d['path'])
        for g in d['gsis']:
            if not 1<=g<=512:add('APLIC GSI source range','FAIL',d['path']+': '+str(g))
    for i,a in enumerate(devices):
        for b in devices[i+1:]:
            for x in a['mmio']:
                for y in b['mmio']:
                    if max(x['base'],y['base'])<=min(x['end'],y['end']):add('MMIO overlap requires ownership review','BLOCKED',a['path']+' '+b['path'])
    for path in sorted(args.evidence.glob('*.dtb')):
        nodes=fdt(path.read_bytes());(out/(path.stem+'-inventory.json')).write_text(json.dumps(nodes,indent=2)+'\n')
        for n in nodes:
            candidates=[d for d in devices if any(r['base']==a and size>0 for a,size in n['reg_tuples'] for r in d['mmio'])]
            special=''
            compat=';'.join(n['properties'].get('compatible',{}).get('strings',[]))
            if 'riscv,imsics' in compat:special='MADT IMSIC/RINTC (privilege domain must be checked)'
            if n['path'].startswith('/cpus/'):special='MADT/RHCT/PPTT/ACPI0007 candidate; CPU-map is topology'
            if n['path'].startswith('/memory'):special='UEFI memory map required'
            if n['path'].startswith('/reserved-memory'):special='UEFI reserved-memory evidence required'
            rep='; '.join(d['path'] for d in candidates) or special
            props=n['properties']
            for prop,value in props.items():
                rows.append([path.stem,n['path'],n['effective_status'],prop,json.dumps(value,sort_keys=True),rep,'DT source only; register/board validation outstanding','see clocks-drivers.md','NOT TESTED' if rep else 'BLOCKED','Candidate only; verify each dependency' if rep else 'No automatic mapping; exclusion or firmware ownership must be documented'])
        add(path.stem+' inventory','PASS',f'{len(nodes)} nodes; every raw property retained; bus-local reg not translated')
    represented={r[5] for r in rows}
    for d in devices:
        rows.append(['ACPI reverse',d['path'],'present (no _STA override)','namespace',d['hid']+' '+d['uid'],d['path'],'Requires DT/hardware reconciliation','see clocks-drivers.md','NOT TESTED','ACPI-only identity or candidate match; no proof from existence'])
    with (out/'equivalence.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['Baseline','Device','DT status','DT resource','Value','ACPI/UEFI representation','Hardware evidence','Driver','Status','Finding']);w.writerows(rows)
    for path in args.evidence.glob('*.aml'):
        try:add('ACPI binary header '+path.name,'PASS',table(path.read_bytes()))
        except ValueError as e:add('ACPI binary header '+path.name,'FAIL',str(e))
    add('ASL reference/clock/reset/power/child semantics','BLOCKED','Requires ACPICA load plus manual driver and hardware analysis; lexical matching is insufficient')
    (out/'static-results.json').write_text(json.dumps(checks,indent=2)+'\n')
    print(json.dumps({'devices':len(devices),'matrix_rows':len(rows),'checks':checks},indent=2))
if __name__=='__main__':main()
