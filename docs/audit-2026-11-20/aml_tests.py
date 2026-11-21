#!/usr/bin/env python3
"""Execute safe _OSC tests in ACPICA simulation. No target hardware access.
Exit1 means a firmware regression case failed, not inability to launch ACPICA.
"""
import json,subprocess,sys
from pathlib import Path
root=Path(__file__).parent;e=root/'evidence';results=[]
cases={
 'unknown':('(00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00) 1 2 (00 00 00 00 FF FF FF FF)','04 00 00 00 FF FF FF FF','Unknown UUID preserves capability DWORD'),
 'valid':('(6E B0 11 08 27 4A F9 44 8D 60 3C BB C2 2E 7B 48) 1 2 (00 00 00 00 80 00 00 00)','00 00 00 00 80 00 00 00','Supported platform PCLPI request'),
 'masked':('(6E B0 11 08 27 4A F9 44 8D 60 3C BB C2 2E 7B 48) 1 2 (00 00 00 00 80 01 00 00)','10 00 00 00 80 00 00 00','Masked capability status bit'),
 'short':('(6E B0 11 08 27 4A F9 44 8D 60 3C BB C2 2E 7B 48) 1 1 (00 00 00 00)',None,'Robustness only: malformed input must not be confused with valid ABI')}
for name in ['canonical','maintained']:
 for case,(args,expected,description) in cases.items():
  cmd=['acpiexec','-b','evaluate _SB._OSC '+args,str(e/f'{name}-dsdt.aml')];r=subprocess.run(cmd,capture_output=True);text=(r.stdout+r.stderr).decode(errors='replace');(e/f'{name}-dsdt-osc-{case}.log').write_text(text)
  status=('PASS' if expected in text else 'FAIL') if expected else 'NOT APPLICABLE'
  results.append({'snapshot':name,'test':case,'status':status,'expected':expected,'description':description,'command':cmd,'process_exit':r.returncode,'buffer_limit':'AE_AML_BUFFER_LIMIT' in text})
(root/'aml-results.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2));sys.exit(any(x['status']=='FAIL' for x in results))
