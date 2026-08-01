/* seed_mixer 0x366B8 — HAND RECONSTRUCTION of the ROM codegen (low-opt,
 * byte-array style), NOT a GCC prediction.  Proves the sh-elf binutils can
 * round-trip the 164-byte body byte-exactly (see rom_hex/seed_mixer_366B8.txt).
 *
 * Layout note: the ROM places seed_mixer's three literals (0x0FE0,
 * 0x001FC000, 0xFFE0301F) at +0x166/+0x168/+0x16C relative to the body
 * start (physically inside the adjacent calculateImmoSeed region); the
 * PC-relative disp fields in the body (91B1 / D34F / D259) are therefore
 * only reproducible if the literals sit at the same relative offsets.
 * Bytes between the body end (+0xA4) and the pool are arbitrary filler here
 * (in the ROM they are calculateImmoSeed code) and are excluded from the
 * comparison.  compare.py compares the first 164 bytes (the body) only.
 */
	.text
	.align	4
	.global	seed_mixer
	.type	seed_mixer,@function
seed_mixer:
	mov.w	@(lit0,pc),r1
	add	#0xF4,r15
	mov.l	@(lit2,pc),r2
	mov	r5,r0
	mov.b	r0,@(0x08,r15)
	extu.w	r4,r0
	shlr8	r0
	mov.b	r0,@(0x04,r15)
	mov.b	r4,@r15
	mov.b	@(0x04,r15),r0
	mov.b	@r15,r3
	extu.b	r0,r0
	shll16	r0
	mov	r0,r4
	mov.b	@(0x08,r15),r0
	extu.b	r3,r3
	extu.b	r0,r0
	shll8	r0
	or	r0,r4
	or	r3,r4
	mov.l	@(lit1,pc),r3
	and	r4,r1
	and	r4,r3
	shlr8	r3
	shlr	r3
	shll8	r1
	shll	r1
	or	r1,r3
	and	r4,r2
	mov	r3,r4
	or	r2,r4
	mov	r4,r7
	shlr16	r7
	mov	r4,r5
	shlr8	r5
	mov	r4,r6
	not	r7,r4
	add	#0x01,r4
	not	r5,r5
	add	#0x01,r5
	not	r6,r6
	add	#0x01,r6
	extu.b	r4,r4
	shll16	r4
	extu.b	r5,r5
	shll8	r5
	or	r5,r4
	extu.b	r6,r6
	or	r6,r4
	mov	r4,r3
	shll16	r3
	shll2	r3
	shll2	r3
	shll	r3
	mov	r4,r2
	shlr2	r2
	shlr	r2
	mov	r3,r4
	or	r2,r4
	mov	r4,r3
	shlr16	r3
	mov	r4,r0
	mov.b	r3,@r15
	shlr8	r0
	mov.b	r0,@(0x04,r15)
	mov	r4,r0
	mov.b	r0,@(0x08,r15)
	mov.b	r3,@r15
	mov.b	@(0x08,r15),r0
	extu.b	r0,r0
	mov.b	@r15,r3
	shll16	r0
	mov	r0,r4
	extu.b	r3,r3
	mov.b	@(0x04,r15),r0
	extu.b	r0,r0
	shll8	r0
	or	r0,r4
	or	r3,r4
	mov	r4,r0
	rts
	add	#0x0C,r15
	/* body ends at +0xA4 (164B). Pool must sit at +0x166/+0x168/+0x16C
	   (as in the ROM: 0x3681E/0x36820/0x36824) so the PC-relative disp
	   fields inside the body come out byte-exact. */
	.space	(0x166 - 0xA4), 0
lit0:
	.short	0x0FE0
lit1:
	.long	0x001FC000
lit2:
	.long	0xFFE0301F
	.size	seed_mixer, .-seed_mixer
