DefinitionBlock ("DsdtTable.aml", "DSDT", 2, "SPMT  ", "K3", 1) {
Scope (_SB) {
  Device (CL00) {
    Name (_HID, "ACPI0010")
    Name (_UID, 0x02000000)
    Device (CPU0) { Name (_HID, "ACPI0007") Name (_UID, 0) }
    Device (CPU1) { Name (_HID, "ACPI0007") Name (_UID, 1) }
    Device (CPU2) { Name (_HID, "ACPI0007") Name (_UID, 2) }
    Device (CPU3) { Name (_HID, "ACPI0007") Name (_UID, 3) }
  }
  Device (CL01) {
    Name (_HID, "ACPI0010")
    Name (_UID, 0x02000001)
    Device (CPU4) { Name (_HID, "ACPI0007") Name (_UID, 4) }
    Device (CPU5) { Name (_HID, "ACPI0007") Name (_UID, 5) }
    Device (CPU6) { Name (_HID, "ACPI0007") Name (_UID, 6) }
    Device (CPU7) { Name (_HID, "ACPI0007") Name (_UID, 7) }
  }
}
  Scope (_SB) {
    Name (SBP, 0)
    Method (_OSC, 4, NotSerialized)
    {
      CreateDWordField (Arg3, 0, CDW1)
      CreateDWordField (Arg3, 4, CDW2)
      If (LNotEqual (Arg1, 1))
      {
        Or (CDW1, 0x08, CDW1)
        Return (Arg3)
      }
      If (LEqual (Arg0, ToUUID ("0811B06E-4A27-44F9-8D60-3CBBC22E7B48")))
      {
        And (CDW2, 0x80, SBP)
        Store (SBP, CDW2)
        Store (0, CDW1)
        Return (Arg3)
      }
      Or (CDW1, 0x04, CDW1)
      And (CDW2, 0, CDW2)
      Return (Arg3)
    }
    Device (IC00)
    {
      Name (_HID, "RSCV0002")
      Name (_UID, Zero)
      Name (_GSB, Zero)
      Name (_CRS, ResourceTemplate ()
      {
        QWordMemory (
          ResourceConsumer, PosDecode, MinFixed, MaxFixed,
          NonCacheable, ReadWrite,
          0x0, 0xE0804000, 0xE0807FFF, 0x0, 0x4000
        )
      })
    }
    Device (COM0)
    {
      Name (_HID, "RSCV0003")
      Name (_UID, Zero)
      Name (_CRS, ResourceTemplate ()
      {
        QWordMemory (
          ResourceConsumer, PosDecode, MinFixed, MaxFixed,
          NonCacheable, ReadWrite,
          0x0, 0xD4017000, 0xD40170FF, 0x0, 0x100
        )
        Interrupt (ResourceConsumer, Level, ActiveHigh, Exclusive) { 42 }
      })
      Name (_DSD, Package () {
        ToUUID ("daffd814-6eba-4d8c-8a91-bc9bbf4aa301"),
        Package () {
          Package (2) { "clock-frequency", 14745600 },
          Package (2) { "reg-shift", 2 },
          Package (2) { "reg-io-width", 4 },
          Package () { "compatible", Package () { "spacemit,k3-uart", "intel,xscale-uart" } }
        }
      })
    }
    Device (ETH0)
    {
      Name (_HID, "PRP0001")
      Name (_UID, 0x40)
      Name (_CCA, 0)
      Name (_CRS, ResourceTemplate ()
      {
        QWordMemory (
          ResourceConsumer, PosDecode, MinFixed, MaxFixed,
          NonCacheable, ReadWrite,
          0x0, 0xCAC80000, 0xCAC81FFF, 0x0, 0x2000
        )
        Interrupt (ResourceConsumer, Level, ActiveHigh, Exclusive) { 131 }
      })
      Name (_DSD, Package () {
        ToUUID ("daffd814-6eba-4d8c-8a91-bc9bbf4aa301"),
        Package () {
          Package () { "compatible", Package () { "spacemit,k3-dwmac", "snps,dwmac-5.40a" } },
          Package () { "phy-mode", "rgmii-id" },
          Package () { "snps,clk-csr", 5 },
          Package () { "tx-internal-delay-ps", 0 },
          Package () { "rx-internal-delay-ps", 0 },
          Package () { "spacemit,apmu-ctrl-reg", 0xD4282BE4 },
          Package () { "spacemit,apmu-dline-reg", 0xD4282BE8 },
          Package () { "snps,multicast-filter-bins", 64 },
          Package () { "snps,perfect-filter-entries", 32 },
          Package () { "snps,txpbl", 8 },
          Package () { "snps,rxpbl", 8 },
          Package () { "snps,aal", 1 },
          Package () { "snps,force_sf_dma_mode", 1 },
          Package () { "rx-fifo-depth", 8192 },
          Package () { "tx-fifo-depth", 8192 }
        }
      })
    }
    Device (USB2)
    {
      Name (_HID, "808622B7")
      Name (_UID, Zero)
      Name (_CCA, 0)
      Name (_CRS, ResourceTemplate ()
      {
        QWordMemory (
          ResourceConsumer, PosDecode, MinFixed, MaxFixed,
          NonCacheable, ReadWrite,
          0x0, 0xC0A00000, 0xC0A0FFFF, 0x0, 0x10000
        )
        Interrupt (ResourceConsumer, Level, ActiveHigh, Exclusive) { 105 }
      })
      Name (_DSD, Package () {
        ToUUID ("daffd814-6eba-4d8c-8a91-bc9bbf4aa301"),
        Package () {
          Package () { "dr_mode", "host" },
          Package () { "phy_type", "utmi" },
          Package () { "snps,hsphy_interface", "utmi" },
          Package () { "snps,dis_enblslpm_quirk", 1 },
          Package () { "snps,dis_u2_susphy_quirk", 1 },
          Package () { "snps,dis_u3_susphy_quirk", 1 },
          Package () { "snps,dis-del-phy-power-chg-quirk", 1 },
          Package () { "snps,dis-tx-ipgap-linecheck-quirk", 1 },
          Package () { "snps,parkmode-disable-ss-quirk", 1 },
          Package () { "usb-role-switch", 1 },
          Package () { "role-switch-default-mode", "host" },
          Package () { "maximum-speed", "high-speed" }
        }
      })
    }
    Device (PCI0)
    {
      Name (_HID, "PNP0A08")
      Name (_CID, "PNP0A03")
      Name (_UID, 0)
      Name (_SEG, 0)
      Name (_BBN, 0x00)
      Name (_CCA, 0)
      Name (_CRS, ResourceTemplate () {
        WordBusNumber (
          ResourceProducer, MinFixed, MaxFixed, PosDecode,
          0x0,
          0x00,
          0xff,
          0x00,
          0x100
        )
        QWordMemory (
          ResourceProducer, PosDecode, MinFixed, MaxFixed,
          NonCacheable, ReadWrite,
          0x00000000,
          0x0010000000,
          0x007FFFFFFF,
          0x1100000000,
          0x0070000000
        )
        QWordMemory (
          ResourceProducer, PosDecode, MinFixed, MaxFixed,
          Prefetchable, ReadWrite,
          0x0,
          0x0000001800000000,
          0x00000018FFFFFFFF,
          0x0000000000000000,
          0x0000000100000000
        )
      })
      Name (SUPP, 0)
      Name (CTRL, 0)
      Method (_OSC, 4, NotSerialized)
      {
        CreateDWordField (Arg3, 0, CDW1)
        If (Arg0 == ToUUID ("33DB4D5B-1FF7-401C-9657-7441C03DD766"))
        {
          CreateDWordField (Arg3, 4, CDW2)
          CreateDWordField (Arg3, 8, CDW3)
          SUPP = CDW2 & 0x10
          CTRL = CDW3 & 0x10
          If (Arg1 != 1) { CDW1 |= 0x08 }
          If (CDW3 != CTRL) { CDW1 |= 0x10 }
          CDW3 = CTRL
          Return (Arg3)
        }
        CDW1 |= 0x04
        Return (Arg3)
      }
      Device (RES0)
      {
        Name (_HID, "PNP0C02")
        Name (_CRS, ResourceTemplate () {
          QWordMemory (
            ResourceProducer, PosDecode, MinFixed, MaxFixed,
            NonCacheable, ReadWrite,
            0x0,
            0x0000001100000000,
            0x000000110FFFFFFF,
            0x0000000000000000,
            0x0000000010000000
          )
        })
      }
      Device (DBI0)
      {
    Name (_HID, "AMZN0001")
        Name (_CID, "PNP0C02")
        Name (_UID, 0)
        Name (_CRS, ResourceTemplate () {
          QWordMemory (
            ResourceConsumer, PosDecode, MinFixed, MaxFixed,
            NonCacheable, ReadWrite,
            0x0,
            0x80000000,
            0x80000FFF,
            0x00000000,
            0x1000
          )
        })
      }
    }
    Device (GPIO)
    {
      Name (_HID, "PRP0001")
      Name (_UID, 0x50)
      Name (_CCA, 0)
      Name (_CRS, ResourceTemplate ()
      {
        QWordMemory (
          ResourceConsumer, PosDecode, MinFixed, MaxFixed,
          NonCacheable, ReadWrite,
          0x0, 0xD4019000, 0xD40190FF, 0x0, 0x100
        )
        Interrupt (ResourceConsumer, Level, ActiveHigh, Shared) { 58 }
      })
      Name (_DSD, Package () {
        ToUUID ("daffd814-6eba-4d8c-8a91-bc9bbf4aa301"),
        Package () {
          Package () { "compatible", "spacemit,k3-gpio" },
        }
      })
    }
    Device (I2C2)
    {
      Name (_HID, "PRP0001")
      Name (_UID, 0x60)
      Name (_CCA, 0)
      Name (_CRS, ResourceTemplate ()
      {
        QWordMemory (
          ResourceConsumer, PosDecode, MinFixed, MaxFixed,
          NonCacheable, ReadWrite,
          0x0, 0xD4012000, 0xD4012037, 0x0, 0x38
        )
        Interrupt (ResourceConsumer, Level, ActiveHigh, Exclusive) { 38 }
      })
      Name (_DSD, Package () {
        ToUUID ("daffd814-6eba-4d8c-8a91-bc9bbf4aa301"),
        Package () {
          Package () { "compatible", "spacemit,k1-i2c" },
          Package () { "clock-frequency", 100000 },
          Package () { "spacemit,func-clock-rate", 31500000 },
        }
      })
      Device (EPR0)
      {
        Name (_HID, "PRP0001")
        Name (_UID, 0)
        Name (_CRS, ResourceTemplate ()
        {
          I2cSerialBus (0x50, ControllerInitiated, 100000,
            AddressingMode7Bit, "\\_SB.I2C2")
        })
        Name (_DSD, Package () {
          ToUUID ("daffd814-6eba-4d8c-8a91-bc9bbf4aa301"),
          Package () {
            Package () { "compatible", "atmel,24c02" },
            Package () { "pagesize", 8 },
            Package () { "read-only", 1 },
          }
        })
      }
    }
    Device (ESPI)
    {
      Name (_HID, "PRP0001")
      Name (_UID, 0x71)
      Name (_CCA, 1)
      Name (_CRS, ResourceTemplate ()
      {
        QWordMemory (
          ResourceConsumer, PosDecode, MinFixed, MaxFixed,
          NonCacheable, ReadWrite,
          0x0, 0xCAC8C000, 0xCAC8CFFF, 0x0, 0x1000
        )
      })
      Name (_DSD, Package () {
        ToUUID ("daffd814-6eba-4d8c-8a91-bc9bbf4aa301"),
        Package () {
          Package () { "compatible", "spacemit,k3-espi" },
          Package () { "operating-frequency", 20 },
          Package () { "watchdog-timeout", 0xffff },
          Package () { "pr-mem-base0", 0x84000000 },
          Package () { "pr-mem-base1", 0xcac8c000 },
          Package () { "io-mode", "single" },
          Package () { "alert-mode", "io1" },
          Package () { "alert-type", "open-drain" },
          Package () { "crc-enable", 1 },
          Package () { "auto-gating-enable", 1 },
          Package () { "peripheral-channel-enable", 1 },
          Package () { "vwire-channel-enable", 1 },
          Package () { "oob-channel-enable", 1 },
          Package () { "flash-channel-enable", 1 }
        }
      })
      Device (EC0)
      {
        Name (_HID, "PRP0001")
        Name (_UID, 0)
        Name (_CCA, 1)
        Name (_CRS, ResourceTemplate ()
        {
          QWordMemory (
            ResourceConsumer, PosDecode, MinFixed, MaxFixed,
            NonCacheable, ReadWrite,
            0x0, 0x84000000, 0x84000FFF, 0x0, 0x1000
          )
          GpioInt (Edge, ActiveHigh, Exclusive, PullUp, 0x0000,
            "\\_SB.GPIO", 0x00, ResourceConsumer, ,
            ) { 43 }
        })
        Name (_DSD, Package () {
          ToUUID ("daffd814-6eba-4d8c-8a91-bc9bbf4aa301"),
          Package () {
            Package () { "compatible", "google,cros-ec-espi" }
          }
        })
        Device (PWM0)
        {
          Name (_HID, "PRP0001")
          Name (_UID, 0)
          Name (_DSD, Package () {
            ToUUID ("daffd814-6eba-4d8c-8a91-bc9bbf4aa301"),
            Package () {
              Package () { "compatible", "google,cros-ec-pwm" }
            }
          })
        }
      }
    }
    Device (FAN0)
    {
      Name (_HID, "PRP0001")
      Name (_UID, 0x72)
      Name (_DSD, Package () {
        ToUUID ("daffd814-6eba-4d8c-8a91-bc9bbf4aa301"),
        Package () {
          Package () { "compatible", "pwm-fan" },
          Package () { "pwms", Package () {
            \_SB.ESPI.EC0.PWM0, 0, 0xffff, 0
          } },
          Package () { "cooling-levels", Package () { 77, 153, 204, 255 } }
        }
      })
    }
    Device (MPXY)
    {
      Name (_HID, "RSCV0005")
      Name (_UID, 0x73)
      Name (_DSD, Package () {
        ToUUID ("daffd814-6eba-4d8c-8a91-bc9bbf4aa301"),
        Package () {
          Package () { "#mbox-cells", 2 }
        }
      })
    }
    Device (RCLK)
    {
      Name (_HID, "PRP0001")
      Name (_UID, 0x74)
      Name (_DSD, Package () {
        ToUUID ("daffd814-6eba-4d8c-8a91-bc9bbf4aa301"),
        Package () {
          Package () { "compatible", "riscv,rpmi-clock" },
          Package () { "mboxes", Package () {
            \_SB.MPXY, 8, 0
          } }
        }
      })
    }
    Device (TSEN)
    {
      Name (_HID, "PRP0001")
      Name (_UID, 0x70)
      Name (_CCA, 0)
      Name (_CRS, ResourceTemplate ()
      {
        QWordMemory (
          ResourceConsumer, PosDecode, MinFixed, MaxFixed,
          NonCacheable, ReadWrite,
          0x0, 0xD4018000, 0xD40180FF, 0x0, 0x100
        )
        Interrupt (ResourceConsumer, Level, ActiveHigh, Exclusive) { 61 }
      })
      Name (_DSD, Package () {
        ToUUID ("daffd814-6eba-4d8c-8a91-bc9bbf4aa301"),
        Package () {
          Package () { "compatible", "spacemit,k3-tsensor" },
          Package () { "sensor_range", Package () { 0, 7 } },
          Package () { "tsensor_map", Package () { 1, 0, 1, 1, 1, 1, 1, 1 } },
          Package () { "temperature_offset", 274 }
        }
      })
    }
  }
}
