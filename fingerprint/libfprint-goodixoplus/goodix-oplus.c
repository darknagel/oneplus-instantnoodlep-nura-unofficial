/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Goodix optical under-display sensor behind the OnePlus/Oplus QSEE TA
 * (OnePlus 8 Pro "instantnoodlep", G5 = gfp9608).  Match-on-chip: images and
 * templates stay inside TrustZone; templates are sealed by the TA and stored
 * through the machine-wide qsee-supplicant (FS/GPFS/RPMB listeners).
 *
 * Protocol recovered from the Android HAL (libgf_hal_G5_oplus.so) and traces.
 */
#define FP_COMPONENT "goodixoplus"

#include "drivers_api.h"
#include "goodix-oplus-io.h"
#include "goodix-oplus-tee.h"

#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <sys/random.h>
#include <sys/stat.h>
#include <unistd.h>

/* targets */
#define T_CORE   1000u
#define T_ALGO   1001u
#define T_SENSOR 1002u

#define GROUP_ID 0u
#define GROUP_PATH "/data/vendor_de/0/fpdata"
#define ENROLL_STAGES 30
#define AUTH_TRIES 4
#define GK_UID 1000u
#define STATE_DIR "/var/lib/goodix-oplus"
#define GK_FILE STATE_DIR "/gatekeeper"
#define GK_PASSWORD_SIZE 32

/* TA result codes */
#define GF_OK 0u
#define GF_BAD_PARAMS 1004u
#define GF_NOT_MATCH 1008u
#define GF_ACQUIRED_PARTIAL 1013u
#define GF_ACQUIRED_DIRTY 1014u
#define GF_DUPLICATE_AREA 1047u

struct _FpiDeviceGoodixOplus
{
  FpDevice parent;
  struct goodix_oplus_io io;
  struct goodix_oplus_tee ta;
  struct goodix_oplus_tee km;
  gchar *ta_name;
  /* set between suspend and resume; the worker pauses instead of failing */
  gint suspended;
};

G_DECLARE_FINAL_TYPE (FpiDeviceGoodixOplus, fpi_device_goodixoplus,
                      FPI, DEVICE_GOODIXOPLUS, FpDevice)
G_DEFINE_TYPE (FpiDeviceGoodixOplus, fpi_device_goodixoplus, FP_TYPE_DEVICE)

static const FpIdEntry id_table[] = {
  { .udev_types = FPI_DEVICE_UDEV_SUBTYPE_MISC,
    .misc_name = "goodix_fp", .misc_compatible = "goodix,gf3626" },
  { .udev_types = 0 }
};

enum work_op { WORK_OPEN, WORK_CLOSE, WORK_LIST, WORK_DELETE, WORK_ENROLL,
               WORK_IDENTIFY, WORK_CLEAR };

struct work { enum work_op op; guint32 finger_id; };

struct finger_list { guint count; guint32 ids[10]; };

struct op_result { guint32 status; guint32 finger_id; };

/* ------------------------------------------------------------------------ */

static GError *
io_error (const char *what)
{
  return g_error_new (G_IO_ERROR, g_io_error_from_errno (errno), "%s: %s",
                      what, g_strerror (errno));
}

static gboolean
cmd (FpiDeviceGoodixOplus *self, guint32 target, guint32 command, guint8 *payload,
     gsize size, guint32 *result, GError **error)
{
  guint32 r = 0;

  if (goodix_oplus_tee_command (&self->ta, target, command, payload, size, &r))
    {
      g_propagate_error (error, io_error ("Goodix TA invoke"));
      return FALSE;
    }
  fp_dbg ("cmd %u/%u size %" G_GSIZE_FORMAT " -> %u", target, command, size, r);
  if (result)
    *result = r;
  else if (r)
    {
      g_set_error (error, G_IO_ERROR, G_IO_ERROR_FAILED,
                   "Goodix command %u/%u failed with %u", target, command, r);
      return FALSE;
    }
  return TRUE;
}

static gboolean
cmd_zero (FpiDeviceGoodixOplus *self, guint32 target, guint32 command, gsize size,
          guint32 *result, GError **error)
{
  g_autofree guint8 *payload = g_malloc0 (size);
  return cmd (self, target, command, payload, size, result, error);
}

static void
put32 (guint8 *p, gsize off, guint32 v)
{
  memcpy (p + off, &v, 4);
}

