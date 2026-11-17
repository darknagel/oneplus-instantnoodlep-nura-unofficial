/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix-oplus-io.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/fb.h>
#include <linux/input.h>
#include <math.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#define GF_IOC_MAGIC 'g'
#define GF_IOC_RESET _IO (GF_IOC_MAGIC, 2)
#define GF_IOC_ENABLE_IRQ _IO (GF_IOC_MAGIC, 3)
#define GF_IOC_ENABLE_POWER _IO (GF_IOC_MAGIC, 7)

#define BITS_PER_LONG (sizeof (long) * 8)
#define NLONGS(x) (((x) + BITS_PER_LONG - 1) / BITS_PER_LONG)
#define TEST_BIT(bit, array) ((array[(bit) / BITS_PER_LONG] >> ((bit) % BITS_PER_LONG)) & 1)

static int
open_touchscreen (int *max_x, int *max_y)
{
  DIR *dir = opendir ("/dev/input");
  struct dirent *entry;
  int fd = -1;

  if (!dir)
    return -1;
  while ((entry = readdir (dir)))
    {
      unsigned long absbits[NLONGS (ABS_CNT)] = {0};
      unsigned long props[NLONGS (INPUT_PROP_CNT)] = {0};
      struct input_absinfo ax, ay;
      char path[300];

      if (strncmp (entry->d_name, "event", 5))
        continue;
      snprintf (path, sizeof (path), "/dev/input/%s", entry->d_name);
      fd = open (path, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
      if (fd < 0)
        continue;
      if (ioctl (fd, EVIOCGBIT (EV_ABS, sizeof (absbits)), absbits) >= 0 &&
          ioctl (fd, EVIOCGPROP (sizeof (props)), props) >= 0 &&
          TEST_BIT (ABS_MT_POSITION_X, absbits) && TEST_BIT (ABS_MT_POSITION_Y, absbits) &&
          TEST_BIT (INPUT_PROP_DIRECT, props) &&
          !ioctl (fd, EVIOCGABS (ABS_MT_POSITION_X), &ax) &&
          !ioctl (fd, EVIOCGABS (ABS_MT_POSITION_Y), &ay) &&
          ax.maximum > 0 && ay.maximum > 0)
        {
          *max_x = ax.maximum;
          *max_y = ay.maximum;
          closedir (dir);
          return fd;
        }
      close (fd);
      fd = -1;
    }
  closedir (dir);
  errno = ENODEV;
  return -1;
}

static void
open_framebuffer (struct goodix_oplus_io *io)
{
  struct fb_var_screeninfo var;
  struct fb_fix_screeninfo fix;

  io->fb_fd = open ("/dev/fb0", O_RDWR | O_CLOEXEC);
  if (io->fb_fd < 0)
    return;
  if (ioctl (io->fb_fd, FBIOGET_VSCREENINFO, &var) ||
      ioctl (io->fb_fd, FBIOGET_FSCREENINFO, &fix) || var.bits_per_pixel != 32)
    {
      close (io->fb_fd);
      io->fb_fd = -1;
      return;
    }
  io->fb_w = var.xres;
  io->fb_h = var.yres;
  io->fb_bpp = var.bits_per_pixel;
  io->fb_stride = fix.line_length;
}

int
goodix_oplus_io_open (struct goodix_oplus_io *io, const char *sensor_path)
{
  memset (io, 0, sizeof (*io));
  io->sensor_fd = io->touch_fd = io->fb_fd = -1;
  io->tracking = -1;
  /* OnePlus 8 Pro (instantnoodlep), 1440x3168 panel: sensor at (720, 2547) */
  io->geo.center_x = 0.5;
  io->geo.center_y = 2547.0 / 3168.0;
  io->geo.accept_radius = 0.20;
  io->geo.spot_radius = 190.0 / 1440.0;

  io->sensor_fd = open (sensor_path, O_RDWR | O_CLOEXEC);
  if (io->sensor_fd < 0 ||
      ioctl (io->sensor_fd, GF_IOC_ENABLE_POWER) ||
      ioctl (io->sensor_fd, GF_IOC_RESET) ||
      ioctl (io->sensor_fd, GF_IOC_ENABLE_IRQ))
    goto fail;
  usleep (50000);
  io->touch_fd = open_touchscreen (&io->touch_max_x, &io->touch_max_y);
  if (io->touch_fd < 0)
    goto fail;
  open_framebuffer (io); /* optional */
  return 0;
fail:
  {
    int saved = errno;
    goodix_oplus_io_close (io);
    errno = saved;
  }
  return -1;
}

void
goodix_oplus_io_close (struct goodix_oplus_io *io)
{
  goodix_oplus_io_light (io, false);
  goodix_oplus_io_guide (io, false);
  if (io->fb_fd >= 0) close (io->fb_fd);
  if (io->touch_fd >= 0) close (io->touch_fd);
  if (io->sensor_fd >= 0) close (io->sensor_fd);
  io->fb_fd = io->touch_fd = io->sensor_fd = -1;
}

static bool
on_sensor (struct goodix_oplus_io *io)
{
  double x = (double) io->cur_x / io->touch_max_x - io->geo.center_x;
  double y = ((double) io->cur_y / io->touch_max_y - io->geo.center_y) *
             ((double) io->touch_max_y / io->touch_max_x);

  return io->tracking >= 0 && sqrt (x * x + y * y) <= io->geo.accept_radius;
}

/* Process pending events; returns 1 if a down/up transition of interest occurred. */
static int
pump (struct goodix_oplus_io *io, bool want_down)
{
  struct input_event ev[64];
  ssize_t n;
  int i, transition = 0;

  while ((n = read (io->touch_fd, ev, sizeof (ev))) > 0)
    {
      for (i = 0; i < n / (ssize_t) sizeof (ev[0]); i++)
        {
          if (ev[i].type == EV_ABS && ev[i].code == ABS_MT_TRACKING_ID)
            {
              io->tracking = ev[i].value;
              if (!want_down && ev[i].value < 0)
                transition = 1;
            }
          else if (ev[i].type == EV_ABS && ev[i].code == ABS_MT_POSITION_X)
            io->cur_x = ev[i].value;
          else if (ev[i].type == EV_ABS && ev[i].code == ABS_MT_POSITION_Y)
            io->cur_y = ev[i].value;
          else if (ev[i].type == EV_SYN && ev[i].code == SYN_REPORT && want_down && on_sensor (io))
            transition = 1;
        }
      if (transition)
        return 1;
    }
  if (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK)
    return -1;
  return 0;
}

static int
wait_transition (struct goodix_oplus_io *io, bool down, int timeout_ms)
{
  struct pollfd pfd = { .fd = io->touch_fd, .events = POLLIN };
  int r;

  if (!down && io->tracking < 0)
    return 1;
  r = pump (io, down);
  if (r)
    return r;
  do r = poll (&pfd, 1, timeout_ms); while (r < 0 && errno == EINTR);
  if (r <= 0)
    return r;
  return pump (io, down);
}

int
goodix_oplus_io_wait_down (struct goodix_oplus_io *io, int timeout_ms)
{
  return wait_transition (io, true, timeout_ms);
}

int
goodix_oplus_io_wait_up (struct goodix_oplus_io *io, int timeout_ms)
{
  return wait_transition (io, false, timeout_ms);
}

void
goodix_oplus_io_guide (struct goodix_oplus_io *io, bool on)
{
  int cx, cy, r_out, r_in, y0, y1, y;
  uint8_t *band;

  if (io->fb_fd < 0)
    return;
  if (!on)
    {
      if (io->guide_saved)
        {
          if (pwrite (io->fb_fd, io->guide_saved, io->guide_size, io->guide_off) < 0)
            { /* best effort */ }
          free (io->guide_saved);
          io->guide_saved = NULL;
        }
      return;
    }
  if (io->guide_saved)
    return;
  cx = (int) (io->geo.center_x * io->fb_w);
  cy = (int) (io->geo.center_y * io->fb_h);
  r_out = (int) (io->geo.spot_radius * io->fb_w) + 12;
  r_in = r_out - 14;
  y0 = cy - r_out < 0 ? 0 : cy - r_out;
  y1 = cy + r_out >= (int) io->fb_h ? (int) io->fb_h - 1 : cy + r_out;
  io->guide_off = (size_t) y0 * io->fb_stride;
  io->guide_size = (size_t) (y1 - y0 + 1) * io->fb_stride;
  io->guide_saved = malloc (io->guide_size);
  band = malloc (io->guide_size);
  if (!io->guide_saved || !band ||
      pread (io->fb_fd, io->guide_saved, io->guide_size, io->guide_off) != (ssize_t) io->guide_size)
    {
      free (io->guide_saved);
      io->guide_saved = NULL;
      free (band);
      return;
    }
  memcpy (band, io->guide_saved, io->guide_size);
  for (y = y0; y <= y1; y++)
    {
      int x;
      for (x = cx - r_out; x <= cx + r_out; x++)
        {
          int dx = x - cx, dy = y - cy, d2 = dx * dx + dy * dy;
          if (x < 0 || x >= (int) io->fb_w || d2 > r_out * r_out || d2 < r_in * r_in)
            continue;
          /* XRGB8888: light blue */
          band[(size_t) (y - y0) * io->fb_stride + (size_t) x * 4 + 0] = 0xff;
          band[(size_t) (y - y0) * io->fb_stride + (size_t) x * 4 + 1] = 0xa0;
          band[(size_t) (y - y0) * io->fb_stride + (size_t) x * 4 + 2] = 0x00;
        }
    }
  if (pwrite (io->fb_fd, band, io->guide_size, io->guide_off) < 0)
    { /* best effort */ }
  free (band);
}

void
goodix_oplus_io_light (struct goodix_oplus_io *io, bool on)
{
  int cx, cy, r, y0, y1, y;

  if (io->fb_fd < 0)
    return;
  if (!on)
    {
      if (io->saved)
        {
          if (pwrite (io->fb_fd, io->saved, io->saved_size, io->saved_off) < 0)
            { /* best effort */ }
          free (io->saved);
          io->saved = NULL;
        }
      return;
    }
  if (io->saved)
    return;
  cx = (int) (io->geo.center_x * io->fb_w);
  cy = (int) (io->geo.center_y * io->fb_h);
  r = (int) (io->geo.spot_radius * io->fb_w);
  y0 = cy - r < 0 ? 0 : cy - r;
  y1 = cy + r >= (int) io->fb_h ? (int) io->fb_h - 1 : cy + r;
  io->saved_off = (size_t) y0 * io->fb_stride;
  io->saved_size = (size_t) (y1 - y0 + 1) * io->fb_stride;
  io->saved = malloc (io->saved_size);
  if (!io->saved)
    return;
  if (pread (io->fb_fd, io->saved, io->saved_size, io->saved_off) != (ssize_t) io->saved_size)
    { free (io->saved); io->saved = NULL; return; }
  {
    uint8_t *band = malloc (io->saved_size);
    if (!band)
      return;
    memcpy (band, io->saved, io->saved_size);
    for (y = y0; y <= y1; y++)
      {
        int dy = y - cy, dx = (int) sqrt ((double) r * r - (double) dy * dy), x0, x1;
        x0 = cx - dx < 0 ? 0 : cx - dx;
        x1 = cx + dx >= (int) io->fb_w ? (int) io->fb_w - 1 : cx + dx;
        memset (band + (size_t) (y - y0) * io->fb_stride + (size_t) x0 * 4, 0xff,
                (size_t) (x1 - x0 + 1) * 4);
      }
    /* write() (not mmap) so DRM fbdev emulation flushes the damage */
    if (pwrite (io->fb_fd, band, io->saved_size, io->saved_off) < 0)
      { /* best effort */ }
    free (band);
  }
}
