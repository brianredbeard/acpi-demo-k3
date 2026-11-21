#!/usr/bin/env python3
"""Resolve known DT phandle-array dependencies; preserve IDs and unresolved edges."""
import csv,json
from pathlib import Path
from audit_static import fdt,asl_devices
ROOT=Path(__file__).parent
rows=[]
for path in sorted((ROOT/'evidence').glob('*.dtb')):
 nodes=fdt(path.read_bytes());by={n['path']:n for n in nodes};ph={n['properties']['phandle']['cells'][0]:n for n in nodes if 'phandle' in n['properties']}
 for n in nodes:
  # Plain interrupts inherit interrupt-parent through the DT ancestry.
  if 'interrupts' in n['properties']:
   cur=n;handle=None
   while cur is not None:
    if 'interrupt-parent' in cur['properties']:
     handle=cur['properties']['interrupt-parent'].get('cells',[None])[0];break
    cur=by.get(cur['parent'])
   target=ph.get(handle)
   vals=n['properties']['interrupts'].get('cells',[])
   if target:
    width=target['properties'].get('#interrupt-cells',{}).get('cells',[0])[0]
    if width and len(vals)%width==0:
     for off in range(0,len(vals),width):rows.append([path.stem,n['path'],'interrupts (effective parent)',hex(handle),target['path'],json.dumps(vals[off:off+width]),n['effective_status'],'NOT TESTED'])
    else:rows.append([path.stem,n['path'],'interrupts (malformed cells)',str(handle),target['path'],json.dumps(vals),n['effective_status'],'FAIL'])
   else:rows.append([path.stem,n['path'],'interrupts (effective parent)',str(handle),'UNRESOLVED',json.dumps(vals),n['effective_status'],'BLOCKED'])
  for key,value in n['properties'].items():
   count={'clocks':'#clock-cells','assigned-clocks':'#clock-cells','assigned-clock-parents':'#clock-cells','resets':'#reset-cells','power-domains':'#power-domain-cells','phys':'#phy-cells','dmas':'#dma-cells','iommus':'#iommu-cells','interrupts-extended':'#interrupt-cells','pwms':'#pwm-cells','msi-parent':'#msi-cells'}.get(key)
   if key.endswith('-gpios') or key=='gpios':count='#gpio-cells'
   single=key.endswith('-supply') or key in ['interrupt-parent','phy-handle','remote-endpoint'] or key.startswith('pinctrl-') and key[len('pinctrl-'):].isdigit()
   if not count and not single:continue
   cells=value.get('cells',[]);i=0
   while i<len(cells):
    handle=cells[i];i+=1
    if handle==0:continue
    target=ph.get(handle)
    if target is None:
     rows.append([path.stem,n['path'],key,hex(handle),'UNRESOLVED','',n['effective_status'],'BLOCKED']);break
    cnt=0 if single else target['properties'].get(count,{}).get('cells',[0])[0]
    args=cells[i:i+cnt];i+=cnt
    rows.append([path.stem,n['path'],key,hex(handle),target['path'],json.dumps(args),n['effective_status'],'NOT TESTED' if len(args)==cnt else 'FAIL'])
with (ROOT/'dt-dependencies.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['Board','Consumer','Property','Phandle','Provider','IDs','Consumer status','Runtime validation']);w.writerows(rows)
with (ROOT/'dt-dependencies.dot').open('w') as f:
 f.write('digraph DT { rankdir=LR;\n')
 for board,consumer,prop,_,provider,ids,status,_ in rows:
  f.write(json.dumps(board+':'+provider)+' -> '+json.dumps(board+':'+consumer)+' [label='+json.dumps(prop+ids+' '+status)+'];\n')
 f.write('}\n')
maint=asl_devices((ROOT/'evidence/maintained-dsdt.asl').read_text());(ROOT/'maintained-acpi-inventory.json').write_text(json.dumps(maint,indent=2)+'\n')
with (ROOT/'devices.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['Board','Device','Compatible','Status','Reg (bus-local)','ACPI candidate (locked)','ACPI candidate (maintained)','Dependencies','Disposition'])
 locked=asl_devices((ROOT/'evidence/canonical-dsdt.asl').read_text())
 for path in sorted((ROOT/'evidence').glob('*.dtb')):
  for n in fdt(path.read_bytes()):
   def match(ds):return ';'.join(d['path'] for d in ds if any(r['base']==a and size for a,size in n['reg_tuples'] for r in d['mmio']))
   p=n['properties']; deps=[r[2]+'->'+r[4]+r[5] for r in rows if r[0]==path.stem and r[1]==n['path']]
   w.writerow([path.stem,n['path'],';'.join(p.get('compatible',{}).get('strings',[])),n['effective_status'],json.dumps(n['reg_tuples']),match(locked),match(maint),';'.join(deps),'Candidate only; manual disposition needed' if match(maint) else 'Unmapped: firmware-owned/excluded/missing not yet established'])
print(f'{len(rows)} dependency edges; unresolved: {sum(r[4]=="UNRESOLVED" for r in rows)}')