static guint32
get32 (const guint8 *p, gsize off)
{
  guint32 v;
  memcpy (&v, p + off, 4);
  return v;
}

static gchar *
read_ta_name (FpDevice *device, GError **error)
{
  const gchar *sysfs = fpi_device_get_udev_sysfs_path (device, FPI_DEVICE_UDEV_SUBTYPE_MISC);
  g_autofree gchar *a = NULL, *b = NULL, *c = NULL;
  gchar *contents = NULL;

  if (!sysfs)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_NOT_FOUND, "no sysfs path");
      return NULL;
    }
  a = g_build_filename (sysfs, "firmware_name", NULL);
  b = g_build_filename (sysfs, "device", "firmware_name", NULL);
  c = g_canonicalize_filename ("../firmware_name", sysfs);
  if (!g_file_get_contents (a, &contents, NULL, NULL) &&
      !g_file_get_contents (b, &contents, NULL, NULL) &&
      !g_file_get_contents (c, &contents, NULL, error))
    return NULL;
  g_strstrip (contents);
  /* Only the Oplus Goodix optical TAs speak this protocol. */
  if (!g_str_has_prefix (contents, "gfp96"))
    {
      g_set_error (error, FP_DEVICE_ERROR, FP_DEVICE_ERROR_NOT_SUPPORTED,
                   "TA '%s' is not an Oplus Goodix optical TA", contents);
      g_free (contents);
      return NULL;
    }
  return contents;
}

/* ---- gatekeeper credential (machine-local) ---- */

static gboolean
gk_load_or_create (FpiDeviceGoodixOplus *self, guint8 *password, guint8 *handle,
                   gsize *handle_size, GError **error)
{
  g_autofree gchar *contents = NULL;
  gsize len = 0;
  guint32 hsize;

  if (g_file_get_contents (GK_FILE, &contents, &len, NULL) &&
      len > GK_PASSWORD_SIZE + 4)
    {
      memcpy (password, contents, GK_PASSWORD_SIZE);
      memcpy (&hsize, contents + GK_PASSWORD_SIZE, 4);
      if (hsize && hsize <= GOODIX_OPLUS_GK_HANDLE_MAX &&
          len == GK_PASSWORD_SIZE + 4 + hsize)
        {
          memcpy (handle, contents + GK_PASSWORD_SIZE + 4, hsize);
          *handle_size = hsize;
          return TRUE;
        }
    }

  /* First use: enroll a random machine secret with Gatekeeper. */
  if (getrandom (password, GK_PASSWORD_SIZE, 0) != GK_PASSWORD_SIZE)
    {
      g_propagate_error (error, io_error ("getrandom"));
      return FALSE;
    }
  *handle_size = GOODIX_OPLUS_GK_HANDLE_MAX;
  if (goodix_oplus_gk_enroll (&self->km, GK_UID, password, GK_PASSWORD_SIZE,
                              handle, handle_size))
    {
      g_propagate_error (error, io_error ("Gatekeeper enroll (RPMB listener running?)"));
      return FALSE;
    }
  {
    g_autofree guint8 *blob = g_malloc (GK_PASSWORD_SIZE + 4 + *handle_size);
    guint32 hs = *handle_size;
    memcpy (blob, password, GK_PASSWORD_SIZE);
    memcpy (blob + GK_PASSWORD_SIZE, &hs, 4);
    memcpy (blob + GK_PASSWORD_SIZE + 4, handle, hs);
    if (g_mkdir_with_parents (STATE_DIR, 0700) ||
        !g_file_set_contents_full (GK_FILE, (gchar *) blob, GK_PASSWORD_SIZE + 4 + hs,
                                   G_FILE_SET_CONTENTS_CONSISTENT, 0600, error))
      return FALSE;
  }
  return TRUE;
}

static gboolean
hardware_auth_token (FpiDeviceGoodixOplus *self, guint64 challenge,
                     guint8 hat[GOODIX_OPLUS_HAT_SIZE], GError **error)
{
  guint8 password[GK_PASSWORD_SIZE], handle[GOODIX_OPLUS_GK_HANDLE_MAX];
  gsize handle_size = 0;
  gboolean ok = FALSE;

  if (!gk_load_or_create (self, password, handle, &handle_size, error))
    goto out;
  if (goodix_oplus_gk_verify (&self->km, GK_UID, challenge, handle, handle_size,
                              password, GK_PASSWORD_SIZE, hat))
    {
      g_propagate_error (error, io_error ("Gatekeeper verify"));
      goto out;
    }
  ok = TRUE;
out:
  explicit_bzero (password, sizeof (password));
  return ok;
}

