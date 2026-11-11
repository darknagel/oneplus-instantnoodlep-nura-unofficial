"""Exercise unmodified production driver functions with simulated I/O/events."""
from pathlib import Path
import subprocess
import tempfile
import sys

root = Path(__file__).resolve().parent
kernel = Path(sys.argv[1]).resolve()
source = (kernel / 'drivers/power/supply/qcom_pm8150b_charger.c').read_text()

def function(name):
    start = source.index('static ', source.rfind('\n}', 0, source.index(name)) + 2)
    opening = source.index('{', source.index(name, start))
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

definitions = source.split('/* clang-format off */', 1)[1].split('/* clang-format on */', 1)[0]
prelude = (root / 'policy-harness.h').read_text()
names = ['smb5_get_prop_usb_online(', 'smb5_apsd_get_charger_type(',
         'smb5_set_current_limit(', 'smb5_set_charge_current(',
         'smb5_queue_status_work(', 'smb5_apply_input_limit(',
         'smb5_status_change_work(', 'smb5_handle_usb_plugin(',
         'smb5_handle_usb_source_change(']
body = '\n\n'.join(function(name) for name in names)
start = source.index('\tfv_uv = chip->batt_info->voltage_max_design_uv;')
end = source.index('\n\trc = smb5_set_charge_current(', start)
body += '\nstatic int test_voltage(struct smb5_chip *chip) { int rc, fv_uv;\n' + source[start:end] + '\nreturn 0; }\n'

