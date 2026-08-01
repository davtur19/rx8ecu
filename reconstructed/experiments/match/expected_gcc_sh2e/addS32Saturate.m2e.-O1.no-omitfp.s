	.file	"addS32Saturate.c"
	.text
	.text
	.align 1
	.global	_addS32Saturate
	.type	_addS32Saturate, @function
_addS32Saturate:
	mov.l	r14,@-r15
	mov	r4,r0
	mov	#0,r7
	cmp/gt	r4,r7
	subc	r1,r1
	cmp/gt	r5,r7
	subc	r2,r2
	clrt
	addc	r5,r0
	addc	r2,r1
	cmp/pl	r1
	bt.s	.L5
	mov	r15,r14
	cmp/pz	r1
	bt.s	.L9
	mov	#-1,r2
.L16:
	cmp/ge	r2,r1
	bf.s	.L6
	cmp/pz	r1
	bf	.L10
.L1:
	mov	r14,r15
	rts	
	mov.l	@r15+,r14
	.align 1
.L9:
	mov.l	.L12,r2
	cmp/hi	r2,r0
	bf.s	.L16
	mov	#-1,r2
.L5:
	mov.l	.L12,r0
	bra	.L1
	nop
	.align 1
.L10:
	mov.l	.L14,r1
	cmp/hs	r1,r0
	bt	.L1
.L6:
	mov.l	.L14,r0
	bra	.L1
	nop
.L15:
	.align 2
.L12:
	.long	2147483647
.L14:
	.long	-2147483648
	.size	_addS32Saturate, .-_addS32Saturate
	.ident	"GCC: (GNU) 14.2.0"
