/* Predicted sh-elf-gcc -m2e -O2 output for c_src/addS32Saturate.c,
 * assuming the compiler emits the SH-2 `addv` (signed-overflow) path that
 * the ROM uses at 0x2304 (rom_hex/addS32Saturate_2304.txt).
 *
 * Plain 2002-era GCC would NOT emit addv for this C (no __builtin_add_overflow
 * then); this file encodes the "vendor compiler / hand-asm" variant that IS
 * byte-identical, to demonstrate what the codegen must look like.
 * Body = 18 bytes (incl. rts delay-slot nop) + 1 padding nop + 4B literal.
 */
	.text
	.align	4
	.global	addS32Saturate
	.type	addS32Saturate,@function
addS32Saturate:
	addv	r4,r5
	bf/s	1f
	mov	r5,r0
	mov.l	@(lit,pc),r0
	cmp/pz	r5
	mov	#0,r5
	addc	r5,r0
1:	rts
	nop
	nop
lit:
	.long	0x7FFFFFFF
	.size	addS32Saturate, .-addS32Saturate
