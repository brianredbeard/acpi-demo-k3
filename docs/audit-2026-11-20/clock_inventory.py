import pathlib,re,csv,json,collections,argparse
parser=argparse.ArgumentParser(description="Inventory declared CCU/ClockDxe clocks and raw DT dependencies; no hardware access")
parser.add_argument("--esos", required=True, type=pathlib.Path)
parser.add_argument("--edk", required=True, type=pathlib.Path)
parser.add_argument("--dt", required=True, type=pathlib.Path)
parser.add_argument("--out", default=pathlib.Path(__file__).resolve().parent, type=pathlib.Path)
opt=parser.parse_args()
out=opt.out;out.mkdir(parents=True,exist_ok=True)
es=opt.esos; ed=opt.edk
f=es/'bsp/spacemit/drivers/clk/ccu-spacemit-k3.c';s=f.read_text();rows=[];edges=[]
arrays={m[1]:re.findall(r'"([^"]+)"',m[2]) for m in re.finditer(r'static const char \* const (\w+)\[\]\s*=\s*\{(.*?)\};',s,re.S)}
ids=['rproc_clk','twsi0_clk','twsi0_bus_clk','gpio_clk','gpio_bus_clk','sdh0_clk','sdh_axi_aclk','ufs_aclk','ufs_refclk','emac0_bus_clk','emac0_ref_clk','emac0_rgmii_tx_clk','usb2_bus_clk']
for m in re.finditer(r'static (SPACEMIT_CCU_\w+)\((.*?)\);',s,re.S):
 args=[v.strip() for v in m[2].split(',')]; name=args[1].strip('"');line=s.count('\n',0,m.start())+1
 parentarg=args[2];parents=re.findall(r'"([^"]+)"',parentarg) or arrays.get(parentarg,[])
 base=next((x for x in args if x.startswith('BASE_TYPE_')),'');idx=args.index(base) if base else -1
 reg=args[idx+1] if base else ''
 rows.append(['esos-clock',name,str(ids.index(name)) if name in ids else '',m[1],';'.join(parents),base,reg,'ESOS CCU; UEFI also programs AP gates' if name in ids else 'ESOS/internal; OS exposure unverified','published by RPMI' if name in ids else 'not published by RPMI','confirmed declaration','ESOS:'+str(f.relative_to(es))+':'+str(line),' '.join(m[2].split())])
 for p in parents:edges.append((p,name,'parent candidate' if len(parents)>1 else 'parent'))
rows.append(['rpmi-stub','rproc_clk','0','stub','', '', '', 'ESOS service','always reports 500 MHz; no hardware clock','confirmed','ESOS:bsp/spacemit/drivers/rpmi/k3/k3-os0_clk.c:209','not a physical clock'])
f=ed/'Silicon/Spacemit/K3/Drivers/ClockDxe/ClockDxe.c';s=f.read_text()
for m in re.finditer(r'^\s*"([A-Z0-9_]+)",\s*0x[0-9A-Fa-f]+,\s*(\d+),',s,re.M):
 end=s.find('\n  },',m.end());body=s[m.end():end]
 rows.append(['uefi-module',m[1],'','ClockDxe module','','',';'.join(dict.fromkeys(re.findall(r'K3_\w+',body))),'UEFI','table entry; enable depends on driver/SKU','confirmed declaration','EDK:'+str(f.relative_to(ed))+':'+str(s.count('\n',0,m.start())+1),'config rows='+m[2]+' '+ ' '.join(body.split())])
# Every raw clock/reset/PHY/power/regulator supply binding in the relevant local DT files.
base=opt.dt
for fn in ['k3.dtsi','k3-pico-itx.dts','k3-display.dtsi']:
 f=base/fn;s=f.read_text()
 for m in re.finditer(r'^\s*((?:clocks|resets|phys|power-domains|[\w-]+-supply))\s*=\s*(.*?);',s,re.M|re.S):
  before=s[:m.start()];contexts=re.findall(r'^\s*([^\n{};]+)\s*\{',before,re.M);ctx=contexts[-1].strip() if contexts else '?'
  # lexical nearest opener is a locator, not resolved node path; source line authoritative.
  rows.append(['dt-dependency',ctx,'',m[1],'','','','DT provider binding','ACPI equivalence requires explicit implementation','confirmed raw declaration','DT:'+fn+':'+str(s.count('\n',0,m.start())+1),' '.join(m[2].split())])
with (out/'clock-dependencies.csv').open('w') as h:
 w=csv.writer(h);w.writerow(['layer','name_or_nearest_lexical_node','rpmi_id','kind','parents','register_bank','register','owner','acpi_status','confidence','evidence','raw_definition']);w.writerows(rows)
with (out/'clocks.dot').open('w') as h:
 h.write('digraph clocks {\n rankdir=LR;\n label="Pinned ESOS CCU: declared parent candidates (not live mux state)";\n')
 for row in rows:
  if row[0]=='esos-clock': h.write(' '+json.dumps(row[1])+' [shape=box'+(',style=filled,fillcolor=lightblue' if row[2] else '')+'];\n')
 for a,b,label in edges:h.write(' '+json.dumps(a)+' -> '+json.dumps(b)+' [label='+json.dumps(label)+'];\n')
 h.write('}\n')
print(collections.Counter(r[0] for r in rows));print('edges',len(edges));print('macro count',len(re.findall(r'static SPACEMIT_CCU_', (es/'bsp/spacemit/drivers/clk/ccu-spacemit-k3.c').read_text())))
