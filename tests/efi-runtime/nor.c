/* Exercise virtual SPI protocol dispatch and the embedded device descriptor. */
#include "SpiNorFlashDxe.c"
#include <assert.h>
#include <string.h>

static SPI_MASTER_PROTOCOL Physical, Mapped;
static NOR_FLASH_INFO OldInfo, NewInfo;
static UINT8 StatusReg;
static BOOLEAN Busy, FailMap, DenyWriteEnable;
static UINTN Programs;
static UINT8 Data[4];

VOID *EFIAPI ZeroMem (VOID *p, UINTN n) { return memset (p, 0, n); }
UINTN EFIAPI MicroSecondDelay (UINTN n) { return n; }

static EFI_STATUS EFIAPI
Adjust (SPI_MASTER_PROTOCOL *This, SPI_XFER_OP *Op)
{
  assert (This == &Mapped);
  return EFI_SUCCESS;
}

static EFI_STATUS EFIAPI
Transfer (SPI_MASTER_PROTOCOL *This, SPI_DEVICE *Slave, SPI_XFER_OP *Op)
{
  assert (This == &Mapped && Slave->Info == &NewInfo);
  assert (Slave->Cs == 0 && Slave->AddrSize == 3);
  switch (Op->Cmd.Opcode) {
    case CMD_READ_STATUS:
      *(UINT8 *)Op->Data.Buf = StatusReg;
      break;
    case CMD_WRITE_ENABLE:
      StatusReg = DenyWriteEnable ? 0 : STATUS_REG_POLL_WEL;
      break;
    case CMD_PAGE_PROGRAM:
      assert (StatusReg == STATUS_REG_POLL_WEL && Op->Addr.Val == 0x710010);
      assert (Op->Data.Nbytes == sizeof Data);
      memcpy (Data, Op->Data.Buf, sizeof Data);
      StatusReg = Busy ? STATUS_REG_POLL_WIP : 0;
      Programs++;
      break;
    default:
      assert (0 && "unexpected NOR opcode");
  }
  return EFI_SUCCESS;
}

EFI_STATUS EFIAPI
EfiConvertPointer (UINTN Flags, VOID **Address)
{
  if (*Address == &OldInfo) {
    if (FailMap) { return EFI_NOT_FOUND; }
    *Address = &NewInfo;
  } else if (*Address == &Physical) {
    *Address = &Mapped;
  } else {
    assert (*Address == (VOID *)Adjust || *Address == (VOID *)Transfer);
  }
  return EFI_SUCCESS;
}

int main (int argc, char **argv)
{
  SPI_FLASH_INSTANCE Flash = {0};
  EFI_STATUS Status;
  FailMap = strcmp (argv[1], "missing-map") == 0;
  Busy = strcmp (argv[1], "program-timeout") == 0;
  DenyWriteEnable = strcmp (argv[1], "enable-timeout") == 0;
  NewInfo.PageSize = 256;
  Flash.Signature = SPI_FLASH_SIGNATURE;
  Flash.SpiDev.Info = &OldInfo;
  Flash.SpiDev.AddrSize = 3;
  Flash.SpiDev.FlashSize = SIZE_8MB;
  Physical.AjustOPSize = Adjust;
  Physical.Transfer = Transfer;
  mSpiMasterProtocol = &Physical;
  mSpiFlashInstance = &Flash;
  SpiFlashVirtualNotifyEvent (NULL, NULL);
  Mapped = Physical;
  Status = SpiFlashWrite (&Flash.SpiFlashProtocol, 0x710010, sizeof Data, "UP23");
  if (FailMap) {
    assert (Status == EFI_DEVICE_ERROR && Programs == 0);
  } else if (DenyWriteEnable) {
    assert (Status == EFI_TIMEOUT && Programs == 0);
  } else {
    assert (Status == (Busy ? EFI_TIMEOUT : EFI_SUCCESS));
    assert (Programs == 1 && memcmp (Data, "UP23", sizeof Data) == 0);
  }
  return 0;
}
