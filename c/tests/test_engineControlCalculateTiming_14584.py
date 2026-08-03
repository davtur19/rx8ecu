#!/usr/bin/env python3
"""
test_engineControlCalculateTiming_14584.py — differential bit-exact test of
engineControlCalculateTiming @0x14584 (lift: c/engineControlCalculateTiming.c).

Method (repo Track-A wrapper-dispatch pattern, see
test_calc_lambda_feedback_pid_11A34.py): the REAL ROM bytes of the wrapper are
executed in the SH-2E emulator with the 66 unique callees STUBBED on both
sides by equivalent trace-append stubs, and the trace + r0/r1 + tail-call
invariants are compared bit-exactly against a pure-Python model of the
dispatch order (and, when a C compiler is available, against the compiled
lift with matching C stubs — this channel actually exercises the lift's call
order).

The wrapper (verified from the disasm of 0x14584, literal pool 0x14784..0x14888)
is a pure task-dispatch skeleton: 68 calls in fixed ROM order with zero
branches —

  Phase 1:   getSR(16)  incomplete_stack_save  + 8 subsystems
  Barrier:   setSR(saved_sr)  getSR(16)
  Phase 2:   55 subsystems (0x1379C .. 0x4D0E8)
  Tail:      jmp setSR(saved_sr) with delay lds.l @r15+,pr (returns to caller)

i.e. 66 unique targets; getSR (0x3920) and setSR (0x3934) are called TWICE
each -> 68 trace entries.  The lift's call order matches the ROM order
exactly (verified against the disasm).

Stub mechanics (emulator side): because getSR @0x3920 and setSR @0x3934 are
only 0x14 bytes apart, the 34-byte single-block stubs of the 0x11A34 test
OVERLAP.  Two-level stubs are used instead:

  * trampoline (10/12 bytes) at each callee's real ROM address:
        mov.l @(1,PC),r2 ; jmp @r2 ; nop ; [pad] ; .long body_addr
    (pool lands at ((a+4)&~3)+4 — differs by 2 bytes for a%4==2 targets,
    hence the pad)
  * shared body (36 bytes, one per slot, in a scratch RAM area far from the
    compared span) with the SAME trace semantics as the 0x11A34 stubs:
        idx = (int8_t)RAM8[0xFFFFD130]
        RAM8[0xFFFFD140 + idx] = k
        RAM8[0xFFFFD130] += 1
    and leaves r0 = 0xFFFFD130 / r1 = 0.

Compared bit-exactly, 0 mismatches required:
  * the whole 102-byte span 0xFFFFD12F..0xFFFFD194 (length cell + trace
    buffer + guard/padding; sign-extended wrap values 0xFE/0xFF land back
    inside the span, and a seeded len0 of 0x11 + 68 stubs still lands in-span);
  * r0 / r1 after the call;
  * tail-call invariants (emulator side only): r15 back to 0xFFFFDF00 and
    the PR word pushed at 0xFFFFDEFC restored to the caller's SENT
    (0xEEEE0000).

NOTE: no full-chain phase here (unlike 0x11A34): 55 real subsystems under
the tiny emulator would hit unimplemented opcodes; the stub channel fully
pins the wrapper's own behavior.

Usage:  python3 c/tests/test_engineControlCalculateTiming_14584.py [N]
        (N = random inputs per seed; default 3000 -> 15000 across 5 seeds)
"""
import os, random, re, struct, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2  # noqa: E402

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
LIFT = os.path.join(ROOT, 'c', 'engineControlCalculateTiming.c')
ADDR = 0x14584

# 68 dispatch targets in the ROM's exact call order (from the disasm of
# 0x14584; the two mov.l's back to 0x14784 and 0x147AC make getSR/setSR
# appear twice).
DISPATCH = (
    0x3920, 0x14B04, 0x121F0, 0x1237C, 0x13A0E, 0x13A5E, 0x13A86,
    0x13B90, 0x13C2C, 0x17DCC, 0x3934, 0x3920,
    0x1379C, 0x138CC, 0x13F68, 0x1408C, 0x141B8, 0x1412A, 0x12BC8,
    0x13070, 0x19220, 0x44B1C, 0x44B9A, 0x43C4A, 0x43E90, 0x43E60,
    0x43E00, 0x44AB2, 0x43EE8, 0x43F56, 0x44076, 0x4409E, 0x440DE,
    0x44206, 0x4416C, 0x442E8, 0x44370, 0x443A2, 0x44506, 0x44530,
    0x4490A, 0x445AA, 0x44694, 0x446BC, 0x44748, 0x44782, 0x447B0,
    0x44824, 0x12938, 0x128C4, 0x126EA, 0x126CA, 0x1252C, 0x12A48,
    0x128FE, 0x127DE, 0x126DA, 0x1261C, 0x135F6, 0x13652, 0x14A5C,
    0x14A92, 0x1061A, 0x1117A, 0x2CBBA, 0x2CC1C, 0x4D0E8, 0x3934,
)
assert len(DISPATCH) == 68
SLOT = {}
for a in DISPATCH:
    SLOT.setdefault(a, len(SLOT))
