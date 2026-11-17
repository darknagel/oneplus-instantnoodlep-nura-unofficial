/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix-oplus-tee.h"

#include <errno.h>
#include <fcntl.h>
#include <linux/tee.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define QSEECOM_IMPL_ID 5u

struct shm { int id; uint8_t *data; size_t size; };

static int
shm_alloc (int fd, size_t size, struct shm *s)
{
  struct tee_ioctl_shm_alloc_data d = { .size = size };
  int sfd = ioctl (fd, TEE_IOC_SHM_ALLOC, &d);

  s->data = NULL;
  if (sfd < 0)
    return -1;
  s->data = mmap (NULL, d.size, PROT_READ | PROT_WRITE, MAP_SHARED, sfd, 0);
  close (sfd);
  if (s->data == MAP_FAILED)
    { s->data = NULL; return -1; }
  s->id = d.id;
  s->size = d.size;
  memset (s->data, 0, s->size);
  return 0;
}

static void
shm_free (struct shm *s)
{
  if (s->data)
    munmap (s->data, s->size);
  s->data = NULL;
}

static int
open_client (void)
{
  struct tee_ioctl_version_data version;
  char path[32];
  int i, fd;

  for (i = 0; i < 8; i++)
    {
      snprintf (path, sizeof (path), "/dev/tee%d", i);
      fd = open (path, O_RDWR | O_CLOEXEC);
      if (fd < 0)
        continue;
      if (!ioctl (fd, TEE_IOC_VERSION, &version) && version.impl_id == QSEECOM_IMPL_ID)
        return fd;
      close (fd);
    }
  errno = ENODEV;
  return -1;
}

int
goodix_oplus_tee_open (struct goodix_oplus_tee *tee, const char *app_name)
{
  struct {
    struct tee_ioctl_open_session_arg arg;
    struct tee_ioctl_param params[1];
  } request = {0};
  struct tee_ioctl_buf_data data;
  struct shm name = {0};
  int saved;

  tee->fd = -1;
  tee->session = 0;
  if (!app_name || strlen (app_name) >= 64)
    { errno = EINVAL; return -1; }
  tee->fd = open_client ();
  if (tee->fd < 0 || shm_alloc (tee->fd, 64, &name))
    goto fail;
  memcpy (name.data, app_name, strlen (app_name) + 1);
  request.arg.num_params = 1;
  request.params[0].attr = TEE_IOCTL_PARAM_ATTR_TYPE_MEMREF_INPUT;
  request.params[0].b = strlen (app_name) + 1;
  request.params[0].c = name.id;
  data.buf_ptr = (uintptr_t) &request;
  data.buf_len = sizeof (request);
  if (ioctl (tee->fd, TEE_IOC_OPEN_SESSION, &data) || request.arg.ret)
    { if (!errno) errno = EIO; goto fail; }
  tee->session = request.arg.session;
  shm_free (&name);
  return 0;
fail:
  saved = errno;
  shm_free (&name);
  if (tee->fd >= 0)
    close (tee->fd);
  tee->fd = -1;
  errno = saved;
  return -1;
}

void
goodix_oplus_tee_close (struct goodix_oplus_tee *tee)
{
  if (tee->fd < 0)
    return;
  if (tee->session)
    {
      struct tee_ioctl_close_session_arg arg = { .session = tee->session };
      ioctl (tee->fd, TEE_IOC_CLOSE_SESSION, &arg);
    }
  close (tee->fd);
  tee->fd = -1;
  tee->session = 0;
}

static uint64_t
ms_of_day (void)
{
  struct timespec now;
  struct tm local;
  time_t seconds;

  if (clock_gettime (CLOCK_REALTIME, &now))
    return 0;
  seconds = now.tv_sec;
  if (!localtime_r (&seconds, &local))
    return 0;
  return ((uint64_t) local.tm_hour * 3600 + local.tm_min * 60 + local.tm_sec) * 1000 +
         now.tv_nsec / 1000000;
}

