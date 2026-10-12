# Find the function containing each hot block: scan back to the prologue (stwu r1,-X(r1)),
# forward to the epilogue's blr.
import struct, sys
mem = open(sys.argv[1], "rb").read()
def word(a): o = a & 0x01ffffff; return struct.unpack(">I", mem[o:o+4])[0]
for pc in [int(x, 16) for x in sys.argv[2:]]:
    a = pc
    start = None
    for k in range(4000):
        w = word(a)
        if (w & 0xffff0000) == 0x94210000:  # stwu r1, d(r1)
            start = a; break
        a -= 4
    # end: first blr after start (0x4e800020)
    e = start or pc
    end = None
    for k in range(8000):
        if word(e) == 0x4e800020:
            end = e; break
        e += 4
    print("%08x: function %s .. %s (%d instructions)" % (pc, hex(start or 0), hex(end or 0), ((end or 0) - (start or 0)) // 4 + 1))
