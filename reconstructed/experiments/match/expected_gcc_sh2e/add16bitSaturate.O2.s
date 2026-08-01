/* Predicted sh-elf-gcc -m2e -O2 output for c_src/add16bitSaturate.c.
 * Target: byte-identical to ROM 0x2460 (rom_hex/add16bitSaturate_2460.txt).
 * Hand-written prediction of GCC SH-2 codegen (assembled + compared by
 * scripts/compare.py).  Label names/alignment chosen to reproduce the ROM
 * layout exactly.
 */
	.text
	.align	4
	.global	add16bitSaturate
	.type	add16bitSaturate,@function
add16bitSaturate:
	extu.w	r4,r4
	extu.w	r5,r5
	add	r5,r4
	mov.l	@(lit,pc),r5
	cmp/hs	r5,r4
	bf/s	1f
	nop
	mov	r5,r4
1:	rts
	mov	r4,r0
lit:
	.long	0x0000FFFF
	.size	add16bitSaturate, .-add16bitSaturate