int
goodix_oplus_tee_command (struct goodix_oplus_tee *tee, uint32_t target,
                          uint32_t command, void *payload, size_t size,
                          uint32_t *result)
{
  struct {
    struct tee_ioctl_invoke_arg arg;
    struct tee_ioctl_param params[4];
  } request = {0};
  struct tee_ioctl_buf_data data;
  struct shm req = {0}, rsp = {0}, body = {0};
  uint64_t ms = ms_of_day ();
  uint32_t value;
  int rc = -1, saved;

  if (tee->fd < 0 || !payload || size < 0x10 || size > 0x100000)
    { errno = EINVAL; return -1; }
  if (shm_alloc (tee->fd, 64, &req) || shm_alloc (tee->fd, 64, &rsp) ||
      shm_alloc (tee->fd, size, &body))
    goto out;
  value = (uint32_t) size; memcpy (req.data + 0x08, &value, 4);
  value = 1; memcpy (req.data + 0x0c, &value, 4);
  memcpy (req.data + 0x10, &ms, 8);
  memcpy (body.data, payload, size);
  memcpy (body.data + 4, &target, 4);
  memcpy (body.data + 8, &command, 4);

  request.arg.session = tee->session;
  request.arg.num_params = 4;
  request.params[0].attr = TEE_IOCTL_PARAM_ATTR_TYPE_MEMREF_INPUT;
  request.params[0].b = 64; request.params[0].c = req.id;
  request.params[1].attr = TEE_IOCTL_PARAM_ATTR_TYPE_MEMREF_OUTPUT;
  request.params[1].b = 64; request.params[1].c = rsp.id;
  /* value param: patch the payload physical address (width 8) at req+0 */
  request.params[2].attr = TEE_IOCTL_PARAM_ATTR_TYPE_VALUE_INPUT;
  request.params[2].a = 0; request.params[2].b = 8;
  request.params[3].attr = TEE_IOCTL_PARAM_ATTR_TYPE_MEMREF_INOUT;
  request.params[3].b = size; request.params[3].c = body.id;
  data.buf_ptr = (uintptr_t) &request;
  data.buf_len = sizeof (request);
  if (ioctl (tee->fd, TEE_IOC_INVOKE, &data) || request.arg.ret)
    { if (!errno) errno = EIO; goto out; }
  memcpy (&value, rsp.data + 0x1c, 4);
  if (value)
    { errno = EIO; goto out; }
  memcpy (payload, body.data, size);
  if (result)
    memcpy (result, body.data + 0xc, 4);
  rc = 0;
out:
  saved = errno;
  shm_free (&body);
  shm_free (&rsp);
  shm_free (&req);
  errno = saved;
  return rc;
}

int
goodix_oplus_tee_raw (struct goodix_oplus_tee *tee, const void *request_buf,
                      size_t request_size, void *response, size_t response_size)
{
  struct {
    struct tee_ioctl_invoke_arg arg;
    struct tee_ioctl_param params[2];
  } request = {0};
  struct tee_ioctl_buf_data data;
  struct shm req = {0}, rsp = {0};
  int rc = -1, saved;

  if (tee->fd < 0)
    { errno = EINVAL; return -1; }
  if (shm_alloc (tee->fd, request_size, &req) || shm_alloc (tee->fd, response_size, &rsp))
    goto out;
  memcpy (req.data, request_buf, request_size);
  request.arg.session = tee->session;
  request.arg.num_params = 2;
  request.params[0].attr = TEE_IOCTL_PARAM_ATTR_TYPE_MEMREF_INPUT;
  request.params[0].b = request_size; request.params[0].c = req.id;
  request.params[1].attr = TEE_IOCTL_PARAM_ATTR_TYPE_MEMREF_OUTPUT;
  request.params[1].b = response_size; request.params[1].c = rsp.id;
  data.buf_ptr = (uintptr_t) &request;
  data.buf_len = sizeof (request);
  if (ioctl (tee->fd, TEE_IOC_INVOKE, &data) || request.arg.ret)
    { if (!errno) errno = EIO; goto out; }
  memcpy (response, rsp.data, response_size);
  rc = 0;
out:
  saved = errno;
  shm_free (&rsp);
  shm_free (&req);
  errno = saved;
  return rc;
}

/* ---- keymaster64 / gatekeeper (QTI legacy format) ---- */

#define KM_GET_VERSION 0x200u
#define KM_SET_VERSION 0x207u
#define KM_GET_AUTH_TOKEN_KEY 0x205u
#define GK_ENROLL 0x1001u
#define GK_VERIFY 0x1002u

