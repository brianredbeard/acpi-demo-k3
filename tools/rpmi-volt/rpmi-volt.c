/* RPMI voltage rail qualification client v6 — sysfs-driven:
 * /sys/devices/platform/PRP0001:07/rpmi_volt/{domain,enable,level_uv,query}
 * reload-free rail control. Proper remove() frees the channel. */
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/platform_device.h>
#include <linux/mod_devicetable.h>
#include <linux/mailbox_client.h>
#include <linux/mailbox/riscv-rpmi-message.h>
#include <linux/printk.h>
#include <linux/string.h>
#include <linux/kobject.h>

#define RPMI_VOLT_SRV_GET_NUM_DOMAINS  0x02
#define RPMI_VOLT_SRV_GET_ATTRIBUTES   0x03
#define RPMI_VOLT_SRV_SET_CONFIG       0x05
#define RPMI_VOLT_SRV_GET_CONFIG       0x06
#define RPMI_VOLT_SRV_SET_LEVEL        0x07
#define RPMI_VOLT_SRV_GET_LEVEL        0x08

struct rpmi_volt_num_dom_resp { __le32 status; __le32 num_domains; };
struct rpmi_volt_attrs_req  { __le32 domain_id; };
struct rpmi_volt_attrs_resp { __le32 status; __le32 flags; __le32 num_levels;
                              __le32 trans_latency; u8 name[16]; };
struct rpmi_volt_cfg_req    { __le32 domain_id; };
struct rpmi_volt_get_cfg_resp { __le32 status; __le32 config; };
struct rpmi_volt_set_cfg_req { __le32 domain_id; __le32 config; };
struct rpmi_volt_set_cfg_resp { __le32 status; };
struct rpmi_volt_level_req  { __le32 domain_id; __le32 voltage_level; };
struct rpmi_volt_level_resp { __le32 status; __le32 voltage_level; };

static struct mbox_chan *chan;
static struct mbox_client cl;

static int rpmi_volt_call(u32 service, void *tx, u32 txlen,
                          void *rx, u32 rxlen)
{
    struct rpmi_mbox_message msg;

    rpmi_mbox_init_send_with_response(&msg, service, tx, txlen, rx, rxlen);
    return rpmi_mbox_send_message(chan, &msg);
}

static ssize_t query_show(struct device *dev, struct device_attribute *attr, char *buf)
{
    struct rpmi_volt_cfg_req greq = { .domain_id = 0 };
    struct rpmi_volt_get_cfg_resp gc;
    struct rpmi_volt_level_req lreq = { .domain_id = 0 };
    struct rpmi_volt_level_resp lv;
    struct rpmi_volt_attrs_req areq = { .domain_id = 0 };
    struct rpmi_volt_attrs_resp ar;
    int len = 0, ret;

    greq.domain_id = lreq.domain_id = areq.domain_id = 
        (u32)(uintptr_t)dev_get_drvdata(dev);

    memset(&gc, 0, sizeof(gc));
    ret = rpmi_volt_call(RPMI_VOLT_SRV_GET_CONFIG, &greq, sizeof(greq), &gc, sizeof(gc));
    len += scnprintf(buf+len, PAGE_SIZE-len, "get_config: ret=%d status=%u config=0x%x\n",
                     ret, gc.status, gc.config);
    memset(&lv, 0, sizeof(lv));
    ret = rpmi_volt_call(RPMI_VOLT_SRV_GET_LEVEL, &lreq, sizeof(lreq), &lv, sizeof(lv));
    len += scnprintf(buf+len, PAGE_SIZE-len, "get_level: ret=%d status=%u level=%d uV\n",
                     ret, lv.status, (int)le32_to_cpu(lv.voltage_level));
    memset(&ar, 0, sizeof(ar));
    ret = rpmi_volt_call(RPMI_VOLT_SRV_GET_ATTRIBUTES, &areq, sizeof(areq), &ar, sizeof(ar));
    len += scnprintf(buf+len, PAGE_SIZE-len, "attrs: ret=%d name=%.16s levels=%u latency=%u\n",
                     ret, ar.name, ar.num_levels, ar.trans_latency);
    return len;
}

static ssize_t enable_store(struct device *dev, struct device_attribute *attr,
                            const char *buf, size_t count)
{
    struct rpmi_volt_set_cfg_req sreq;
    struct rpmi_volt_set_cfg_resp sc;
    u32 domain = (u32)(uintptr_t)dev_get_drvdata(dev);
    unsigned long v;
    int ret;

    if (kstrtoul(buf, 0, &v) || v > 1)
        return -EINVAL;
    sreq.domain_id = cpu_to_le32(domain);
    sreq.config = cpu_to_le32((u32)v);
    memset(&sc, 0, sizeof(sc));
    ret = rpmi_volt_call(RPMI_VOLT_SRV_SET_CONFIG, &sreq, sizeof(sreq), &sc, sizeof(sc));
    dev_info(dev, "SET_CONFIG domain %u -> %lu: ret=%d status=%u\n",
             domain, v, ret, sc.status);
    return count;
}

