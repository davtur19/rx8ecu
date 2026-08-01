	.file	"shift_right_8_r0_467A_loop.c"
	.text
	.text
	.align 1
	.align 4
	.global	_shift_right_8_r0
	.type	_shift_right_8_r0, @function
_shift_right_8_r0:
	mov	r4,r0
	shar	r0
	shar	r0
	shar	r0
	shar	r0
	shar	r0
	shar	r0
	shar	r0
	rts	
	shar	r0
	.size	_shift_right_8_r0, .-_shift_right_8_r0
	.ident	"GCC: (GNU) 3.4.6"