assert len(SLOT) == 66
DISPATCH_K = [SLOT[a] for a in DISPATCH]
# expected trace: getSR, incomplete, 8 subsys, setSR, getSR, 55 subsys, setSR
assert DISPATCH_K == ([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 0]
                      + list(range(11, 66)) + [10])

# equivalence-channel cells (test-rig scaffolding, NOT real ROM RAM)
SPAN_START = 0xFFFFD12F        # first byte of the seeded / compared span
SPAN_LEN = 102                  # 0xFFFFD12F..0xFFFFD194 (covers all 68 writes)
LEN_ADDR = 0xFFFFD130           # u8 trace length byte (span offset 1)
TRACE_ADDR = 0xFFFFD140         # u8 trace buffer base (span offset 17)
TRACE_OFF = TRACE_ADDR - SPAN_START      # 17

# scratch area for the shared stub bodies (far above the span, below the
# stack at 0xFFFFDF00)
BODY_BASE = 0xFFFFD400
BODY_STRIDE = 36                # per-slot body size (4-aligned)

# emulator-side tail-call invariants
R15_INIT = 0xFFFFDF00
PR_WORD = 0xFFFFDEFC
SENT = SH2(b'').SENT            # 0xEEEE0000 — the caller's PR under call()

BUILD_DIR = os.path.join('/tmp', 'rx8-timing-14584')


def make_body(k, addr):
    """Shared trace-append body for dispatch slot k, installed at `addr`."""
    b = bytearray(BODY_STRIDE)
    b[0] = 0xE4; b[1] = k & 0xFF            # mov #K,r4
    pool = (addr + 22 + 3) & ~3             # 4-aligned pool after the code
    b2 = (addr + 6) & ~3
    b4 = (addr + 8) & ~3
    b[2] = 0xD0; b[3] = (pool - b2) // 4    # mov.l @(disp,PC),r0 -> &LEN
    b[4] = 0xD3; b[5] = (pool + 4 - b4) // 4  # mov.l @(disp,PC),r3 -> &TRACE
    b[6] = 0x62; b[7] = 0x00                # mov.b @r0,r2   (sign-extend len)
    b[8] = 0x32; b[9] = 0x3C                # add R3,R2      (r2 = &trace[idx])
    b[10] = 0x22; b[11] = 0x40              # mov.b r4,@r2   (trace[idx] = k)
    b[12] = 0x62; b[13] = 0x00              # mov.b @r0,r2   (re-read len)
    b[14] = 0x72; b[15] = 0x01              # add #1,r2
    b[16] = 0x20; b[17] = 0x20              # mov.b R2,@R0   (len = len + 1)
    b[18] = 0x00; b[19] = 0x0B              # rts
    b[20] = 0x00; b[21] = 0x09              #   (delay slot) nop
    lo = pool - addr
    b[lo:lo + 4] = struct.pack('>I', LEN_ADDR)
    b[lo + 4:lo + 8] = struct.pack('>I', TRACE_ADDR)
    return bytes(b)


def make_tramp(a, body):
    """10/12-byte trampoline at ROM address `a` -> jmp to the body."""
    # mov.l @(1,PC),r2 ; jmp @r2 ; nop ; [pad] ; .long body
    #   mov.l base is ((pc+4)&~3); pool lands at ((a+4)&~3)+4.  For a%4==0
    #   that is a+8 (2 pad bytes); for a%4==2 it is a+6 (no pad).
    pool = ((a + 4) & ~3) + 4
    code = b'\xD2\x01\x42\x2B\x00\x09'      # mov.l @(1,PC),r2; jmp @r2; nop
    pad = bytes(pool - (a + 6))
    return code + pad + struct.pack('>I', body)


