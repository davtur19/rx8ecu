# putTaskInSchedule_FuelArrayStuff @ 0xA10E
**Purpose:** Schedules a fuel-related task into the ECU's task scheduler with priority 4 and initial value 1.
**Inputs:** r4: task_id or task_descriptor (parameter to osTaskScheduler)
**Out:** Task queued into scheduler at 0x9630 (osTaskScheduler) ; Task runs with priority=4, initial_value=1
**Calls:** 0x00009630 (osTaskScheduler): RTOS scheduler entry point
Load priority value 4 into r5 ; Load scheduler address 0x9630 into r2 ; Save return address to stack (sts.l pr, @-r15) ; Allocate 4 bytes on stack (add #-4, r15) ; Move stack pointer to r6 (used as
frame for scheduler) ; Store task_id parameter (r4) to stack ; Call osTaskScheduler(r2=0x9630, r4=task_id, r5=priority(4), r6=stack_frame) ; Load initial value 1 into r4 (delay slot) ; Deallocate
stack (add #4, r15) ; Restore return address ; Return
**Draft C:**
```c
void putTaskInSchedule_FuelArrayStuff(int task_id) {
    int priority = 4;
    int initial_value = 1;
    int stack_frame[1];
    stack_frame[0] = task_id;
    osTaskScheduler(task_id, priority, (void *)stack_frame);
    // or possibly: osTaskScheduler(stack_frame, priority, initial_value, stack_frame);
}
```
**Status:** med — function structure is clear, but exact osTaskScheduler calling convention is unclear. SH-2 ABI uses r4-r7 for int args and r2 for jsr target. The name strongly suggests fuel calculation scheduling.
**Uncertainties:** What is exact osTaskScheduler signature? (parameter order/meaning) ; What task_id is being passed? (should come from r4) ; Why priority 4? (is there a priority scale 0-7 or similar?) ; What does initial_value=1 mean? (first iteration flag? counter seed?) ; Is this a periodic task or one-shot?
