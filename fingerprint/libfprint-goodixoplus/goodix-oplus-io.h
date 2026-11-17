/* SPDX-License-Identifier: LGPL-2.1-or-later */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Sensor position on the panel as fractions of width/height. */
struct goodix_oplus_geometry {
  double center_x, center_y; /* sensor centre */
  double accept_radius;      /* touches within this (fraction of width) count */
  double spot_radius;        /* illuminated disk radius (fraction of width) */
};

struct goodix_oplus_io {
  int sensor_fd;   /* /dev/goodix_fp */
  int touch_fd;    /* direct multitouch evdev */
  int touch_max_x, touch_max_y;
  int fb_fd;       /* /dev/fb0 or -1 */
  uint32_t fb_w, fb_h, fb_stride, fb_bpp;
  uint8_t *saved;  /* framebuffer band under the spot */
  size_t saved_size, saved_off;
  uint8_t *guide_saved; /* framebuffer band under the guide ring */
  size_t guide_size, guide_off;
  struct goodix_oplus_geometry geo;
  /* touch tracking state */
  int cur_x, cur_y, tracking;
};

int goodix_oplus_io_open (struct goodix_oplus_io *io, const char *sensor_path);
void goodix_oplus_io_close (struct goodix_oplus_io *io);

/* Wait (up to timeout_ms) for a finger to go down on the sensor area.
 * Returns 1 when down, 0 on timeout, -1 on error. */
int goodix_oplus_io_wait_down (struct goodix_oplus_io *io, int timeout_ms);
/* Wait for the finger to lift; 1 lifted, 0 timeout, -1 error. */
int goodix_oplus_io_wait_up (struct goodix_oplus_io *io, int timeout_ms);

void goodix_oplus_io_light (struct goodix_oplus_io *io, bool on);
/* Ring marking the sensor while waiting for a finger. */
void goodix_oplus_io_guide (struct goodix_oplus_io *io, bool on);
