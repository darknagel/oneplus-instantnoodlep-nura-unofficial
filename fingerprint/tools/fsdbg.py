import sys, re
src, dst = sys.argv[1], sys.argv[2]
s = open(src).read()
NL = '\\' + 'n'  # literal backslash-n inside the C string
if '#include <stdio.h>' not in s:
    s = s.replace('#include', '#include <stdio.h>\n#include', 1)
m = re.search(r'static int fail\(void \*buffer, uint32_t command\)\n\{\n', s)
s = s[:m.end()] + '\tfprintf(stderr, "FSDBG fail cmd=0x%x errno=%d' + NL + '", command, errno);\n' + s[m.end():]
old = '\tcommand = path_request->command;\n'
new = old + (
    '\tif (command == QS_FS_OPEN)\n'
    '\t\tfprintf(stderr, "FSDBG open %.200s flags=0x%x' + NL + '", open_request->pathname, (unsigned)open_request->flags);\n'
    '\telse if (command == QS_FS_CREAT || command == QS_FS_UNLINK || command == QS_FS_REMOVE || command == QS_FS_MKDIR || command == QS_FS_RMDIR || command == QS_FS_RENAME)\n'
    '\t\tfprintf(stderr, "FSDBG cmd=0x%x %.200s' + NL + '", command, path_request->pathname);\n'
    '\telse\n'
    '\t\tfprintf(stderr, "FSDBG cmd=0x%x' + NL + '", command);\n')
assert old in s
s = s.replace(old, new, 1)
open(dst, 'w').write(s)
