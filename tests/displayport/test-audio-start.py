#!/usr/bin/env python3
"""DisplayPort audio start: the q6afe port starts from the back-end trigger, the
card runs back-end triggers before the front end, and refuses the start while
the DP jack reports no display.

Compiles q6hdmi_dai_trigger() from q6afe-dai.c and sm8250_snd_trigger() from
sm8250.c against a small model and runs them in the order soc-pcm uses: the
link trigger first, then the DAI trigger.
"""
from pathlib import Path
import re, subprocess, sys, tempfile

if len(sys.argv) != 2:
    raise SystemExit(f"usage: {sys.argv[0]} KERNEL_CHECKOUT")
root = Path(sys.argv[1]).resolve()

def extract(path, name):
    s = (root/path).read_text()
    m = re.search(r'^static int ' + name + r'\(', s, re.M)
    assert m, name
    b = s.index('{', m.start()); end = b + 1; depth = 1
    while depth:
        depth += (s[end] == '{') - (s[end] == '}'); end += 1
    return s[m.start():end] + '\n'

# Prepare must leave the DisplayPort port to the trigger on a nonatomic PCM.
prepare = extract('sound/soc/qcom/qdsp6/q6afe-dai.c', 'q6afe_dai_prepare')
skip = prepare.find('dai->id == DISPLAY_PORT_RX && substream->pcm->nonatomic')
assert skip >= 0 and skip < prepare.index('q6afe_port_start('), \
    'q6afe_dai_prepare() starts the DisplayPort port before the trigger'

# Playback front ends must run their back-end triggers first, so that the port
# is running before the ASM stream that feeds it starts.
card = (root/'sound/soc/qcom/sm8250.c').read_text()
add_be = card[card.index('static void sm8250_add_be_ops('):]
add_be = add_be[:add_be.index('\n}\n')]
assert 'link->dynamic' in add_be and \
    'link->trigger[SNDRV_PCM_STREAM_PLAYBACK] = SND_SOC_DPCM_TRIGGER_POST' in add_be, \
    'playback front ends do not trigger their back ends first'

code = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#define DISPLAY_PORT_RX 104
#define SNDRV_PCM_TRIGGER_STOP 0
#define SNDRV_PCM_TRIGGER_START 1
#define SNDRV_PCM_TRIGGER_PAUSE_PUSH 3
#define SNDRV_PCM_TRIGGER_PAUSE_RELEASE 4
#define SNDRV_PCM_TRIGGER_RESUME 6
#define SND_JACK_VIDEOOUT 0x0010
#define SND_JACK_LINEOUT 0x0020
#define SND_JACK_AVOUT (SND_JACK_LINEOUT | SND_JACK_VIDEOOUT)
#define READ_ONCE(x) (x)
#define dev_err(dev, ...) ((void)(dev))
struct snd_soc_dai { void *dev; int id; };
struct snd_soc_jack { int status; };
struct sm8250_snd_data { struct snd_soc_jack dp_jack; };
struct snd_soc_card { struct sm8250_snd_data *drvdata; };
struct snd_soc_pcm_runtime { struct snd_soc_card *card; struct snd_soc_dai *cpu; };
struct snd_pcm_substream { struct snd_soc_pcm_runtime *rtd; };
struct q6afe_dai_data { bool is_port_started[256]; void *port[256]; };
static struct snd_soc_pcm_runtime *snd_soc_substream_to_rtd(struct snd_pcm_substream *s) { return s->rtd; }
static struct snd_soc_dai *snd_soc_rtd_to_cpu(struct snd_soc_pcm_runtime *rtd, int i) { (void)i; return rtd->cpu; }
static struct sm8250_snd_data *snd_soc_card_get_drvdata(struct snd_soc_card *card) { return card->drvdata; }
static void *dev_get_drvdata(void *dev) { return dev; }
static int starts, start_error;
static int q6afe_port_start(void *port) { (void)port; starts++; return start_error; }
'''
code += extract('sound/soc/qcom/sm8250.c', 'sm8250_snd_trigger')
code += extract('sound/soc/qcom/qdsp6/q6afe-dai.c', 'q6hdmi_dai_trigger')
code += r'''
static struct q6afe_dai_data afe;
static struct sm8250_snd_data card_data;
static struct snd_soc_card card = { &card_data };
static struct snd_soc_dai dp = { &afe, DISPLAY_PORT_RX }, hdmi = { &afe, 1 };
static struct snd_soc_pcm_runtime dp_rtd = { &card, &dp }, hdmi_rtd = { &card, &hdmi };
static struct snd_pcm_substream dp_pcm = { &dp_rtd }, hdmi_pcm = { &hdmi_rtd };

/* soc-pcm runs the link trigger before the DAI trigger and stops at the first error. */
static int trigger(struct snd_pcm_substream *s, int cmd)
{
	int ret = sm8250_snd_trigger(s, cmd);

	return ret ? ret : q6hdmi_dai_trigger(s, cmd, s->rtd->cpu);
}

int main(void)
{
	/* Nothing plugged in: the start is refused before it reaches the DSP. */
	assert(trigger(&dp_pcm, SNDRV_PCM_TRIGGER_START) == -ENODEV);
	assert(trigger(&dp_pcm, SNDRV_PCM_TRIGGER_RESUME) == -ENODEV);
	assert(trigger(&dp_pcm, SNDRV_PCM_TRIGGER_PAUSE_RELEASE) == -ENODEV);
	assert(!trigger(&dp_pcm, SNDRV_PCM_TRIGGER_STOP));
	assert(starts == 0 && !afe.is_port_started[DISPLAY_PORT_RX]);

	/* A failed AFE start is reported and leaves the port stopped. */
	card_data.dp_jack.status = SND_JACK_AVOUT;
	start_error = -ETIMEDOUT;
	assert(trigger(&dp_pcm, SNDRV_PCM_TRIGGER_START) == -ETIMEDOUT);
	assert(starts == 1 && !afe.is_port_started[DISPLAY_PORT_RX]);

	/* With a display the start starts the port, once. */
	start_error = 0;
	assert(!trigger(&dp_pcm, SNDRV_PCM_TRIGGER_START));
	assert(starts == 2 && afe.is_port_started[DISPLAY_PORT_RX]);
	assert(!trigger(&dp_pcm, SNDRV_PCM_TRIGGER_PAUSE_PUSH));
	assert(!trigger(&dp_pcm, SNDRV_PCM_TRIGGER_PAUSE_RELEASE));
	assert(starts == 2);

	/* Other ports are left to prepare, whatever the DP jack says. */
	card_data.dp_jack.status = 0;
	assert(!trigger(&hdmi_pcm, SNDRV_PCM_TRIGGER_START));
	assert(starts == 2 && !afe.is_port_started[hdmi.id]);

	puts("PASS: prepare leaves the DP port to the trigger; back ends trigger first; no display refuses the start before the DSP; a display starts the port once; failed starts stay stopped; other ports untouched");
	return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
    p = Path(d); (p/'test.c').write_text(code)
    subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                    str(p/'test.c'), '-o', str(p/'test')], check=True)
    subprocess.run([str(p/'test')], check=True)