/* ---- TA bring-up ---- */

static gboolean
set_group (FpiDeviceGoodixOplus *self, GError **error)
{
  guint8 payload[288] = {0};
  put32 (payload, 0x1c, GROUP_ID);
  memcpy (payload + 0x20, GROUP_PATH, sizeof (GROUP_PATH));
  return cmd (self, T_CORE, 0, payload, sizeof (payload), NULL, error);
}

static gboolean
bring_up (FpiDeviceGoodixOplus *self, GError **error)
{
  /* Same order as the Android HAL; 1002/9 + 1002/0 are required before the
   * TA's own SPI driver can talk to the sensor. */
  static const struct { guint32 t, c; gsize size; } chain[] = {
    { T_SENSOR, 9, 32 }, { T_SENSOR, 0, 28 }, { T_SENSOR, 1, 44 },
    { T_SENSOR, 2, 272 }, { T_SENSOR, 11, 32 }, { T_ALGO, 0, 40 },
    { T_ALGO, 20, 40 }, { T_SENSOR, 8, 28 }, { T_CORE, 13, 28 },
  };
  guint8 key_blob[0xa0];
  guint8 payload[284] = {0};
  guint i;

  for (i = 0; i < G_N_ELEMENTS (chain); i++)
    if (!cmd_zero (self, chain[i].t, chain[i].c, chain[i].size, NULL, error))
      return FALSE;

  /* HMAC key for hardware auth tokens, wrapped by keymaster for this TA. */
  if (goodix_oplus_tee_open (&self->km, "keymaster64") ||
      goodix_oplus_km_set_version (&self->km) ||
      goodix_oplus_km_auth_key (&self->km, key_blob))
    {
      g_propagate_error (error, io_error ("keymaster64"));
      return FALSE;
    }
  memcpy (payload + 0x20, key_blob, sizeof (key_blob));
  explicit_bzero (key_blob, sizeof (key_blob));
  if (!cmd (self, T_CORE, 10, payload, sizeof (payload), NULL, error))
    return FALSE;
  return set_group (self, error);
}

/* ---- capture ---- */

static void
report_finger (FpiDeviceGoodixOplus *self, FpFingerStatusFlags status);
static gboolean
enumerate (FpiDeviceGoodixOplus *self, struct finger_list *list, GError **error);

static gboolean
capture (FpiDeviceGoodixOplus *self, gboolean enrolling, GError **error)
{
  guint8 p3[56] = {0}, p101[80] = {0};
  guint32 r;

  if (enrolling)
    {
      put32 (p3, 0x1c, 1);
      put32 (p3, 0x20, 1);
    }
  else
    put32 (p3, 0x20, 2);
  put32 (p3, 0x28, 1);
  put32 (p101, 0x20, 1);
  put32 (p101, 0x2c, 0x092c);
  put32 (p101, 0x30, 0x0bbf);
  put32 (p101, 0x34, 0x21c);
  put32 (p101, 0x38, 0x776);
  put32 (p101, 0x3c, 0x42a80000);
  put32 (p101, 0x40, 0x7f);
  if (!cmd_zero (self, T_ALGO, 15, 48, &r, error) ||
      !cmd (self, T_SENSOR, 3, p3, sizeof (p3), NULL, error) ||
      !cmd (self, T_SENSOR, 101, p101, sizeof (p101), NULL, error))
    return FALSE;
  return TRUE;
}

