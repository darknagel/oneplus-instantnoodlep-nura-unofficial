"""Check DP teardown retries and HDMI isolation against a kernel checkout."""
from pathlib import Path
import subprocess
import sys
import tempfile
kernel = Path(sys.argv[1]).resolve()
source = (kernel / 'sound/soc/qcom/qdsp6/q6afe-dai.c').read_text()
start = source.index('static int q6hdmi_dai_hw_free(')
end = source.index('static int q6slim_set_channel_map(', start)
prefix = r"""
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stdio.h>
#define DISPLAY_PORT_RX 104
struct snd_pcm_substream { int unused; };
struct q6afe_dai_data { bool is_port_started[256]; void *port[256]; };
struct snd_soc_dai { void *dev; int id; };
static int stops, stop_error;
static void *dev_get_drvdata(void *dev) { return dev; }
static int q6afe_port_stop(void *port) { (void)port; stops++; return stop_error; }
"""
suffix = r"""int main(void) {
 struct q6afe_dai_data data = {0};
 struct snd_soc_dai dp = { &data, DISPLAY_PORT_RX }, hdmi = { &data, 1 };
 struct snd_pcm_substream pcm = {0};
 assert(!q6hdmi_dai_hw_free(&pcm, &dp) && stops == 0);
 data.is_port_started[DISPLAY_PORT_RX] = true;
 assert(!q6hdmi_dai_hw_free(&pcm, &dp));
 assert(stops == 1 && !data.is_port_started[DISPLAY_PORT_RX]);
 assert(!q6hdmi_dai_hw_free(&pcm, &dp) && stops == 1);
 data.is_port_started[DISPLAY_PORT_RX] = true;
 stop_error = -EIO;
 assert(q6hdmi_dai_hw_free(&pcm, &dp) == -EIO);
 assert(data.is_port_started[DISPLAY_PORT_RX]);
 stop_error = 0;
 assert(!q6hdmi_dai_hw_free(&pcm, &dp));
 assert(!data.is_port_started[DISPLAY_PORT_RX] && stops == 3);
 data.is_port_started[hdmi.id] = true;
 assert(!q6hdmi_dai_hw_free(&pcm, &hdmi) && stops == 3);
 assert(data.is_port_started[hdmi.id]);
 puts("PASS: inactive port, duplicate cleanup, hw_free retries, HDMI isolation");
}
"""
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path/'test.c').write_text(prefix + source[start:end] + suffix)
    subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', str(path/'test.c'), '-o', str(path/'test')], check=True)
    subprocess.run([str(path/'test')], check=True)
