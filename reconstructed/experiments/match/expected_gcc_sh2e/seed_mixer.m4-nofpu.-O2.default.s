	.file	"seed_mixer.c"
	.text
	.text
	.align 1
	.align 2
	.global	_seed_mixer
	.type	_seed_mixer, @function
_seed_mixer:
	extu.b	r5,r5
	mov	r4,r1
	shlr8	r1
	mov.l	.L3,r3
	extu.b	r4,r2
	extu.b	r1,r1
	swap.b	r5,r4
	or	r2,r4
	mov.l	.L4,r2
	shll16	r1
	or	r1,r4
	mov	r4,r1
	shll8	r1
	add	r1,r1
	and	r4,r3
	and	r2,r1
	mov.w	.L5,r2
	shlr8	r4
	shlr	r4
	and	r2,r4
	or	r4,r1
	or	r1,r3
	mov	r3,r7
	mov	r3,r1
	shlr16	r7
	shlr8	r1
	neg	r7,r7
	neg	r1,r1
	extu.b	r1,r1
	extu.b	r7,r7
	shll16	r7
	swap.b	r1,r2
	neg	r3,r3
	or	r7,r2
	extu.b	r3,r3
	or	r3,r2
	mov	r2,r1
	mov	#21,r3
	shlr2	r2
	shlr	r2
	shld	r3,r1
	or	r2,r1
	mov.w	.L6,r2
	swap.b	r1,r1
	swap.w	r1,r1
	swap.b	r1,r1
	and	r2,r1
	swap.w	r1,r0
	shll8	r0
	shlr8	r1
	rts	
	or	r1,r0
	.align 1
.L5:
	.short	4064
.L6:
	.short	-256
.L7:
	.align 2
.L3:
	.long	-2084833
.L4:
	.long	2080768
	.size	_seed_mixer, .-_seed_mixer
	.ident	"GCC: (GNU) 14.2.0"