/* Wait for a finger on the sensor area, honouring cancellation. */
static gboolean
wait_finger (FpiDeviceGoodixOplus *self, GCancellable *cancellable, GError **error)
{
  /* fprintd publishes this as "finger-needed"; under a compositor the
   * goodix-fp-overlay session helper draws the ring and the light from it */
  report_finger (self, FP_FINGER_STATUS_NEEDED);
  goodix_oplus_io_guide (&self->io, TRUE);
  for (;;)
    {
      int r;
      if (g_cancellable_set_error_if_cancelled (cancellable, error))
        {
          goodix_oplus_io_guide (&self->io, FALSE);
          return FALSE;
        }
      if (g_atomic_int_get (&self->suspended))
        {
          /* the system sleeps: no capture, and drop the touch that woke it */
          g_usleep (200000);
          goodix_oplus_io_wait_up (&self->io, 0);
          continue;
        }
      r = goodix_oplus_io_wait_down (&self->io, 200);
      if (r < 0)
        {
          goodix_oplus_io_guide (&self->io, FALSE);
          g_propagate_error (error, io_error ("touchscreen"));
          return FALSE;
        }
      if (r > 0)
        {
          /* let the finger settle on the glass before capturing */
          g_usleep (120000);
          goodix_oplus_io_guide (&self->io, FALSE);
          return TRUE;
        }
    }
}

static void
wait_lift (FpiDeviceGoodixOplus *self, GCancellable *cancellable)
{
  gint64 deadline = g_get_monotonic_time () + 5 * G_TIME_SPAN_SECOND;
  while (!g_cancellable_is_cancelled (cancellable) && g_get_monotonic_time () < deadline)
    if (goodix_oplus_io_wait_up (&self->io, 200) != 0)
      break;
}

static GError *
retry_for (guint32 status)
{
  switch (status)
    {
    case GF_ACQUIRED_PARTIAL:
      return fpi_device_retry_new (FP_DEVICE_RETRY_CENTER_FINGER);
    case GF_ACQUIRED_DIRTY:
      return fpi_device_retry_new_msg (FP_DEVICE_RETRY_GENERAL, "Image quality too low");
    case GF_DUPLICATE_AREA:
      return fpi_device_retry_new_msg (FP_DEVICE_RETRY_REMOVE_FINGER,
                                       "Area already captured, move the finger a bit");
    default:
      return fpi_device_retry_new_msg (FP_DEVICE_RETRY_GENERAL, "Goodix status %u", status);
    }
}

struct progress { FpiDeviceGoodixOplus *self; FpFingerStatusFlags finger; gint completed; GError *retry; };

static gboolean
progress_main (gpointer data)
{
  struct progress *p = data;
  fpi_device_report_finger_status (FP_DEVICE (p->self), p->finger);
  if (p->completed >= 0 || p->retry)
    fpi_device_enroll_progress (FP_DEVICE (p->self), MAX (p->completed, 0), NULL,
                                g_steal_pointer (&p->retry));
  g_object_unref (p->self);
  g_free (p);
  return G_SOURCE_REMOVE;
}

static void
queue_progress (FpiDeviceGoodixOplus *self, FpFingerStatusFlags finger, gint completed,
                GError *retry)
{
  struct progress *p = g_new0 (struct progress, 1);
  p->self = g_object_ref (self);
  p->finger = finger;
  p->completed = completed;
  p->retry = retry;
  g_main_context_invoke (NULL, progress_main, p);
}

static void
report_finger (FpiDeviceGoodixOplus *self, FpFingerStatusFlags status)
{
  queue_progress (self, status, -1, NULL);
}

