#include <stdio.h>
#include <stdbool.h>
#include <string.h>
#include <stddef.h>
#include <errno.h>
#define BIT(n) (1U << (n))
#define GENMASK(h,l) (((~0U) << (l)) & ((~0U) >> (31-(h))))
#define min(a,b) ((a)<(b)?(a):(b))
#define clamp(v,l,h) ((v)<(l)?(l):((v)>(h)?(h):(v)))
#define HZ 100
#define mutex_lock(x) ((void)0)
#define mutex_unlock(x) ((void)0)
#define dev_err(...) ((void)0)
#define dev_err_ratelimited(...) ((void)0)
#define dev_err_probe(dev,err,...) (err)
#define dev_info(...) ((void)0)
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
enum { POWER_SUPPLY_USB_TYPE_UNKNOWN, POWER_SUPPLY_USB_TYPE_SDP,
       POWER_SUPPLY_USB_TYPE_CDP, POWER_SUPPLY_USB_TYPE_DCP,
       POWER_SUPPLY_USB_TYPE_C, POWER_SUPPLY_USB_TYPE_PD,
       POWER_SUPPLY_USB_TYPE_PD_PPS };
enum { POWER_SUPPLY_PROP_ONLINE, POWER_SUPPLY_PROP_CURRENT_NOW,
       POWER_SUPPLY_PROP_USB_TYPE, POWER_SUPPLY_PROP_VOLTAGE_NOW };
struct work_struct { int unused; };
struct delayed_work { struct work_struct work; };
struct battery_info { int constant_charge_voltage_max_uv, voltage_max_design_uv; };
struct smb5_chip {
    struct battery_info *batt_info;
    void *dev, *regmap, *chg_psy;
    unsigned int base;
    int lock;
    bool ready, has_tcpm, apsd_started;
    unsigned int apsd_retries, user_current_limit, source_current_limit;
    int usb_type;
    struct delayed_work status_change_work;
};
typedef int irqreturn_t;
#define IRQ_HANDLED 1
static unsigned int registers[0x1000];
static int supply[4], pending, reruns, apsd_read_enabled, supplier_error;
static void *system_wq;
static int start_enabled, read_fault, write_fault, apsd_reads;
static int regmap_read(void *map, unsigned int addr, unsigned int *value) {
    (void)map;
    if ((int)addr == read_fault) return -EIO;
    if (addr == 0x307) apsd_reads++;
    if (addr == 0x307) apsd_read_enabled = !!(registers[0x362] & BIT(3));
    *value = registers[addr]; return 0;
}
static int regmap_write(void *map, unsigned int addr, unsigned int value) {
    (void)map;
    if ((int)addr == write_fault) return -EIO;
    if (addr == 0x341 && (value & 1)) {
        reruns++; start_enabled=!!(registers[0x362]&BIT(3));
        registers[0x307]=0; registers[0x308]=0;
        value &= ~1; /* Self-clearing restart command; completion is asynchronous. */
    }
    registers[addr] = value; return 0;
}
static int regmap_update_bits(void *map, unsigned int addr, unsigned int mask, unsigned int value) {
    return regmap_write(map, addr, (registers[addr] & ~mask) | (value & mask));
}
static void mod_delayed_work(void *queue, struct delayed_work *work, int delay) {
    (void)queue; (void)work; (void)delay; pending = 1;
}
static void power_supply_changed(void *psy) { (void)psy; }
static int smb5_supplier_property(struct smb5_chip *chip, int prop, int *value) {
    (void)chip; *value = supply[prop]; return supplier_error;
}