def install_stubs(ram):
    """Install one trace-append stub per unique callee.  Returns {addr: k}."""
    for i, (a, k) in enumerate(SLOT.items()):
        body_addr = BODY_BASE + BODY_STRIDE * i
        for j, byte in enumerate(make_body(k, body_addr)):
            ram[body_addr + j] = byte
        t = make_tramp(a, body_addr)
        for j, byte in enumerate(t):
            ram[a + j] = byte
    return SLOT


# ---------------- python model (the differential reference) ----------------

def model(pre):
    """Python model of the wrapper with the trace-append stubs.
    Returns (post-span tuple, r0, r1).  pre = SPAN_LEN-byte list."""
    m = list(pre)
    ln = m[1]                       # length byte (span offset 1)
    for k in DISPATCH_K:
        idx = ln - 256 if ln & 0x80 else ln   # SH-2 mov.b sign-extension
        m[TRACE_OFF + idx] = k
        ln = (ln + 1) & 0xFF
    m[1] = ln
    r0 = LEN_ADDR                   # last stub leaves LEN_ADDR in r0
    r1 = 0                          # wrapper + stubs never touch r1
    return tuple(m), r0, r1


# ---------------- emulator side ----------------

def emu_run(cpu, vec):
    ram = {}
    install_stubs(ram)
    for off, val in enumerate(vec):
        ram[SPAN_START + off] = val & 0xFF
    cpu.call(ADDR, ram=ram)
    r = cpu.ram
    got = tuple(r.get(SPAN_START + i, 0) for i in range(SPAN_LEN))
    # tail-call invariants
    assert cpu.r[15] == R15_INIT, 'r15 = 0x%08X after call' % cpu.r[15]
    pr = ((r.get(PR_WORD, 0) << 24) | (r.get(PR_WORD + 1, 0) << 16)
          | (r.get(PR_WORD + 2, 0) << 8) | r.get(PR_WORD + 3, 0))
    assert pr == SENT, 'PR word = 0x%08X, want 0x%08X' % (pr, SENT)
    return got, cpu.r[0], cpu.r[1]


# ---------------- host-C oracle ----------------

