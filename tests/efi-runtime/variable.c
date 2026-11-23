/* Link the pinned SDK's actual FV bounds check and LBA walk into the FVB test. */
#include "Variable.c"
#include <string.h>

VOID *EFIAPI CopyMem (VOID *d, CONST VOID *s, UINTN n) { return memcpy (d, s, n); }

EFI_STATUS
TestVariableWrite (EFI_FIRMWARE_VOLUME_BLOCK_PROTOCOL *Fvb, UINTN FvBase, const char *Value)
{
  VARIABLE_MODULE_GLOBAL Module = {0};
  EFI_FIRMWARE_VOLUME_HEADER Header = {0};
  Header.FvLength = 12 * SIZE_64KB;
  Header.BlockMap[0].NumBlocks = 12;
  Header.BlockMap[0].Length = SIZE_64KB;
  Module.VariableGlobal.NonVolatileVariableBase = FvBase + sizeof Header;
  mNvFvHeaderCache = &Header;
  mVariableModuleGlobal = &Module;
  return UpdateVariableStore (&Module.VariableGlobal, FALSE, TRUE, Fvb,
                              SIZE_64KB + 0x10 - sizeof Header, 4, (UINT8 *)Value);
}
