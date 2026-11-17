/* Send a raw QSEE command (plain QSEECom_send_cmd style: request + response
 * buffer, no ION patching) to an already loaded TA via wrobelda's QSEECOM TEE.
 * Usage: rawcmd TA_NAME RSP_SIZE HEXWORD32 [HEXWORD32 ...]
 * Writes the response to stdout as hex and to $OUT (binary) if set. */
#include <errno.h>
#include <fcntl.h>
#include <linux/tee.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

struct shm { int id; uint8_t *data; size_t size; };

static int shm_alloc(int fd, size_t size, struct shm *s)
{
	struct tee_ioctl_shm_alloc_data d = { .size = size };
	int sfd = ioctl(fd, TEE_IOC_SHM_ALLOC, &d);
	if (sfd < 0) return -1;
	s->data = mmap(NULL, d.size, PROT_READ | PROT_WRITE, MAP_SHARED, sfd, 0);
	close(sfd);
	if (s->data == MAP_FAILED) return -1;
	s->id = d.id; s->size = d.size; memset(s->data, 0, s->size);
	return 0;
}

int main(int argc, char **argv)
{
	if (argc < 4) { fprintf(stderr, "usage: %s TA RSP_SIZE WORD...\n", argv[0]); return 2; }
	const char *ta = argv[1];
	size_t rsize = strtoul(argv[2], NULL, 0);
	size_t qsize = (size_t)(argc - 3) * 4;
	uint8_t reqfile[8192]; size_t reqlen = 0;
	if (getenv("REQ")) {
		FILE *f = fopen(getenv("REQ"), "rb");
		if (!f) { perror("REQ"); return 1; }
		reqlen = fread(reqfile, 1, sizeof reqfile, f);
		fclose(f);
		qsize = reqlen;
	}
	int fd = -1;
	struct tee_ioctl_version_data v;
	for (int i = 0; i < 8 && fd < 0; i++) {
		char p[32]; snprintf(p, sizeof p, "/dev/tee%d", i);
		fd = open(p, O_RDWR);
		if (fd < 0) continue;
		if (ioctl(fd, TEE_IOC_VERSION, &v) || v.impl_id != 5) { close(fd); fd = -1; }
	}
	if (fd < 0) { perror("no qseecom tee"); return 1; }

	struct shm name, req, rsp;
	if (shm_alloc(fd, 64, &name) || shm_alloc(fd, qsize, &req) || shm_alloc(fd, rsize, &rsp)) { perror("shm"); return 1; }
	strcpy((char *)name.data, ta);
	struct { struct tee_ioctl_open_session_arg a; struct tee_ioctl_param p[1]; } os = {0};
	os.a.num_params = 1;
	os.p[0].attr = TEE_IOCTL_PARAM_ATTR_TYPE_MEMREF_INPUT;
	os.p[0].b = strlen(ta) + 1; os.p[0].c = name.id;
	struct tee_ioctl_buf_data bd = { (uintptr_t)&os, sizeof os };
	if (ioctl(fd, TEE_IOC_OPEN_SESSION, &bd) || os.a.ret) {
		printf("open_session %s: errno %d (%s) ret 0x%x origin %u\n", ta, errno, strerror(errno), os.a.ret, os.a.ret_origin);
		return 1;
	}
	printf("session %u to %s\n", os.a.session, ta);
	if (reqlen)
		memcpy(req.data, reqfile, reqlen);
	else
		for (int i = 3; i < argc; i++) {
			uint32_t w = strtoul(argv[i], NULL, 0);
			memcpy(req.data + (i - 3) * 4, &w, 4);
		}
	struct { struct tee_ioctl_invoke_arg a; struct tee_ioctl_param p[2]; } iv = {0};
	iv.a.session = os.a.session; iv.a.num_params = 2;
	iv.p[0].attr = TEE_IOCTL_PARAM_ATTR_TYPE_MEMREF_INPUT; iv.p[0].b = qsize; iv.p[0].c = req.id;
	iv.p[1].attr = TEE_IOCTL_PARAM_ATTR_TYPE_MEMREF_OUTPUT; iv.p[1].b = rsize; iv.p[1].c = rsp.id;
	struct tee_ioctl_buf_data bi = { (uintptr_t)&iv, sizeof iv };
	int r = ioctl(fd, TEE_IOC_INVOKE, &bi);
	printf("invoke: rc %d errno %d ret 0x%x origin %u\n", r, r ? errno : 0, iv.a.ret, iv.a.ret_origin);
	printf("rsp:");
	for (size_t i = 0; i < rsize; i++) printf("%s%02x", i % 16 ? " " : "\n  ", rsp.data[i]);
	printf("\n");
	if (getenv("OUT")) {
		FILE *f = fopen(getenv("OUT"), "wb");
		if (f) { fwrite(rsp.data, 1, rsize, f); fclose(f); }
	}
	return 0;
}
