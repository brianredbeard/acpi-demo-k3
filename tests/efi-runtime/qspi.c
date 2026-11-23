/* Actual QSPI transfer with a mock register file at its Linux runtime VA. */
#include "QspiDxe.c"
#include <assert.h>
#include <string.h>

#define REG_VA 0x20f0c000
static UINT32 Regs[SIZE_4KB / sizeof (UINT32)];
static BOOLEAN FailMap, SfarStuck, ResetStuck;
static UINTN Triggers;

BOOLEAN EFIAPI EfiAtRuntime (VOID) { return TRUE; }
UINTN EFIAPI MicroSecondDelay (UINTN n) { return n; }
VOID *EFIAPI CopyMem (VOID *d, CONST VOID *s, UINTN n) { return memcpy (d, s, n); }

EFI_STATUS EFIAPI
EfiConvertPointer (UINTN Flags, VOID **Address)
{
  assert ((UINTN)*Address == 0xd420c000);
  if (FailMap) { return EFI_NOT_FOUND; }
  *Address = (VOID *)(UINTN)REG_VA;
  return EFI_SUCCESS;
}

UINT32 EFIAPI
MmioRead32 (UINTN Address)
{
  assert (Address >= REG_VA && Address < REG_VA + sizeof Regs);
  if (ResetStuck && Triggers && Address == REG_VA + QSPI_FR) {
    return Regs[QSPI_FR / 4] | QSPI_FR_XIP_ON;
  }
  return Regs[(Address - REG_VA) / 4];
}

UINT32 EFIAPI
MmioWrite32 (UINTN Address, UINT32 Value)
{
  assert (Address >= REG_VA && Address < REG_VA + sizeof Regs);
  UINTN Off = Address - REG_VA;
  if (Off == QSPI_FR) {
    Regs[Off / 4] &= ~Value;
  } else {
    Regs[Off / 4] = Value;
  }
  if (SfarStuck && Off == QSPI_SFAR) {
    Regs[QSPI_FR / 4] |= QSPI_FR_IPIEF;
  }
  if (Off == QSPI_IPCR) {
    assert (Regs[QSPI_RBCT / 4] & QSPI_RBCT_RXBRD_MASK);
    Triggers++;
    Regs[QSPI_FR / 4] |= QSPI_FR_TFF;
  }
  return Value;
}

int main (int argc, char **argv)
{
  SPI_MASTER_INSTANCE Master = {0};
  SPI_DEVICE Slave = {0};
  SPI_XFER_OP Op = {0};
  UINT8 Data[QSPI_RX_FIFO_MAX];
  Master.Signature = SPI_MASTER_SIGNATURE;
  Master.QspiHost.RegisterBase = 0xd420c000;
  Master.QspiHost.CsAddr[QSPI_CS_A1] = 0xb8000000;
  Master.QspiHost.XipRead = 1;
  Master.QspiHost.RxUnitSize = 4096;
  mSpiMasterInstance = &Master;
  FailMap = strcmp (argv[1], "missing-map") == 0;
  SfarStuck = strcmp (argv[1], "sfar-timeout") == 0;
  ResetStuck = strcmp (argv[1], "reset-timeout") == 0;
  SpiMasterVirtualNotifyEvent (NULL, NULL);
  Op.Cmd.Opcode = SPI_FLASH_FAST_READ;
  Op.Cmd.BusWidth = Op.Addr.BusWidth = Op.Data.BusWidth = 1;
  Op.Addr.Val = 0x710010;
  Op.Addr.Nbytes = 3;
  Op.Data.Dir = SPI_XFER_RX_DATA;
  Op.Data.Nbytes = 4096;
  Op.Data.Buf = Data;
  assert (SpiAjustOPSize (&Master.SpiMaster, &Op) == EFI_SUCCESS);
  assert (Op.Data.Nbytes == sizeof Data);
  Regs[QSPI_RBDR0 / 4] = 0x34333231;
  Regs[QSPI_RSER / 4] = 0x1234;
  Regs[QSPI_SFA1AD / 4] = 0x88880000;
  EFI_STATUS Result = SpiTransfer (&Master.SpiMaster, &Slave, &Op);
  if (FailMap) {
    assert (Result == EFI_DEVICE_ERROR && Triggers == 0);
  } else {
    assert (Result == ((SfarStuck || ResetStuck) ? EFI_TIMEOUT : EFI_SUCCESS));
    assert (Triggers == (SfarStuck ? 0 : 1));
    assert (Regs[QSPI_RBCT / 4] == 0);
    assert (Regs[QSPI_SFAR / 4] == 0xb8710010);
    assert (Regs[QSPI_RSER / 4] == 0x1234 && Regs[QSPI_SFA1AD / 4] == 0x88880000);
    if (!SfarStuck) { assert (memcmp (Data, "1234", 4) == 0); }
  }
  return 0;
}
