/* SPDX-License-Identifier: LGPL-2.1-or-later */
#pragma once

#include <stddef.h>
#include <stdint.h>

/* One TEE session (QSEECOM TEE driver, impl id 5) to a named QSEE app. */
struct goodix_oplus_tee {
  int fd;
  uint32_t session;
};

int goodix_oplus_tee_open (struct goodix_oplus_tee *tee, const char *app_name);
void goodix_oplus_tee_close (struct goodix_oplus_tee *tee);

/* OnePlus/Goodix request: 64-byte header + payload (target at +4, command at
 * +8, result at +0xc of the payload, patched in by physical address). */
int goodix_oplus_tee_command (struct goodix_oplus_tee *tee, uint32_t target,
                              uint32_t command, void *payload, size_t size,
                              uint32_t *result);

/* Plain QSEECom_send_cmd style request/response (keymaster64). */
int goodix_oplus_tee_raw (struct goodix_oplus_tee *tee, const void *request,
                          size_t request_size, void *response,
                          size_t response_size);

#define GOODIX_OPLUS_HAT_SIZE 69
#define GOODIX_OPLUS_GK_HANDLE_MAX 256

/* keymaster64 helpers */
int goodix_oplus_km_set_version (struct goodix_oplus_tee *km);
int goodix_oplus_km_auth_key (struct goodix_oplus_tee *km, uint8_t blob[0xa0]);
int goodix_oplus_gk_enroll (struct goodix_oplus_tee *km, uint32_t uid,
                            const uint8_t *password, size_t password_size,
                            uint8_t *handle, size_t *handle_size);
int goodix_oplus_gk_verify (struct goodix_oplus_tee *km, uint32_t uid,
                            uint64_t challenge, const uint8_t *handle,
                            size_t handle_size, const uint8_t *password,
                            size_t password_size,
                            uint8_t hat[GOODIX_OPLUS_HAT_SIZE]);
