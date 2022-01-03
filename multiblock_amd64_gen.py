import sys
import random

# The file is based on https://github.com/mmcloughlin/aesnix/blob/master/gen.py

FILE_HEADER = (
u'''
// Code generated by multiblock_amd64_gen.py. DO NOT EDIT.

#include "textflag.h"

// See https://golang.org/src/crypto/aes/gcm_amd64.s
#define NR CX
#define XK AX
#define DST DX
#define SRC R10
#define IV_PTR BX
#define BLOCK_INDEX R11
#define IV_LOW R12
#define IV_HIGH R13
#define BSWAP X15

DATA bswapMask<>+0x00(SB)/8, $0x08090a0b0c0d0e0f
DATA bswapMask<>+0x08(SB)/8, $0x0001020304050607

GLOBL bswapMask<>(SB), (NOPTR+RODATA), $16
''')

TEXT = u'TEXT \u00b7{name}(SB),NOSPLIT,$0'

CTR_DECL = '// func {name}(nr int, xk *uint32, dst, src, ivRev *byte, blockIndex uint64)'
CTR_HEADER = (
u'''
	MOVQ nr+0(FP), NR
	MOVQ xk+8(FP), XK
	MOVUPS 0(XK), {reg_key}
	MOVQ dst+16(FP), DST
	MOVQ src+24(FP), SRC
	MOVQ ivRev+32(FP), IV_PTR
	MOVQ 0(IV_PTR), IV_LOW
	MOVQ 8(IV_PTR), IV_HIGH
	MOVQ blockIndex+40(FP), BLOCK_INDEX

	MOVOU bswapMask<>(SB), BSWAP
''')


REV16_DECL = '// func {name}(iv *byte)'
REV16_HEADER = (
u'''
	MOVQ iv+0(FP), IV_PTR
	MOVUPS 0(IV_PTR), X0
	MOVOU bswapMask<>(SB), BSWAP
	PSHUFB BSWAP, X0
	MOVUPS X0, 0(IV_PTR)
''')


def ctr(n):
    """
    Generate Go assembly for XORing CTR output to n blocks at once with one key.
    """

    assert n <= 8

    params = {
        'name': 'ctrBlocks{}Asm'.format(n),
        'reg_key': 'X{}'.format(n),
    }

    # Header.
    for tmpl in [CTR_DECL, TEXT, CTR_HEADER]:
        print tmpl.format(**params)

    # Prepare plain from IV and blockIndex.

    # Add blockIndex.
    print '\tADDQ BLOCK_INDEX, IV_LOW'
    print '\tADCQ $0, IV_HIGH'

    # Copy to plaintext registers.
    for i in xrange(n):
        # https://stackoverflow.com/a/2231893
        print '\tMOVQ IV_LOW, X{i}'.format(i=i)
        print '\tPINSRQ $1, IV_HIGH, X{i}'.format(i=i)
        print '\tPSHUFB BSWAP, X{i}'.format(i=i)
        if i != n-1:
            print '\tADDQ $1, IV_LOW'
            print '\tADCQ $0, IV_HIGH'

    # Initial key add.
    print '\tADDQ $16, AX'
    for i in xrange(n):
        print '\tPXOR {reg_key}, X{i}'.format(i=i, **params)

    # Num rounds branching.
    print '\tSUBQ $12, NR'
    print '\tJE Lenc192'
    print '\tJB Lenc128'

    def enc(ax, inst='AESENC'):
        print '\tMOVUPS {offset}(AX), {reg_key}'.format(offset=16*ax, **params)
        for i in xrange(n):
            print '\t{inst} {reg_key}, X{i}'.format(inst=inst, i=i, **params)

    # 2 extra rounds for 256-bit keys.
    print 'Lenc256:'
    enc(0)
    enc(1)
    print '\tADDQ $32, AX'

    # 2 extra rounds for 192-bit keys.
    print 'Lenc192:'
    enc(0)
    enc(1)
    print '\tADDQ $32, AX'

    # 10 rounds for 128-bit (with special handling for final).
    print 'Lenc128:'
    for r in xrange(9):
        enc(r)
    enc(9, inst='AESENCLAST')

    # XOR results to destination. Use X8-X15 for that.
    # It overwrites BSWAP in the end, but it is not needed.
    for i in xrange(n):
        print '\tMOVUPS {offset}(SRC), X{r}'.format(offset=16*i, r=i+8)
        print '\tPXOR X{i}, X{r}'.format(i=i, r=i+8)
        print '\tMOVUPS X{r}, {offset}(DST)'.format(offset=16*i, r=i+8)

    print '\tRET'
    print


def rev16():
    """
    Generate Go assembly for BSWAP.
    """

    params = {
        'name': 'rev16Asm',
    }

    # Header.
    for tmpl in [REV16_DECL, TEXT, REV16_HEADER]:
        print tmpl.format(**params)

    print '\tRET'
    print


def generate_file(sizes):
    print FILE_HEADER
    for size in sizes:
        ctr(size)
    rev16()


def main(args):
    sizes = map(int, args[1].split(','))
    generate_file(sizes)


if __name__ == '__main__':
    main(sys.argv)
