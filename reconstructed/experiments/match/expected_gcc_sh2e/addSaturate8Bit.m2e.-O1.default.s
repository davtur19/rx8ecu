	.file	"addSaturate8Bit.c"
	.text
	.text
	.align 1
	.global	_addSaturate8Bit
	.type	_addSaturate8Bit, @function
_addSaturate8Bit:
	extu.b	r4,r4
	extu.b	r5,r5
	mov	r4,r2
	add	r5,r2
	mov.w	.L4,r1
	cmp/hi	r1,r2
	bt	.L3
	rts	
	extu.b	r2,r0
	.align 1
.L3:
	mov.w	.L5,r0
	rts	
	nop
	.align 1
.L4:
	.short	254
.L5:
	.short	255
	.size	_addSaturate8Bit, .-_addSaturate8Bit
	.ident	"GCC: (GNU) 14.2.0"