int
goodix_oplus_km_set_version (struct goodix_oplus_tee *km)
{
  uint32_t req[6] = { KM_SET_VERSION, 4, 5, 4, 5, 0 };
  int32_t rsp[4] = {0};

  if (goodix_oplus_tee_raw (km, req, sizeof (req), rsp, sizeof (rsp)))
    return -1;
  if (rsp[0])
    { errno = EIO; return -1; }
  return 0;
}

int
goodix_oplus_km_auth_key (struct goodix_oplus_tee *km, uint8_t blob[0xa0])
{
  uint32_t req[2] = { KM_GET_AUTH_TOKEN_KEY, 2 };
  uint8_t rsp[256] = {0};
  int32_t status;

  if (goodix_oplus_tee_raw (km, req, sizeof (req), rsp, sizeof (rsp)))
    return -1;
  memcpy (&status, rsp, 4);
  if (status)
    { errno = EIO; return -1; }
  memcpy (blob, rsp + 4, 0xa0);
  return 0;
}

static size_t
gk_build (uint8_t *buffer, uint32_t command, uint32_t uid, uint64_t word,
          const uint8_t *handle, size_t handle_size, uint32_t pw_slot,
          const uint8_t *password, size_t password_size)
{
  size_t off = 0x20;
  uint32_t value;

  memset (buffer, 0, 0x20);
  memcpy (buffer, &command, 4);
  memcpy (buffer + 4, &uid, 4);
  if (word)
    memcpy (buffer + 8, &word, 8);
  if (handle && handle_size)
    {
      value = off; memcpy (buffer + 0x10, &value, 4);
      value = handle_size; memcpy (buffer + 0x14, &value, 4);
      memcpy (buffer + off, handle, handle_size);
      off += handle_size;
    }
  value = off; memcpy (buffer + pw_slot, &value, 4);
  value = password_size; memcpy (buffer + pw_slot + 4, &value, 4);
  memcpy (buffer + off, password, password_size);
  return off + password_size;
}

static int
gk_call (struct goodix_oplus_tee *km, const uint8_t *request, size_t size,
         uint8_t *out, size_t *out_size)
{
  uint8_t rsp[0x1000];
  int32_t status;
  uint32_t off, len;

  if (goodix_oplus_tee_raw (km, request, size, rsp, sizeof (rsp)))
    return -1;
  memcpy (&status, rsp, 4);
  memcpy (&off, rsp + 4, 4);
  memcpy (&len, rsp + 8, 4);
  if (status || off > sizeof (rsp) || len > sizeof (rsp) - off || len > *out_size)
    { errno = EIO; return -1; }
  memcpy (out, rsp + off, len);
  *out_size = len;
  return 0;
}

int
goodix_oplus_gk_enroll (struct goodix_oplus_tee *km, uint32_t uid,
                        const uint8_t *password, size_t password_size,
                        uint8_t *handle, size_t *handle_size)
{
  uint8_t request[0x200];
  size_t size;

  if (password_size > 0x100)
    { errno = EINVAL; return -1; }
  size = gk_build (request, GK_ENROLL, uid, 0, NULL, 0, 0x18, password, password_size);
  return gk_call (km, request, size, handle, handle_size);
}

int
goodix_oplus_gk_verify (struct goodix_oplus_tee *km, uint32_t uid,
                        uint64_t challenge, const uint8_t *handle,
                        size_t handle_size, const uint8_t *password,
                        size_t password_size, uint8_t hat[GOODIX_OPLUS_HAT_SIZE])
{
  uint8_t request[0x400];
  size_t size, hat_size = GOODIX_OPLUS_HAT_SIZE;

  if (password_size > 0x100 || handle_size > GOODIX_OPLUS_GK_HANDLE_MAX)
    { errno = EINVAL; return -1; }
  size = gk_build (request, GK_VERIFY, uid, challenge, handle, handle_size, 0x18,
                   password, password_size);
  if (gk_call (km, request, size, hat, &hat_size))
    return -1;
  if (hat_size != GOODIX_OPLUS_HAT_SIZE)
    { errno = EIO; return -1; }
  return 0;
}