ORACLE_C = r"""
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>

#define SPAN_START 0xFFFFD12F
#define SPAN_LEN   102
#define LEN_ADDR   0xFFFFD130
#define TRACE_ADDR 0xFFFFD140
#define MAP_BASE   0xFFFFD000
#define MAP_SIZE   0x1000

static uint8_t *RAM;        /* mmap'd page holding the span at 0xFFFFD12F.. */
static uint32_t reg_r0, reg_r1;

static void t_stub(int k) {
    int ln = (int8_t)RAM[LEN_ADDR - MAP_BASE];          /* sign-extended len */
    RAM[TRACE_ADDR - MAP_BASE + ln] = (uint8_t)k;       /* trace[idx] = k    */
    RAM[LEN_ADDR - MAP_BASE] = (uint8_t)(ln + 1);       /* len += 1 (wrap)   */
    reg_r0 = LEN_ADDR;                                  /* mirror SH-2 stub  */
    reg_r1 = 0;
}

uint32_t getSR(uint32_t mask) { (void)mask; t_stub(0); return LEN_ADDR; }
void     setSR(uint32_t sr)   { (void)sr;   t_stub(10); }
void     incomplete_stack_save_r14_r13(void) { t_stub(1); }

#define DEF_STUB(name, k) \
    void name(void) { t_stub(k); }
DEF_STUB(calc_combustion_efficiency_metric, 2)
DEF_STUB(calc_combustion_load_factor, 3)
DEF_STUB(getKnockControlAllowed, 4)
DEF_STUB(getKnockSensorFaultedStatus, 5)
DEF_STUB(getKnockControlActive, 6)
DEF_STUB(updateKnockMaxRAM, 7)
DEF_STUB(calc_ignition_all_rotors_13C2C, 8)
DEF_STUB(cooling_fan_control, 9)
DEF_STUB(calc_adaptive_fuel_trim, 11)
DEF_STUB(calc_accel_fuel_enrichment, 12)
DEF_STUB(calc_barometric_pressure_trim, 13)
DEF_STUB(read_fuel_pressure_feedback_status, 14)
DEF_STUB(calc_closed_loop_fuel_status, 15)
DEF_STUB(read_o2_sensor_voltage_trim, 16)
DEF_STUB(calc_rotor_sync_idle_gate_B, 17)
DEF_STUB(read_engine_speed_status, 18)
DEF_STUB(dscRelatedTiming, 19)
DEF_STUB(sensor_range_calc, 20)
DEF_STUB(sensor_abs_deviation, 21)
DEF_STUB(calculateDriverConditions, 22)
DEF_STUB(knock_sensor_threshold, 23)
DEF_STUB(rpm_limiter_calc, 24)
DEF_STUB(air_bypass_control, 25)
DEF_STUB(fuel_enable_logic, 26)
DEF_STUB(air_bleed_control, 27)
DEF_STUB(exhaust_control, 28)
DEF_STUB(sensor_signal_calc, 29)
DEF_STUB(fuel_pressure_calc, 30)
DEF_STUB(catalyst_control, 31)
DEF_STUB(lambda_control_calc, 32)
DEF_STUB(emissions_control, 33)
DEF_STUB(fault_code_handler, 34)
DEF_STUB(fuel_correction_update, 35)
DEF_STUB(func_0443A2, 36)
DEF_STUB(fpu_clear_result, 37)
DEF_STUB(readiness_check, 38)
DEF_STUB(fuel_cut_logic, 39)
DEF_STUB(calc_decel_fuel_cut_445AA, 40)
DEF_STUB(intake_condition_check, 41)
DEF_STUB(ignition_advance_interp, 42)
DEF_STUB(sensor_select_check, 43)
DEF_STUB(rpm_neutral_calc, 44)
DEF_STUB(idle_correction_interp, 45)
DEF_STUB(knock_control_calc, 46)
DEF_STUB(calc_combustion_chamber_temp, 47)
DEF_STUB(write_knock_detected_flag, 48)
DEF_STUB(calc_rotor_A_pressure_load, 49)
DEF_STUB(add_fuel_pressure_correction, 50)
DEF_STUB(calc_intake_pressure_pid_output, 51)
DEF_STUB(calc_rotor_B_knock_flag, 52)
DEF_STUB(write_rotor_A_knock_flag, 53)
DEF_STUB(calc_rotor_B_pressure_load, 54)
DEF_STUB(add_rotor_timing_offset, 55)
DEF_STUB(calc_vis_solenoid_duty_cycle, 56)
DEF_STUB(calc_fuel_pump_duty_trim, 57)
DEF_STUB(calc_evap_purge_duty, 58)
DEF_STUB(fpu_conditional_accumulate_pair_ch0, 59)
DEF_STUB(fpu_conditional_accumulate_pair_ch1, 60)
DEF_STUB(sensor_filter_apply_all, 61)
DEF_STUB(getEngineCrankingStatus, 62)
DEF_STUB(filter_signal_adaptive, 63)
DEF_STUB(check_fuel_pump_relay_enable, 64)
DEF_STUB(health_check_system, 65)
#undef DEF_STUB

#include "LIFT_PATH"

int main(void) {
    RAM = (uint8_t *)mmap((void *)MAP_BASE, MAP_SIZE,
                          PROT_READ | PROT_WRITE,
                          MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (RAM == MAP_FAILED) { perror("mmap"); return 2; }
    char line[4096];
    while (fgets(line, sizeof line, stdin)) {
        unsigned v[SPAN_LEN];
        int n = 0;
        char *tok = strtok(line, " \t\r\n");
        while (tok && n < SPAN_LEN) {
            v[n++] = (unsigned)strtoul(tok, NULL, 16);
            tok = strtok(NULL, " \t\r\n");
        }
        if (n != SPAN_LEN) return 3;
        memset(RAM, 0, MAP_SIZE);
        for (int i = 0; i < SPAN_LEN; i++)
            RAM[SPAN_START - MAP_BASE + i] = (uint8_t)v[i];
        engineControlCalculateTiming();
        for (int i = 0; i < SPAN_LEN; i++)
            printf("%02X ", RAM[SPAN_START - MAP_BASE + i]);
        printf("%08X %08X\n", reg_r0, reg_r1);
    }
    return 0;
}
"""


def build_oracle(cc='cc'):
    os.makedirs(BUILD_DIR, exist_ok=True)
    src = os.path.join(BUILD_DIR, 'oracle_14584.c')
    with open(src, 'w') as f:
        f.write(ORACLE_C.replace('"LIFT_PATH"', '"%s"' % LIFT))
    exe = os.path.join(BUILD_DIR, 'oracle_14584')
    cmd = [cc, '-O2', '-Wall', '-Wextra', '-x', 'c', src, '-o', exe]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return exe


# ---------------- vector generation ----------------

