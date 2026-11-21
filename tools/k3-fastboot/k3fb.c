// SPDX-License-Identifier: GPL-2.0
// k3-enter-fastboot flag writer: byte 0x1 at the DTB_TABLE
// shared region (0xc087c000) that the ESOS RPMI sysreset
// handler polls on reboot (k3-os0_sysreset.c: LISTEN_ADDR /
// FLAG_FASTBOOT). One-shot: load, write, done.
#include <linux/module.h>
#include <linux/io.h>
#include <linux/init.h>

#define LISTEN_ADDR   0xc087c000UL
#define FLAG_FASTBOOT 0x1

static int __init k3fb_init(void)
{
	void __iomem *p = ioremap(LISTEN_ADDR, 1);
	if (!p)
		return -ENOMEM;
	iowrite8(FLAG_FASTBOOT, p);
	iounmap(p);
	pr_info("k3fb: FLAG_FASTBOOT written to 0x%lx — next reboot enters fastboot\n", LISTEN_ADDR);
	return 0;
}

static void __exit k3fb_exit(void) { }

module_init(k3fb_init);
module_exit(k3fb_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("K3 fastboot-reboot flag writer (ESOS sysreset listen byte)");