static struct op_result *
do_enroll (FpiDeviceGoodixOplus *self, GCancellable *cancellable, GError **error)
{
  guint8 pre[40] = {0}, start[108] = {0}, hat[GOODIX_OPLUS_HAT_SIZE];
  guint64 challenge;
  guint32 finger_id = 0, remaining = ENROLL_STAGES;
  struct op_result *result = NULL;

  if (!set_group (self, error) ||
      !cmd (self, T_CORE, 2, pre, sizeof (pre), NULL, error))
    return NULL;
  memcpy (&challenge, pre + 0x20, 8);
  if (!hardware_auth_token (self, challenge, hat, error))
    return NULL;
  memcpy (start + 0x21, hat, sizeof (hat));
  if (!cmd (self, T_CORE, 3, start, sizeof (start), NULL, error))
    return NULL;

  while (remaining > 0)
    {
      guint8 p1[56] = {0};
      guint32 status;

      if (!wait_finger (self, cancellable, error))
        goto out;
      report_finger (self, FP_FINGER_STATUS_PRESENT);
      goodix_oplus_io_light (&self->io, TRUE);
      g_usleep (150000); /* light on: framebuffer, or overlay via D-Bus + compositor */
      if (!cmd_zero (self, T_SENSOR, 9, 32, NULL, error) || !capture (self, TRUE, error))
        { goodix_oplus_io_light (&self->io, FALSE); goto out; }
      put32 (p1, 0x34, 0x1c);
      if (!cmd (self, T_ALGO, 1, p1, sizeof (p1), &status, error))
        { goodix_oplus_io_light (&self->io, FALSE); goto out; }
      cmd_zero (self, T_SENSOR, 8, 28, NULL, NULL);
      goodix_oplus_io_light (&self->io, FALSE);
      if (status == GF_OK)
        {
          finger_id = get32 (p1, 0x20) ? get32 (p1, 0x20) : finger_id;
          remaining = get32 (p1, 0x28);
          queue_progress (self, FP_FINGER_STATUS_PRESENT,
                          CLAMP (ENROLL_STAGES - (gint) remaining, 0, ENROLL_STAGES - 1),
                          NULL);
        }
      else
        queue_progress (self, FP_FINGER_STATUS_PRESENT, -1, retry_for (status));
      wait_lift (self, cancellable);
      report_finger (self, FP_FINGER_STATUS_NONE);
    }

  {
    guint8 save[36] = {0};
    put32 (save, 0x20, finger_id);
    if (!finger_id || !cmd (self, T_CORE, 9, save, sizeof (save), NULL, error))
      {
        if (!*error)
          g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_FAILED, "no finger id");
        goto out;
      }
  }
  result = g_new0 (struct op_result, 1);
  result->finger_id = finger_id;
out:
  report_finger (self, FP_FINGER_STATUS_NONE);
  return result;
}

static struct op_result *
do_identify (FpiDeviceGoodixOplus *self, GCancellable *cancellable, GError **error)
{
  struct op_result *result = NULL;
  guint32 status = GF_NOT_MATCH, finger_id = 0;
  guint i;

  struct finger_list enrolled = {0};

  /* With no templates the TA rejects authenticate (1004); still take the
   * touch so callers (e.g. fprintd's duplicate check) get a real no-match. */
  if (!enumerate (self, &enrolled, error))
    return NULL;
  if (!enrolled.count)
    {
      if (!wait_finger (self, cancellable, error))
        return NULL;
      report_finger (self, FP_FINGER_STATUS_PRESENT);
      wait_lift (self, cancellable);
      report_finger (self, FP_FINGER_STATUS_NONE);
      result = g_new0 (struct op_result, 1);
      result->status = GF_NOT_MATCH;
      return result;
    }
  if (!set_group (self, error) || !cmd_zero (self, T_CORE, 1, 40, NULL, error))
    return NULL;
  if (!wait_finger (self, cancellable, error))
    return NULL;
  report_finger (self, FP_FINGER_STATUS_PRESENT);
  goodix_oplus_io_light (&self->io, TRUE);
  g_usleep (150000); /* light on: framebuffer, or overlay via D-Bus + compositor */
  if (!cmd_zero (self, T_SENSOR, 9, 32, NULL, error))
    goto out;
  for (i = 0; i < AUTH_TRIES; i++)
    {
      guint8 p2[176] = {0};
      if (!capture (self, FALSE, error))
        goto out;
      put32 (p2, 0x24, 1);
      put32 (p2, 0x58, 2);
      put32 (p2, 0x88, 1);
      put32 (p2, 0x90, 1);
      put32 (p2, 0x94, 0x1c);
      if (!cmd (self, T_ALGO, 2, p2, sizeof (p2), &status, error))
        goto out;
      if (status == GF_OK)
        {
          finger_id = get32 (p2, 0x30);
          break;
        }
    }
  result = g_new0 (struct op_result, 1);
  result->status = status == GF_BAD_PARAMS ? GF_NOT_MATCH : status;
  result->finger_id = finger_id;
out:
  cmd_zero (self, T_SENSOR, 8, 28, NULL, NULL);
  goodix_oplus_io_light (&self->io, FALSE);
  wait_lift (self, cancellable);
  report_finger (self, FP_FINGER_STATUS_NONE);
  return result;
}

static gboolean
enumerate (FpiDeviceGoodixOplus *self, struct finger_list *list, GError **error)
{
  guint8 p[112] = {0};
  guint i;

  if (!set_group (self, error) || !cmd (self, T_CORE, 7, p, sizeof (p), NULL, error))
    return FALSE;
  list->count = MIN (get32 (p, 0x1c), G_N_ELEMENTS (list->ids));
  for (i = 0; i < list->count; i++)
    list->ids[i] = get32 (p, 0x48 + 4 * i);
  return TRUE;
}