def gen_edges():
    v = []
    lens = (0x00, 0x01, 0x07, 0x10, 0x11, 0xFE, 0xFF)
    pats = (0x00, 0xFF, 0xAA)
    for ln in lens:
        for pat in pats:
            s = [pat & 0xFF] * SPAN_LEN
            s[1] = ln & 0xFF
            s[0] = 0x5A
            s[2] = 0xA5
            v.append(s)
    for ln in lens:
        s = [i & 0xFF for i in range(SPAN_LEN)]
        s[1] = ln & 0xFF
        s[0] = 0x5A
        s[2] = 0xA5
        v.append(s)
    return v


def gen_random(rng, k):
    v = []
    for _ in range(k):
        if rng.random() < 0.15:
            ln = rng.choice((0xFE, 0xFF))
        else:
            ln = rng.choice((0, 0, 0, 1, 2, 3, 5, 7, 8, 15, 16, 17))
        s = [rng.getrandbits(8) for _ in range(SPAN_LEN)]
        s[0] = 0x5A
        s[1] = ln & 0xFF
        s[2] = 0xA5
        v.append(s)
    return v


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x14584, 0x14784, 0x3920, 0x1234, 0x5EED)

    # ---- host-C oracle (best effort; skipped cleanly if no C compiler) ----
    oracle = None
    cc = os.environ.get('CC', 'cc')
    try:
        oracle = build_oracle(cc)
    except Exception as e:
        print('note: host-C oracle not built (%s); Python-model channel only' % e)

    total_fails = 0
    total_vecs = 0
    for seed in seeds:
        random.seed(seed)
        rng = random.Random(seed)
        vectors = gen_edges() + gen_random(rng, N)
        n = len(vectors)

        # (a) emulator (real ROM wrapper bytes; stubbed callees)
        emu = [emu_run(cpu, v) for v in vectors]

        # (b) python model
        py = [model(v) for v in vectors]

        # (c) host C (if available)
        if oracle:
            inp = '\n'.join(' '.join('%02X' % b for b in v) for v in vectors) + '\n'
            out = subprocess.run([oracle], input=inp, capture_output=True,
                                 text=True, check=True).stdout.splitlines()
            assert len(out) == n, 'oracle returned %d lines, want %d' % (len(out), n)
            c_model = []
            for line in out:
                toks = line.split()
                c_model.append((tuple(int(t, 16) for t in toks[:SPAN_LEN]),
                                int(toks[SPAN_LEN], 16), int(toks[SPAN_LEN + 1], 16)))

        mism = 0
        for i, v in enumerate(vectors):
            e_span, e_r0, e_r1 = emu[i]
            p_span, p_r0, p_r1 = py[i]
            if e_span != p_span or e_r0 != p_r0 or e_r1 != p_r1:
                print('MISMATCH vs PY seed=0x%X vec#%d len0=%02X'
                      % (seed, i, v[1]))
                print('  emu span: %s' % ' '.join('%02X' % x for x in e_span[:40]))
                print('  py  span: %s' % ' '.join('%02X' % x for x in p_span[:40]))
                print('  r0 emu=%08X py=%08X  r1 emu=%08X py=%08X'
                      % (e_r0, p_r0, e_r1, p_r1))
                mism += 1
                if mism >= 3:
                    break
            if oracle is not None and mism == 0:
                c_span, c_r0, c_r1 = c_model[i]
                if e_span != c_span or e_r0 != c_r0 or e_r1 != c_r1:
                    print('MISMATCH vs C  seed=0x%X vec#%d len0=%02X'
                          % (seed, i, v[1]))
                    print('  emu span: %s' % ' '.join('%02X' % x for x in e_span[:40]))
                    print('  c   span: %s' % ' '.join('%02X' % x for x in c_span[:40]))
                    print('  r0 emu=%08X c=%08X  r1 emu=%08X c=%08X'
                          % (e_r0, c_r0, e_r1, c_r1))
                    mism += 1
                    if mism >= 3:
                        break
        print('  seed 0x%X: %d inputs, fails=%d' % (seed, n, mism))
        total_fails += mism
        total_vecs += n
        if total_fails:
            break

    if total_fails:
        print('\n%d FAILURE(S) over %d inputs' % (total_fails, total_vecs))
        sys.exit(1)
    chan = 'Python model'
    if oracle is not None:
        chan += ' + host-C oracle'
    print('OK  engineControlCalculateTiming_14584 (%d inputs across %d seeds, '
          '0 mismatches; channel: %s)' % (total_vecs, len(seeds), chan))
    print('    dispatch pinned: 68 calls / 66 unique targets in ROM order '
          '(getSR+setSR x2, tail jmp setSR)')
    sys.exit(0)


if __name__ == '__main__':
    main()