main = r'''
#include <assert.h>
static struct smb5_chip fresh(void) {
    memset(registers,0,sizeof(registers)); memset(supply,0,sizeof(supply));
    pending=reruns=apsd_reads=0; apsd_read_enabled=-1; start_enabled=0;
    read_fault=write_fault=-1; supplier_error=0;
    registers[0x310]=BIT(4);
    supply[POWER_SUPPLY_PROP_ONLINE]=1;
    supply[POWER_SUPPLY_PROP_VOLTAGE_NOW]=5000000;
    supply[POWER_SUPPLY_PROP_USB_TYPE]=POWER_SUPPLY_USB_TYPE_C;
    return (struct smb5_chip){.ready=true,.has_tcpm=true,.user_current_limit=3000000};
}
static void tick(struct smb5_chip *c) {
    pending=0; smb5_status_change_work(&c->status_change_work.work);
}
static void completed(unsigned int result) {registers[0x307]=1;registers[0x308]=result;}
static void report(const char *name) {printf("PASS %s\n",name);}
int main(void) {
    struct smb5_chip c; int type, expected, count, before;
    /* All possible masked results: invalid combinations must not raise power. */
    for (unsigned int raw=0;raw<128;raw++) {
        c=fresh();completed(raw); expected=POWER_SUPPLY_USB_TYPE_UNKNOWN;
        if (raw==1) expected=POWER_SUPPLY_USB_TYPE_SDP;
        if (raw==4) expected=POWER_SUPPLY_USB_TYPE_CDP;
        if (raw==2||raw==8||raw==32||raw==64||raw==40||raw==72) expected=POWER_SUPPLY_USB_TYPE_DCP;
        assert(!smb5_apsd_get_charger_type(&c,&type));assert(type==expected);
    }
    report("all 128 result encodings; empty and invalid results stay Unknown");
    c=fresh();completed(1);tick(&c);
    assert(c.usb_type==POWER_SUPPLY_USB_TYPE_UNKNOWN && c.source_current_limit==500000);
    assert(reruns==1 && start_enabled && apsd_reads==0 && pending);
    completed(8);tick(&c);
    assert(c.usb_type==POWER_SUPPLY_USB_TYPE_DCP && registers[0x370]==30 && pending);
    report("fresh legacy cycle discards old SDP and detects DCP after enable/restart");
    count=0;while(pending && count<20){tick(&c);count++;}
    assert(count==3 && !pending && reruns==1);
    completed(4);assert(smb5_handle_usb_source_change(0,&c)==IRQ_HANDLED);assert(pending);
    tick(&c);assert(c.usb_type==POWER_SUPPLY_USB_TYPE_CDP && !pending && reruns==1);
    report("late source-change interrupt refreshes classification after polling ends");
    c=fresh();tick(&c);completed(1);tick(&c);
    assert(c.usb_type==POWER_SUPPLY_USB_TYPE_SDP && c.source_current_limit==500000 && pending);
    completed(8);tick(&c);assert(c.usb_type==POWER_SUPPLY_USB_TYPE_DCP);
    report("bounded fallback polling refreshes early SDP without a source-change IRQ");
    c=fresh();tick(&c);count=0;
    while(pending && count<20){tick(&c);count++;}
    assert(count==4 && !pending && reruns==1 && c.source_current_limit==500000);
    assert(c.usb_type==POWER_SUPPLY_USB_TYPE_UNKNOWN);
    report("incomplete detection stops after four reads, without restart storm");
    c=fresh();supply[POWER_SUPPLY_PROP_USB_TYPE]=POWER_SUPPLY_USB_TYPE_PD;
    supply[POWER_SUPPLY_PROP_CURRENT_NOW]=3000000;tick(&c);
    assert(c.usb_type==POWER_SUPPLY_USB_TYPE_PD && c.source_current_limit==3000000);
    assert(!c.apsd_started && !reruns && !(registers[0x362]&BIT(3)));
    supply[POWER_SUPPLY_PROP_USB_TYPE]=POWER_SUPPLY_USB_TYPE_C;
    supply[POWER_SUPPLY_PROP_CURRENT_NOW]=0;completed(8);tick(&c);
    assert(c.usb_type==POWER_SUPPLY_USB_TYPE_UNKNOWN && reruns==1 && start_enabled);
    supply[POWER_SUPPLY_PROP_USB_TYPE]=POWER_SUPPLY_USB_TYPE_PD;
    supply[POWER_SUPPLY_PROP_CURRENT_NOW]=2000000;tick(&c);
    assert(c.source_current_limit==2000000 && !c.apsd_started && !(registers[0x362]&BIT(3)));
    report("PD to USB-A restarts detection; returning to PD disables it");
    c=fresh();tick(&c);completed(8);tick(&c);
    smb5_handle_usb_plugin(0,&c);assert(!c.apsd_started && pending);tick(&c);
    assert(reruns==2 && c.usb_type==POWER_SUPPLY_USB_TYPE_UNKNOWN);
    supply[POWER_SUPPLY_PROP_ONLINE]=0;tick(&c);
    assert(!c.apsd_started && !c.source_current_limit && (registers[0x340]&1));
    report("quick cable replacement resets detection; detach suspends input");
    c=fresh();c.user_current_limit=250000;tick(&c);completed(8);tick(&c);
    assert(c.source_current_limit==1500000 && registers[0x370]==5);
    report("user input-current limit remains effective after DCP detection");
    c=fresh();tick(&c);read_fault=0x307;tick(&c);
    assert(!c.source_current_limit && !c.apsd_started && (registers[0x340]&1));
    c=fresh();write_fault=0x341;tick(&c);
    assert(!c.source_current_limit && !c.apsd_started && (registers[0x340]&1));
    report("detection read/restart failures suspend input and invalidate state");
    c=fresh();supply[POWER_SUPPLY_PROP_VOLTAGE_NOW]=9000000;tick(&c);
    assert(!c.source_current_limit && (registers[0x340]&1));
    report("existing board voltage guard remains effective");
    c=fresh();assert(!smb5_set_charge_current(&c,2000000));assert(registers[0x61]==40);
    assert(!smb5_set_charge_current(&c,3000000));assert(registers[0x61]==60);
    assert(!smb5_set_charge_current(&c,-EINVAL));assert(registers[0x61]==30);
    before=registers[0x61];assert(smb5_set_charge_current(&c,8000001)==-EINVAL);
    assert(smb5_set_charge_current(&c,1)==-EINVAL && (int)registers[0x61]==before);
    report("battery current uses board value, with correct encoding and hardware bounds");
    c=fresh();c.ready=false;smb5_handle_usb_source_change(0,&c);assert(!pending);
    smb5_handle_usb_plugin(0,&c);assert(!pending);
    report("IRQs do not schedule work after shutdown");
    c=fresh();struct battery_info battery={-EINVAL,4350000};c.batt_info=&battery;
    assert(!test_voltage(&c) && registers[FLOAT_VOLTAGE_CFG]==0x4b);
    battery.voltage_max_design_uv=4359000;
    assert(!test_voltage(&c) && registers[FLOAT_VOLTAGE_CFG]==0x4b);
    battery.voltage_max_design_uv=3500000;assert(test_voltage(&c)==-EINVAL);
    battery.voltage_max_design_uv=4800000;assert(test_voltage(&c)==-EINVAL);
    battery.voltage_max_design_uv=4350000;battery.constant_charge_voltage_max_uv=4400000;
    assert(!test_voltage(&c) && registers[FLOAT_VOLTAGE_CFG]==0x4b);
    report("float-voltage encoding, flooring and battery-design bounds");
    c=fresh();supply[POWER_SUPPLY_PROP_CURRENT_NOW]=3000000;tick(&c);
    assert(c.usb_type==POWER_SUPPLY_USB_TYPE_C && c.source_current_limit==3000000);
    assert(!apsd_reads && !reruns && !(registers[0x362]&BIT(3)));
    c.user_current_limit=1000000;tick(&c);assert(registers[0x370]==20);
    c.user_current_limit=0;tick(&c);assert(registers[0x340]&1);
    report("Type-C Rp bypasses detection; user limit and zero-current suspend apply");
    c=fresh();supply[POWER_SUPPLY_PROP_USB_TYPE]=POWER_SUPPLY_USB_TYPE_PD;
    supply[POWER_SUPPLY_PROP_CURRENT_NOW]=0;tick(&c);
    assert(!c.source_current_limit && (registers[0x340]&1));
    c=fresh();supplier_error=-ENODEV;tick(&c);
    assert(!c.source_current_limit && (registers[0x340]&1));
    c=fresh();supply[POWER_SUPPLY_PROP_CURRENT_NOW]=-EINVAL;tick(&c);
    assert(!c.source_current_limit && (registers[0x340]&1));
    report("PD zero current and supplier failures suspend input");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='nura-policy-') as scratch:
    generated = Path(scratch) / 'policy-regression.c'
    generated.write_text(prelude + definitions + body + main)
    binary = Path(scratch) / 'policy-test'
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-parameter',
                    '-fsanitize=address,undefined',str(generated),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
