"""Compile the actual changed helpers against mocks of their hardware calls."""
from pathlib import Path
import subprocess
import tempfile
import sys

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/kernel/phystart1')


def function(source, name):
    start = source.index('static int ' + name + '(')
    body = source.index('{', start)
    depth = 1
    end = body + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


panel = (ROOT / 'drivers/gpu/drm/panel/panel-samsung-ams678uw01.c').read_text()
charger = (ROOT / 'drivers/power/supply/qcom_pm8150b_charger.c').read_text()
prelude = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
typedef uint16_t u16;
#define MIPI_DSI_MODE_LPM 1UL
struct ams678uw01 { struct { bool prepared; } panel; };
struct mipi_dsi_device { unsigned long mode_flags; struct ams678uw01 *ctx; };
struct backlight_device { struct mipi_dsi_device *dsi; struct { int brightness; } props; };
static int transfers, transfer_error, last_brightness, adc_reads, online_rc, online_value, adc_rc;
static struct mipi_dsi_device *bl_get_data(struct backlight_device *b) { return b->dsi; }
static struct ams678uw01 *mipi_dsi_get_drvdata(struct mipi_dsi_device *d) { return d->ctx; }
static int backlight_get_brightness(struct backlight_device *b) { return b->props.brightness; }
static int mipi_dsi_dcs_set_display_brightness_large(struct mipi_dsi_device *d, u16 v) {
    assert(!(d->mode_flags & MIPI_DSI_MODE_LPM)); transfers++; last_brightness=v; return transfer_error;
}
static int mipi_dsi_dcs_get_display_brightness_large(struct mipi_dsi_device *d, u16 *v) {
    assert(!(d->mode_flags & MIPI_DSI_MODE_LPM)); transfers++; *v=32; return transfer_error;
}
struct smb5_chip { void *dev; };
struct iio_channel { int error; };
#define IS_ERR(p) ((p)->error != 0)
#define PTR_ERR(p) ((long)(p)->error)
#define dev_err(...) ((void)0)
static int smb5_get_prop_usb_online(struct smb5_chip *c, int *v) { (void)c; *v=online_value; return online_rc; }
static int iio_read_channel_processed(struct iio_channel *c, int *v) { (void)c; adc_reads++; *v=4943248; return adc_rc; }
'''
main = r'''
int main(void) {
    struct ams678uw01 ctx={0};
    struct mipi_dsi_device d={.ctx=&ctx,.mode_flags=0x81};
    struct backlight_device b={.dsi=&d,.props.brightness=32};
    assert(ams678uw01_bl_update_status(&b)==0 && transfers==0);
    assert(ams678uw01_bl_get_brightness(&b)==32 && transfers==0);
    ctx.panel.prepared=true;
    for (unsigned long flags=0x80; flags<=0x81; flags++) {
        d.mode_flags=flags; transfer_error=0;
        assert(ams678uw01_bl_update_status(&b)==0 && last_brightness==32 && d.mode_flags==flags);
        assert(ams678uw01_bl_get_brightness(&b)==32 && d.mode_flags==flags);
        transfer_error=-EIO;
        assert(ams678uw01_bl_update_status(&b)==-EIO && d.mode_flags==flags);
        assert(ams678uw01_bl_get_brightness(&b)==-EIO && d.mode_flags==flags);
    }
    struct smb5_chip c={0}; struct iio_channel adc={0}; int value=-1;
    online_value=0;
    assert(smb5_get_iio_chan(&c,&adc,&value)==0 && value==0 && adc_reads==0);
    online_value=1;
    assert(smb5_get_iio_chan(&c,&adc,&value)==0 && value==4943248 && adc_reads==1);
    online_rc=-EIO;
    assert(smb5_get_iio_chan(&c,&adc,&value)==-EIO && adc_reads==1);
    online_rc=0; adc_rc=-ETIMEDOUT;
    assert(smb5_get_iio_chan(&c,&adc,&value)==-ETIMEDOUT && adc_reads==2);
    adc.error=-ENODEV;
    assert(smb5_get_iio_chan(&c,&adc,&value)==-ENODEV && adc_reads==2);
    puts("PASS: cached brightness, DSI error unwind and online USB telemetry");
}
'''
with tempfile.TemporaryDirectory() as d:
    p = Path(d) / 'test.c'
    p.write_text(prelude + '\n' + function(panel, 'ams678uw01_bl_update_status') + '\n' +
                 function(panel, 'ams678uw01_bl_get_brightness') + '\n' +
                 function(charger, 'smb5_get_iio_chan') + '\n' + main)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', str(p), '-o', d+'/test'], check=True)
    subprocess.run([d+'/test'], check=True)
