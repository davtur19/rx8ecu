/* Predicted sh-elf-gcc -m2e -O2 output for c_src/addSaturate8Bit.c.
 * Target: byte-identical to ROM 0x2478 (rom_hex/addSaturate8Bit_2478.txt).
 * Body = 22 bytes (incl. rts delay-slot `mov r4,r0`), literal @+0x16.
 */
	.text
	.align	4
	.global	addSaturate8Bit
	.type	addSaturate8Bit,@function
addSaturate8Bit:
	extu.b	r4,r4
	extu.b	r5,r5
	add	r5,r4
	extu.w	r4,r3
	mov.w	@(lit,pc),r5
	cmp/ge	r5,r3
	bf/s	1f
	nop
	mov	r5,r4
1:	rts
	mov	r4,r0
lit:
	.short	0x00FF
	.size	addSaturate8Bit, .-addSaturate8Bit