static gboolean
remove_finger (FpiDeviceGoodixOplus *self, guint32 finger_id, GError **error)
{
  guint8 p[120] = {0};
  put32 (p, 0x1c, GROUP_ID);
  put32 (p, 0x20, finger_id);
  return cmd (self, T_CORE, 6, p, sizeof (p), NULL, error);
}

/* ---- worker ---- */

static void
close_all (FpiDeviceGoodixOplus *self)
{
  goodix_oplus_tee_close (&self->km);
  goodix_oplus_tee_close (&self->ta);
  goodix_oplus_io_close (&self->io);
}

static void
worker (GTask *task, gpointer object, gpointer task_data, GCancellable *cancellable)
{
  FpiDeviceGoodixOplus *self = object;
  struct work *w = task_data;
  g_autoptr(GError) error = NULL;

  switch (w->op)
    {
    case WORK_OPEN:
      if (!self->ta_name && !(self->ta_name = read_ta_name (FP_DEVICE (self), &error)))
        break;
      if (goodix_oplus_io_open (&self->io, fpi_device_get_udev_data (FP_DEVICE (self),
                                                FPI_DEVICE_UDEV_SUBTYPE_MISC)))
        { error = io_error ("opening sensor/touchscreen"); break; }
      if (goodix_oplus_tee_open (&self->ta, self->ta_name))
        { error = io_error ("opening Goodix TA (qsee-app-loader running?)"); break; }
      if (!bring_up (self, &error))
        break;
      g_task_return_boolean (task, TRUE);
      return;
    case WORK_CLOSE:
      close_all (self);
      g_task_return_boolean (task, TRUE);
      return;
    case WORK_LIST:
      {
        struct finger_list *list = g_new0 (struct finger_list, 1);
        if (!enumerate (self, list, &error))
          { g_free (list); break; }
        g_task_return_pointer (task, list, g_free);
        return;
      }
    case WORK_DELETE:
      if (!set_group (self, &error) || !remove_finger (self, w->finger_id, &error))
        break;
      g_task_return_boolean (task, TRUE);
      return;
    case WORK_CLEAR:
      {
        struct finger_list list = {0};
        guint i;
        if (!enumerate (self, &list, &error))
          break;
        for (i = 0; i < list.count && !error; i++)
          remove_finger (self, list.ids[i], &error);
        if (error)
          break;
        g_task_return_boolean (task, TRUE);
        return;
      }
    case WORK_ENROLL:
    case WORK_IDENTIFY:
      {
        struct op_result *r = w->op == WORK_ENROLL ? do_enroll (self, cancellable, &error)
                                                   : do_identify (self, cancellable, &error);
        if (!r)
          break;
        g_task_return_pointer (task, r, g_free);
        return;
      }
    }
  if (w->op == WORK_OPEN)
    close_all (self);
  g_task_return_error (task, g_steal_pointer (&error));
}

static void
start (FpiDeviceGoodixOplus *self, enum work_op op, guint32 finger_id,
       GAsyncReadyCallback cb)
{
  g_autoptr(GTask) task = g_task_new (self,
      (op == WORK_OPEN || op == WORK_CLOSE) ? NULL :
      fpi_device_get_cancellable (FP_DEVICE (self)), cb, NULL);
  struct work *w = g_new0 (struct work, 1);
  w->op = op;
  w->finger_id = finger_id;
  g_task_set_task_data (task, w, g_free);
  g_task_run_in_thread (task, worker);
}

static FpPrint *
make_print (FpiDeviceGoodixOplus *self, FpPrint *print, guint32 finger_id)
{
  if (!print)
    print = fp_print_new (FP_DEVICE (self));
  fpi_print_set_type (print, FPI_PRINT_RAW);
  fpi_print_set_device_stored (print, TRUE);
  g_object_set (print, "fpi-data", g_variant_new ("(uu)", GROUP_ID, finger_id), NULL);
  return print;
}

