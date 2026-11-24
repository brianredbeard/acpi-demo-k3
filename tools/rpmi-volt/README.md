# rpmi-volt — the RPMI voltage qualification client

Binds the RQTS DSDT device (`k3,rpmi-qual-test`, PRP0001:07 —
the mboxes channel 7 = the voltage service group) and exposes
runtime rail control:

```
D=/sys/devices/platform/PRP0001:07
echo <domain> > $D/domain     # 0-23 (fixed 0-5, dynamic 6-23)
echo 1     > $D/enable        # SET_CONFIG enable/disable
echo 3300000 > $D/level       # SET_LEVEL in uV
cat $D/query                  # name/config/level/attrs
```

Domain map (live-enumerated 2026-11-24; fixed 0-5 = pvin,
pwr_ext, p1v8, p3v3, pwr_x100, pwr_a100): 6=adcdc1, 7=dcdc3,
8=dcdc4, 9=dcdc5, 10=dcdc6, 11=aldo1, 12=aldo2, **13=aldo3**,
14=aldo4, 15=dldo1 ... 21=dldo7, 22=adcdc2.

Build on the rig against the kernel tree:

```
make -C /home/redhat/kernel-dev/tree M=$PWD modules
```

History: v5 (module params) leaked the mbox channel — the
missing .remove kept the channel bound after rmmod (EBUSY on
reload). v6 adds the sysfs interface + the remove.

NOT part of the kernel spec: a diagnostic client, not shipped
kernel code.
