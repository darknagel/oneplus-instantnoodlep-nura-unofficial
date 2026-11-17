import sys
src, dst = sys.argv[1], sys.argv[2]
s = open(src).read()
NL = '\\' + 'n'
old = '\tcommand = path_request->command;\n'
assert old in s
s = s.replace(old, old + '\tfprintf(stderr, "GPDBG cmd=%u path=%.200s' + NL + '", command, command == 12 ? "-" : path_request->pathname);\n', 1)
old2 = '\tgp_reply(buffer, command, saved, saved ? 0 : length);\n\treturn 0;\n}'
assert old2 in s
s = s.replace(old2, '\tfprintf(stderr, "GPDBG  -> off=%d len=%u err=%d' + NL + '", offset, length, saved);\n' + old2, 1)
open(dst, 'w').write(s)
