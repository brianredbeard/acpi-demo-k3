# K3 Linux kernel

| What are you building? | Where to start |
| --- | --- |
| The full EL10-284 kernel RPM | [Staging instructions](el10-284/README.md) and [kernel.spec](el10-284/kernel.spec). The spec lists every K3 patch and its application order. |
| One driver module RPM | [Module build instructions](kmods/README.md). Each job uses a patch from the same EL10-284 directory and targets a specific kernel ABI. |

For the original UFS and GPIO bring-up, backport decisions, and earlier RPM patch revisions, see the [kernel history](../../docs/history/kernel/README.md).