static gboolean
print_finger (FpPrint *print, guint32 *finger_id)
{
  g_autoptr(GVariant) data = NULL;
  guint32 group;
  g_object_get (print, "fpi-data", &data, NULL);
  if (!data || !g_variant_is_of_type (data, G_VARIANT_TYPE ("(uu)")))
    return FALSE;
  g_variant_get (data, "(uu)", &group, finger_id);
  return group == GROUP_ID;
}

static void
open_done (GObject *o, GAsyncResult *r, gpointer u)
{
  GError *e = NULL;
  g_task_propagate_boolean (G_TASK (r), &e);
  fpi_device_open_complete (FP_DEVICE (o), e);
}

static void
close_done (GObject *o, GAsyncResult *r, gpointer u)
{
  GError *e = NULL;
  g_task_propagate_boolean (G_TASK (r), &e);
  fpi_device_close_complete (FP_DEVICE (o), e);
}

static void
delete_done (GObject *o, GAsyncResult *r, gpointer u)
{
  GError *e = NULL;
  g_task_propagate_boolean (G_TASK (r), &e);
  fpi_device_delete_complete (FP_DEVICE (o), e);
}

static void
clear_done (GObject *o, GAsyncResult *r, gpointer u)
{
  GError *e = NULL;
  g_task_propagate_boolean (G_TASK (r), &e);
  fpi_device_clear_storage_complete (FP_DEVICE (o), e);
}

static void
list_done (GObject *o, GAsyncResult *r, gpointer u)
{
  FpiDeviceGoodixOplus *self = FPI_DEVICE_GOODIXOPLUS (o);
  GError *e = NULL;
  g_autofree struct finger_list *list = g_task_propagate_pointer (G_TASK (r), &e);
  GPtrArray *prints;
  guint i;

  if (!list)
    {
      fpi_device_list_complete (FP_DEVICE (o), NULL, e);
      return;
    }
  prints = g_ptr_array_new_with_free_func (g_object_unref);
  for (i = 0; i < list->count; i++)
    g_ptr_array_add (prints, g_object_ref_sink (make_print (self, NULL, list->ids[i])));
  fpi_device_list_complete (FP_DEVICE (o), prints, NULL);
}

static void
enroll_done (GObject *o, GAsyncResult *r, gpointer u)
{
  FpiDeviceGoodixOplus *self = FPI_DEVICE_GOODIXOPLUS (o);
  GError *e = NULL;
  g_autofree struct op_result *res = g_task_propagate_pointer (G_TASK (r), &e);
  FpPrint *print = NULL;

  if (!res)
    {
      fpi_device_enroll_complete (FP_DEVICE (o), NULL, e);
      return;
    }
  fpi_device_get_enroll_data (FP_DEVICE (o), &print);
  make_print (self, print, res->finger_id);
  fpi_device_enroll_complete (FP_DEVICE (o), g_object_ref (print), NULL);
}

static void
identify_done (GObject *o, GAsyncResult *r, gpointer u)
{
  FpiDeviceGoodixOplus *self = FPI_DEVICE_GOODIXOPLUS (o);
  GError *e = NULL;
  g_autofree struct op_result *res = g_task_propagate_pointer (G_TASK (r), &e);
  GPtrArray *gallery = NULL;
  FpPrint *match = NULL;
  g_autoptr(FpPrint) scan = NULL;
  guint i;

  if (!res)
    {
      fpi_device_identify_complete (FP_DEVICE (o), e);
      return;
    }
  if (res->status != GF_OK && res->status != GF_NOT_MATCH)
    {
      fpi_device_identify_report (FP_DEVICE (o), NULL, NULL, retry_for (res->status));
      fpi_device_identify_complete (FP_DEVICE (o), NULL);
      return;
    }
  if (res->status == GF_OK)
    {
      scan = g_object_ref_sink (make_print (self, NULL, res->finger_id));
      fpi_device_get_identify_data (FP_DEVICE (o), &gallery);
      for (i = 0; gallery && i < gallery->len; i++)
        {
          guint32 fid;
          if (print_finger (g_ptr_array_index (gallery, i), &fid) && fid == res->finger_id)
            {
              match = g_ptr_array_index (gallery, i);
              break;
            }
        }
    }
  fpi_device_identify_report (FP_DEVICE (o), match, scan, NULL);
  fpi_device_identify_complete (FP_DEVICE (o), NULL);
}

