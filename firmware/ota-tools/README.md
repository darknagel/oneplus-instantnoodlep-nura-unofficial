# Generating oneplus-ota-fetch.json

oneplus-ota-fetch downloads only the OTA operations that hold the files it needs.
The list is computed once, offline, for the pinned OTA:

1. `ota_probe.py URL`: checks range support and saves the payload manifest.
2. `ota_extract.py URL odm|vendor IMG`: downloads a whole partition (for analysis).
3. `trace_blocks.py IMG OUT SPEC...` (Alpine with erofs-utils 1.9 and strace):
   records the bytes `dump.erofs` reads for the wanted files and directories.
4. `needed_ops.py PART TRACE FULL SPARSE`: maps them to OTA operations and builds
   a sparse test image. Check that every file reads back identical from it.
5. `gen_data.py`: writes `oneplus-ota-fetch.json` (offsets, op lists, hashes).

The JSON holds no proprietary content, only offsets, lengths and SHA-256 sums.
