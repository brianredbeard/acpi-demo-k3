#!/usr/bin/env python3
"""Reconstruct pinned tables/DT without modifying firmware trees. Requires cpp, dtc, iasl.
Usage: python3 reproduce.py --platform-repo ../edk2-platforms --scratch /tmp/new-audit
Output evidence path defaults to this report. A new scratch directory is required.
"""
import argparse,hashlib,json,subprocess
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--platform-repo',type=Path,required=True);ap.add_argument('--scratch',type=Path,required=True);ap.add_argument('--output',type=Path,default=Path(__file__).parent/'evidence');a=ap.parse_args()
root=Path(__file__).resolve().parents[2];a.scratch.mkdir(parents=True,exist_ok=False);a.output.mkdir(parents=True,exist_ok=True)
manifest=json.loads((root/'sources.lock.json').read_text());component=next(c for c in manifest['components'] if c['name']=='edk2-platforms');records=[]
def run(cmd,**kw):
 r=subprocess.run([str(x) for x in cmd],capture_output=True,**kw);records.append({'command':[str(x) for x in cmd],'returncode':r.returncode,'stderr':r.stderr.decode(errors='replace')});
 if r.returncode:raise RuntimeError(records[-1])
 return r.stdout
archive=run(['git','-C',a.platform_repo,'archive',component['revision']]);run(['tar','-x','-C',a.scratch],input=archive)
for patch in component['patches']:
 f=root/patch['file']
 if hashlib.sha256(f.read_bytes()).hexdigest()!=patch['sha256']:raise ValueError('patch hash mismatch: '+str(f))
 run(['git','apply','--unsafe-paths',f],cwd=a.scratch)
p=a.scratch/'Platform/Spacemit/K3'
for board in ['k3-pico-itx','k3-com260-ifx']:
 dts=run(['cpp','-nostdinc','-undef','-D__DTS__','-x','assembler-with-cpp','-I',p/'DeviceTree/Os/Sources/include',p/'DeviceTree/Os'/f'{board}.os.dts'])
 (a.output/f'{board}.preprocessed.dts').write_bytes(dts);run(['dtc','-I','dts','-O','dtb','-o',a.output/f'{board}.dtb'],input=dts)
for board in ['k3-pico-itx','k3-com260-ifx','k3-deepcomputing-fml13v05']:
 dts=run(['cpp','-nostdinc','-undef','-D__DTS__','-x','assembler-with-cpp','-I',p/'DeviceTree',p/'DeviceTree'/f'{board}.dts'])
 (a.output/f'firmware-{board}.preprocessed.dts').write_bytes(dts);run(['dtc','-I','dts','-O','dtb','-o',a.output/f'firmware-{board}.dtb'],input=dts)
for label,tree in [('canonical',p),('maintained',a.platform_repo/'Platform/Spacemit/K3')]:
 source=(tree/'AcpiTables/Dsdt/Dsdt.asl').read_text().replace('#include "K3PlatformAcpi.h"','#define EFI_ACPI_OEM_REVISION 1').replace('include ("Cpu.asl")',(tree/'AcpiTables/Dsdt/Cpu.asl').read_text())
 asl=run(['cpp','-P','-x','c','-'],input=source.encode());(a.output/f'{label}-dsdt.asl').write_bytes(asl)
 log=run(['iasl','-p',a.output/f'{label}-dsdt','-tc',a.output/f'{label}-dsdt.asl']);(a.output/f'iasl-{label}.log').write_bytes(log)
(a.output/'reproduction-commands.json').write_text(json.dumps(records,indent=2)+'\n')
print('Reconstructed evidence; maintained means supplied checkout, inspect its HEAD/status separately.')