static void dev_open (FpDevice *d) { start (FPI_DEVICE_GOODIXOPLUS (d), WORK_OPEN, 0, open_done); }
static void dev_close (FpDevice *d) { start (FPI_DEVICE_GOODIXOPLUS (d), WORK_CLOSE, 0, close_done); }
static void dev_list (FpDevice *d) { start (FPI_DEVICE_GOODIXOPLUS (d), WORK_LIST, 0, list_done); }
static void dev_enroll (FpDevice *d) { start (FPI_DEVICE_GOODIXOPLUS (d), WORK_ENROLL, 0, enroll_done); }
static void dev_identify (FpDevice *d) { start (FPI_DEVICE_GOODIXOPLUS (d), WORK_IDENTIFY, 0, identify_done); }
static void dev_clear (FpDevice *d) { start (FPI_DEVICE_GOODIXOPLUS (d), WORK_CLEAR, 0, clear_done); }

static void
dev_delete (FpDevice *d)
{
  FpPrint *print = NULL;
  guint32 fid;

  fpi_device_get_delete_data (d, &print);
  if (!print_finger (print, &fid))
    {
      fpi_device_delete_complete (d, fpi_device_error_new (FP_DEVICE_ERROR_DATA_INVALID));
      return;
    }
  start (FPI_DEVICE_GOODIXOPLUS (d), WORK_DELETE, fid, delete_done);
}

static void
dev_cancel (FpDevice *d)
{
  /* the worker polls the action's cancellable */
}

/* Without these, libfprint cancels a running verify when the system goes to
 * sleep (fprintd's logind sleep handling), so the lock screen's fingerprint
 * prompt is gone after a resume. The TA and the sensor keep their state over
 * s2idle; the waiting worker only pauses. */
static void
dev_suspend (FpDevice *d)
{
  g_atomic_int_set (&FPI_DEVICE_GOODIXOPLUS (d)->suspended, 1);
  fpi_device_suspend_complete (d, NULL);
}

static void
dev_resume (FpDevice *d)
{
  g_atomic_int_set (&FPI_DEVICE_GOODIXOPLUS (d)->suspended, 0);
  fpi_device_resume_complete (d, NULL);
}

static void
dev_probe (FpDevice *d)
{
  FpiDeviceGoodixOplus *self = FPI_DEVICE_GOODIXOPLUS (d);
  GError *error = NULL;
  g_autofree gchar *id = NULL;

  self->ta_name = read_ta_name (d, &error);
  if (self->ta_name)
    id = g_strdup_printf ("oplus:%s", self->ta_name);
  fpi_device_probe_complete (d, id, NULL, error);
}

static void
fpi_device_goodixoplus_init (FpiDeviceGoodixOplus *self)
{
  self->io.sensor_fd = self->io.touch_fd = self->io.fb_fd = -1;
  self->ta.fd = self->km.fd = -1;
}

static void
fpi_device_goodixoplus_finalize (GObject *object)
{
  FpiDeviceGoodixOplus *self = FPI_DEVICE_GOODIXOPLUS (object);
  g_clear_pointer (&self->ta_name, g_free);
  G_OBJECT_CLASS (fpi_device_goodixoplus_parent_class)->finalize (object);
}

static void
fpi_device_goodixoplus_class_init (FpiDeviceGoodixOplusClass *klass)
{
  GObjectClass *object_class = G_OBJECT_CLASS (klass);
  FpDeviceClass *dc = FP_DEVICE_CLASS (klass);

  object_class->finalize = fpi_device_goodixoplus_finalize;
  dc->id = FP_COMPONENT;
  dc->full_name = "Goodix optical under-display sensor (Oplus QSEE TA)";
  dc->type = FP_DEVICE_TYPE_UDEV;
  dc->id_table = id_table;
  dc->scan_type = FP_SCAN_TYPE_PRESS;
  dc->nr_enroll_stages = ENROLL_STAGES;
  dc->temp_hot_seconds = -1;
  dc->open = dev_open;
  dc->probe = dev_probe;
  dc->close = dev_close;
  dc->list = dev_list;
  dc->delete = dev_delete;
  dc->clear_storage = dev_clear;
  dc->enroll = dev_enroll;
  dc->identify = dev_identify;
  dc->cancel = dev_cancel;
  dc->suspend = dev_suspend;
  dc->resume = dev_resume;
  fpi_device_class_auto_initialize_features (dc);
}
