import unittest,struct,csv
from pathlib import Path
from audit_static import asl_devices,fdt,table
E=Path(__file__).parent/'evidence'
class AuditTests(unittest.TestCase):
 def test_aml_checksum_and_truncation(self):
  b=(E/'canonical-dsdt.aml').read_bytes();self.assertEqual(table(b)['signature'],'DSDT')
  bad=bytearray(b);bad[-1]^=1
  with self.assertRaisesRegex(ValueError,'checksum'):table(bad)
  with self.assertRaisesRegex(ValueError,'length'):table(b[:-1])
 def test_madt_zero_length_rejected(self):
  b=bytearray(46);b[:4]=b'APIC';struct.pack_into('<I',b,4,len(b));b[44]=25;b[45]=0;b[9]=(-sum(b))&255
  with self.assertRaisesRegex(ValueError,'subtable'):table(b)
 def test_madt_fixed_header_required(self):
  b=bytearray(36);b[:4]=b'APIC';struct.pack_into('<I',b,4,36);b[9]=(-sum(b))&255
  with self.assertRaisesRegex(ValueError,'fixed header'):table(b)
 def test_resources_not_inherited_from_child(self):
  ds=asl_devices((E/'canonical-dsdt.asl').read_text());d={x['name']:x for x in ds}
  self.assertEqual(d['COM0']['mmio'][0]['base'],0xd4017000)
  self.assertEqual(d['COM0']['mmio'][0]['length'],0x100)
  self.assertEqual(d['I2C2']['gsis'],[38]);self.assertEqual(d['EPR0']['gsis'],[])
  self.assertEqual(d['EPR0']['path'],'\\_SB.I2C2.EPR0')
  self.assertNotIn('UFS0',d)
 def test_maintained_delta(self):
  d={x['name']:x for x in asl_devices((E/'maintained-dsdt.asl').read_text())}
  self.assertEqual(d['UFS0']['gsis'],[135])
 def test_dependency_graph_has_real_provider_edges(self):
  with (E.parent/'dt-dependencies.csv').open() as f:rows=list(csv.DictReader(f))
  self.assertFalse(any(r['Provider']=='UNRESOLVED' for r in rows))
  self.assertFalse(any(r['Property'].startswith('pinctrl-single,') for r in rows))
  self.assertTrue(any(r['Board']=='k3-pico-itx' and r['Consumer']=='/soc/serial@d4017000' and r['Property']=='interrupts (effective parent)' and r['IDs']=='[42, 4]' for r in rows))
 def test_dt_keeps_disabled_nodes_and_properties(self):
  ns=fdt((E/'k3-pico-itx.dtb').read_bytes());self.assertEqual(len(ns),257)
  self.assertTrue(any(n['effective_status']=='disabled' for n in ns))
  self.assertTrue(any('clocks' in n['properties'] for n in ns))
  self.assertTrue(any('resets' in n['properties'] for n in ns))
if __name__=='__main__':unittest.main()