static ssize_t level_store(struct device *dev, struct device_attribute *attr,
                           const char *buf, size_t count)
{
    struct rpmi_volt_level_req lreq;
    struct rpmi_volt_level_resp lv;
    u32 domain = (u32)(uintptr_t)dev_get_drvdata(dev);
    long v;
    int ret;

    if (kstrtol(buf, 0, &v))
        return -EINVAL;
    lreq.domain_id = cpu_to_le32(domain);
    lreq.voltage_level = cpu_to_le32((u32)v);
    memset(&lv, 0, sizeof(lv));
    ret = rpmi_volt_call(RPMI_VOLT_SRV_SET_LEVEL, &lreq, sizeof(lreq), &lv, sizeof(lv));
    dev_info(dev, "SET_LEVEL domain %u -> %ld uV: ret=%d status=%u\n",
             domain, v, ret, lv.status);
    return count;
}

static ssize_t domain_store(struct device *dev, struct device_attribute *attr,
                            const char *buf, size_t count)
{
    unsigned long v;
    if (kstrtoul(buf, 0, &v) || v > 31)
        return -EINVAL;
    dev_set_drvdata(dev, (void *)(uintptr_t)v);
    return count;
}

static DEVICE_ATTR_RO(query);
static DEVICE_ATTR_WO(enable);
static DEVICE_ATTR_WO(level);
static DEVICE_ATTR_WO(domain);

static struct attribute *rpmi_volt_attrs[] = {
    &dev_attr_query.attr,
    &dev_attr_enable.attr,
    &dev_attr_level.attr,
    &dev_attr_domain.attr,
    NULL,
};
ATTRIBUTE_GROUPS(rpmi_volt);

static int rpmi_qual_probe(struct platform_device *pdev)
{
    struct rpmi_mbox_message am;
    struct rpmi_volt_num_dom_resp nd;
    int ret;

    cl.dev = &pdev->dev;
    cl.tx_block = false;
    cl.knows_txdone = true;

    chan = mbox_request_channel(&cl, 0);
    if (IS_ERR(chan))
        return dev_err_probe(&pdev->dev, PTR_ERR(chan), "mbox channel request failed\n");

    memset(&am, 0, sizeof(am));
    rpmi_mbox_init_get_attribute(&am, RPMI_MBOX_ATTR_SERVICEGROUP_ID);
    ret = rpmi_mbox_send_message(chan, &am);
    if (ret || am.error)
        dev_warn(&pdev->dev, "servicegroup query failed: %d/%d\n", ret, am.error);
    else if (am.attr.value != 0x0007)
        dev_warn(&pdev->dev, "channel is not the voltage group (%u)\n", am.attr.value);
    else
        dev_info(&pdev->dev, "channel servicegroup_id = 7 (voltage)\n");

    memset(&nd, 0, sizeof(nd));
    ret = rpmi_volt_call(RPMI_VOLT_SRV_GET_NUM_DOMAINS, NULL, 0, &nd, sizeof(nd));
    if (ret)
        dev_warn(&pdev->dev, "GET_NUM_DOMAINS failed: %d\n", ret);
    else
        dev_info(&pdev->dev, "voltage domains: %u\n", nd.num_domains);

    dev_set_drvdata(&pdev->dev, (void *)(uintptr_t)8); /* start at aldo3? see docs */
    ret = sysfs_create_groups(&pdev->dev.kobj, rpmi_volt_groups);
    if (ret) {
        mbox_free_channel(chan);
        return ret;
    }
    dev_info(&pdev->dev, "sysfs interface ready (domain/enable/level/query)\n");
    return 0;
}

static void rpmi_qual_remove(struct platform_device *pdev)
{
    sysfs_remove_groups(&pdev->dev.kobj, rpmi_volt_groups);
    if (chan && !IS_ERR(chan))
        mbox_free_channel(chan);
    chan = NULL;
}

static const struct of_device_id rpmi_qual_of_match[] = {
    { .compatible = "k3,rpmi-qual-test" },
    { }
};

static struct platform_driver rpmi_qual_driver = {
    .probe = rpmi_qual_probe,
    .remove = rpmi_qual_remove,
    .driver = {
        .name = "rpmi-qual-test",
        .of_match_table = rpmi_qual_of_match,
    },
};
module_platform_driver(rpmi_qual_driver);
MODULE_LICENSE("GPL");
