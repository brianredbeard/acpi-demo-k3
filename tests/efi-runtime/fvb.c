/* Run the production FVB methods before and after SetVirtualAddressMap. */
#include "FlashFvbDxe.c"
#include <assert.h>
#include <string.h>
#include <stdio.h>

extern EFI_STATUS TestVariableWrite (EFI_FIRMWARE_VOLUME_BLOCK_PROTOCOL *, UINTN, const char *);

static BOOLEAN Virtual, Identity, FailSpi, FailRegion;
static EFI_PHYSICAL_ADDRESS Mapped;
static SPI_FLASH_PROTOCOL PhysicalSpi, VirtualSpi;
static UINT8 Storage[4];

BOOLEAN EFIAPI EfiGoneVirtual (VOID) { return Virtual; }
BOOLEAN EFIAPI EfiAtRuntime (VOID) { return Virtual; }

static EFI_STATUS EFIAPI
Write (SPI_FLASH_PROTOCOL *This, UINT32 Offset, UINTN Size, VOID *Data)
{
  assert (This == (Virtual && !Identity ? &VirtualSpi : &PhysicalSpi));
  assert (Offset == 0x710010 && Size == sizeof Storage);
  memcpy (Storage, Data, Size);
  return EFI_SUCCESS;
}

static EFI_STATUS EFIAPI
Read (SPI_FLASH_PROTOCOL *This, UINT32 Offset, UINTN Size, VOID *Data)
{
  assert (This == (Virtual && !Identity ? &VirtualSpi : &PhysicalSpi));
  assert (Offset == 0x710010 && Size == sizeof Storage);
  memcpy (Data, Storage, Size);
  return EFI_SUCCESS;
}

static EFI_STATUS EFIAPI
Erase (SPI_FLASH_PROTOCOL *This, UINTN Offset, UINTN Size)
{
  assert (This == (Virtual && !Identity ? &VirtualSpi : &PhysicalSpi));
  assert (Offset == 0x710000 && Size == SIZE_64KB);
  memset (Storage, 0xff, sizeof Storage);
  return EFI_SUCCESS;
}

/* Dispatch through the old function address after the switch must fail. */
static EFI_STATUS EFIAPI
PhysicalWrite (SPI_FLASH_PROTOCOL *This, UINT32 Offset, UINTN Size, VOID *Data)
{
  assert (!Virtual || Identity);
  return Write (This, Offset, Size, Data);
}

EFI_STATUS EFIAPI
EfiConvertPointer (UINTN Flags, VOID **Address)
{
  assert (!Virtual);
  if ((UINTN)*Address == 0xb8700000) {
    if (FailRegion) { return EFI_NOT_FOUND; }
    *Address = (VOID *)(UINTN)Mapped;
  } else if (*Address == &PhysicalSpi) {
    if (FailSpi) { return EFI_NOT_FOUND; }
    *Address = Identity ? &PhysicalSpi : &VirtualSpi;
  } else if (*Address == (VOID *)PhysicalWrite) {
    if (!Identity) { *Address = (VOID *)Write; }
  } else if (*Address != (VOID *)Read && *Address != (VOID *)Write && *Address != (VOID *)Erase) {
    return EFI_NOT_FOUND;
  }

  return EFI_SUCCESS;
}

static void
CheckIo (FV_FLASH_INSTANCE *Instance, const char *Value)
{
  UINTN Size = sizeof Storage;
  UINT8 Data[sizeof Storage];
  EFI_FIRMWARE_VOLUME_BLOCK2_PROTOCOL *Fvb = &Instance->FvbProtocol;
  EFI_STATUS Status = TestVariableWrite (Fvb, Virtual ? Mapped : 0xb8700000, Value);
  if (EFI_ERROR (Status)) {
    fprintf (stderr, "UpdateVariableStore returned 0x%llx\n", (unsigned long long)Status);
  }
  assert (Status == EFI_SUCCESS);
  assert (FvbRead (Fvb, 1, 0x10, &Size, Data) == EFI_SUCCESS);
  assert (memcmp (Value, Data, Size) == 0);
  assert (FvbEraseBlocks (Fvb, (EFI_LBA)1, (UINTN)1, EFI_LBA_LIST_TERMINATOR) == EFI_SUCCESS);
  assert (Storage[0] == 0xff);
}

int main (int argc, char **argv)
{
  FV_FLASH_INSTANCE Instance = {0};
  FV_FLASH_INSTANCE *Table[] = { &Instance };
  EFI_PHYSICAL_ADDRESS Base = 0;
  Identity = strcmp (argv[1], "identity") == 0;
  FailSpi = strcmp (argv[1], "missing-spi") == 0;
  FailRegion = strcmp (argv[1], "missing-region") == 0;
  Mapped = Identity ? 0xb8700000 : 0x20900000;
  if (strcmp (argv[1], "high-va") == 0) { Mapped += SIZE_4GB; }
  Instance.Signature = FV_FLASH_SIGNATURE;
  Instance.DeviceBaseAddress = 0xb8000000;
  Instance.RegionBaseAddress = 0xb8700000;
  Instance.Media.BlockSize = SIZE_64KB;
  Instance.Media.LastBlock = 11;
  Instance.Initialized = TRUE;
  Instance.FvbProtocol.GetPhysicalAddress = FvbGetPhysicalAddress;
  Instance.FvbProtocol.Write = FvbWrite;
  PhysicalSpi.Read = Read;
  PhysicalSpi.Write = PhysicalWrite;
  PhysicalSpi.Erase = Erase;
  mFlash = &PhysicalSpi;
  mFlashInstances = Table;
  assert (FvbGetPhysicalAddress (&Instance.FvbProtocol, &Base) == EFI_SUCCESS && Base == 0xb8700000);
  CheckIo (&Instance, "PRE1");
  FlashFvbVirtualNotifyEvent (NULL, NULL);
  VirtualSpi = PhysicalSpi; /* two views of the same runtime allocation */
  Virtual = TRUE;
  if (FailRegion) {
    assert (FvbGetPhysicalAddress (&Instance.FvbProtocol, &Base) == EFI_DEVICE_ERROR && Base == 0);
    return 0;
  }
  if (FailSpi) {
    UINT8 Byte = 0;
    UINTN Size = 1;
    assert (FvbWrite (&Instance.FvbProtocol, 0, 0, &Size, &Byte) == EFI_DEVICE_ERROR);
    assert (FvbRead (&Instance.FvbProtocol, 0, 0, &Size, &Byte) == EFI_DEVICE_ERROR);
    assert (FvbEraseBlocks (&Instance.FvbProtocol, (EFI_LBA)0, (UINTN)1, EFI_LBA_LIST_TERMINATOR) == EFI_DEVICE_ERROR);
    return 0;
  }
  CheckIo (&Instance, "UP23");
  assert (FvbGetPhysicalAddress (&Instance.FvbProtocol, &Base) == EFI_SUCCESS && Base == Mapped);
  return 0;
}
