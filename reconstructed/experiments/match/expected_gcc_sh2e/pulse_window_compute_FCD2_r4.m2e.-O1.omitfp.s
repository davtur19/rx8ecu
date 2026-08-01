	.file	"pulse_window_compute_FCD2_r4.c"
	.text
	.text
	.align 1
	.global	_pulse_window_compute
	.type	_pulse_window_compute, @function
_pulse_window_compute:
	mov	r5,r3
	sub	r4,r3
	mov	r3,r4
	cmp/pl	r4
	bt.s	.L2
	nop
	mov.w	.L3,r3
	add	r3,r4
.L2:
	rts	
	mov	r4,r0
	.align 1
.L3:
	.short	360
	.size	_pulse_window_compute, .-_pulse_window_compute
	.ident	"GCC: (GNU) 3.4.6"
