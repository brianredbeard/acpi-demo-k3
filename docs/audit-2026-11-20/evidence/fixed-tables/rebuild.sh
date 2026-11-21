#!/bin/bash
# Workstation-specific reproducibility: first reconstruct locked platforms under
# /tmp/k3-independent-audit/platforms. Uses existing generated AutoGen.h + EDK2.
set -eu
export WORKSPACE=/home/bharring/Projects/K3-Ubuntu-Images/workdir/k3-maintained-efi
export EDK_TOOLS_PATH=/home/bharring/Projects/K3-Ubuntu-Images/workdir/efi-development/baseline/edk2/BaseTools
export PATH="$EDK_TOOLS_PATH/Source/C/bin:$PATH"
mkdir -p /tmp/k3-independent-audit/fixed-tables
make -B -f docs/audit-2026-11-20/evidence/fixed-tables/Makefile \
 /tmp/k3-independent-audit/fixed-tables/Madt.acpi \
 /tmp/k3-independent-audit/fixed-tables/Mcfg.acpi \
 /tmp/k3-independent-audit/fixed-tables/Rhct.acpi \
 /tmp/k3-independent-audit/fixed-tables/Pptt.acpi \
 /tmp/k3-independent-audit/fixed-tables/Fadt.acpi \
 /tmp/k3-independent-audit/fixed-tables/Spcr.acpi
