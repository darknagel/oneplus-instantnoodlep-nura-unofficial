/* OnePlus/Goodix (Delmar) TA command test over the QSEECOM TEE driver.
 * Request layout reverse-engineered from goodix::CaEntry::sendCommand in
 * libgf_hal_19811_G6_oplus.so:
 *   64-byte request: +0x00 payload phys (patched by kernel), +0x08 payload
 *   size, +0x0c token, +0x10 ms of day, +0x18 dump level, +0x1c status (out),
 *   +0x20 carveout phys, +0x28 carveout len.
 *   payload: +0x04 target, +0x08 cmd id, +0x0c result (out), command data.
 * Usage: optest TARGET CMD PAYLOAD_SIZE [WIDTH]  (WIDTH of address patch, 4/8) */
#include <errno.h>
#include <fcntl.h>
#include <linux/tee.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
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

static void dump(const char *t, const uint8_t *p, size_t n)
{
	printf("%s:", t);
	for (size_t i = 0; i < n; i++) printf("%s%02x", i % 16 ? " " : "\n  ", p[i]);
	printf("\n");
}

int main(int argc, char **argv)
{
	if (argc < 4) { fprintf(stderr, "usage: %s TARGET CMD SIZE [WIDTH]\n", argv[0]); return 2; }
	uint32_t target = strtoul(argv[1], NULL, 0), cmd = strtoul(argv[2], NULL, 0);
	size_t psize = strtoul(argv[3], NULL, 0);
	int width = argc > 4 ? atoi(argv[4]) : 8;
	int fd = -1;
	struct tee_ioctl_version_data v;
	for (int i = 0; i < 8 && fd < 0; i++) {
		char p[32]; snprintf(p, sizeof p, "/dev/tee%d", i);
		fd = open(p, O_RDWR);
		if (fd < 0) continue;
		if (ioctl(fd, TEE_IOC_VERSION, &v) || v.impl_id != 5) { close(fd); fd = -1; }
	}
	if (fd < 0) { perror("no qseecom tee"); return 1; }

	if (!getenv("NOPOWER")) {
		int gfd = open("/dev/goodix_fp", O_RDWR);
		if (gfd < 0) { perror("/dev/goodix_fp"); return 1; }
		ioctl(gfd, _IO('g', 7)); ioctl(gfd, _IO('g', 2)); ioctl(gfd, _IO('g', 3));
		usleep(50000);
	} else {
		printf("NOPOWER: sensor left unpowered\n");
	}
	if (getenv("HOLD")) {
		printf("holding %s s before invoke\n", getenv("HOLD"));
		fflush(stdout);
		sleep(atoi(getenv("HOLD")));
	}

	struct shm name, req, rsp, body;
	if (shm_alloc(fd, 64, &name)) { perror("shm"); return 1; }
	const char *ta = getenv("TA") ? getenv("TA") : "gfp9608";
	strcpy((char *)name.data, ta);
	struct { struct tee_ioctl_open_session_arg a; struct tee_ioctl_param p[1]; } os = {0};
	os.a.num_params = 1;
	os.p[0].attr = TEE_IOCTL_PARAM_ATTR_TYPE_MEMREF_INPUT;
	os.p[0].b = strlen(ta) + 1; os.p[0].c = name.id;
	struct tee_ioctl_buf_data bd = { (uintptr_t)&os, sizeof os };
	if (ioctl(fd, TEE_IOC_OPEN_SESSION, &bd) || os.a.ret) {
		printf("open_session: errno %d ret 0x%x\n", errno, os.a.ret); return 1;
	}

	/* LOG=level: append the HAL's 0x8000-byte TA log area after the payload */
	uint32_t loglevel = getenv("LOG") ? strtoul(getenv("LOG"), NULL, 0) : 0;
	size_t bsize = psize + (loglevel ? 0x8000 : 0);
	if (shm_alloc(fd, 64, &req) || shm_alloc(fd, 64, &rsp) || shm_alloc(fd, bsize, &body)) { perror("shm"); return 1; }
	memcpy(req.data + 0x18, &loglevel, 4);
	struct timespec now; clock_gettime(CLOCK_REALTIME, &now);
	struct tm lt; localtime_r(&now.tv_sec, &lt);
	uint64_t ms = ((uint64_t)lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec) * 1000 + now.tv_nsec / 1000000;
	uint32_t val = psize; memcpy(req.data + 0x08, &val, 4);
	val = 1; memcpy(req.data + 0x0c, &val, 4);
	memcpy(req.data + 0x10, &ms, 8);
	/* PAYLOAD=file: preload payload bytes from a file (target/cmd still forced) */
	if (getenv("PAYLOAD")) {
		FILE *pf = fopen(getenv("PAYLOAD"), "rb");
		if (!pf) { perror("PAYLOAD"); return 1; }
		size_t got = fread(body.data, 1, psize, pf);
		fclose(pf);
		printf("payload preloaded: %zu bytes\n", got);
	}
	memcpy(body.data + 4, &target, 4);
	memcpy(body.data + 8, &cmd, 4);
	/* SET="off:b|w:val,..." sets bytes/words in the payload */
	if (getenv("SET")) {
		char *s = strdup(getenv("SET")), *tok, *save;
		for (tok = strtok_r(s, ",", &save); tok; tok = strtok_r(NULL, ",", &save)) {
			unsigned long off = strtoul(tok, &tok, 0);
			char t = tok[1]; unsigned long v = strtoul(tok + 3, NULL, 0);
			if (off + 4 > psize) continue;
			if (t == 'b') body.data[off] = v; else { uint32_t w = v; memcpy(body.data + off, &w, 4); }
			printf("set payload[0x%lx] (%c) = 0x%lx\n", off, t, v);
		}
	}

	struct { struct tee_ioctl_invoke_arg a; struct tee_ioctl_param p[4]; } iv = {0};
	iv.a.session = os.a.session; iv.a.num_params = 4;
	iv.p[0].attr = TEE_IOCTL_PARAM_ATTR_TYPE_MEMREF_INPUT; iv.p[0].b = 64; iv.p[0].c = req.id;
	iv.p[1].attr = TEE_IOCTL_PARAM_ATTR_TYPE_MEMREF_OUTPUT; iv.p[1].b = 64; iv.p[1].c = rsp.id;
	iv.p[2].attr = TEE_IOCTL_PARAM_ATTR_TYPE_VALUE_INPUT; iv.p[2].a = 0; iv.p[2].b = width;
	iv.p[3].attr = TEE_IOCTL_PARAM_ATTR_TYPE_MEMREF_INOUT; iv.p[3].b = bsize; iv.p[3].c = body.id;
	struct tee_ioctl_buf_data bi = { (uintptr_t)&iv, sizeof iv };
	int r = ioctl(fd, TEE_IOC_INVOKE, &bi);
	printf("target %u cmd %u size %zu width %d: rc %d errno %d ret 0x%x\n", target, cmd, psize, width, r, r ? errno : 0, iv.a.ret);
	dump("rsp", rsp.data, 64);
	uint32_t st, res; memcpy(&st, rsp.data + 0x1c, 4); memcpy(&res, body.data + 0xc, 4);
	printf("rsp status@0x1c = %u, payload result@0xc = %u\n", st, res);
	dump("payload", body.data, psize < 1024 ? psize : 1024);
	if (loglevel) {
		const uint8_t *lg = body.data + psize;
		printf("---- TA log area (printable runs) ----\n");
		size_t i = 0;
		while (i < 0x8000) {
			size_t j = i;
			while (j < 0x8000 && lg[j] >= 0x20 && lg[j] < 0x7f) j++;
			if (j - i >= 4) printf("%.*s\n", (int)(j - i), lg + i);
			i = j + 1;
		}
		FILE *f = fopen("/tmp/talog.bin", "wb");
		if (f) { fwrite(lg, 1, 0x8000, f); fclose(f); }
	}
	return 0;
}
