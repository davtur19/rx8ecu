#!/usr/bin/env python3
"""test_omp_task_0x1825E.py

Differential test for the OMP (oil-metering-pump) RTOS task at ROM 0x1825E
(lift: c/omp_task_0x1825E.c).  Runs the ROM task in the SH-2 emulator and
compares the full relevant RAM against a Python model.

The task is the top of the stepper-motor control chain.  Flow (see the lift
header for the full annotated layout):
  snapshot dispatch flags -> hardware fault gate on RAM9ECD bit1 ->
  engine-on accumulation -> idle reset -> countdown (A97B) -> purge block ->
  partial/full epilogue -> mode dispatch (A998/0x18C6C, A968/0x18860,
  A96A/0x18C08, A96B/0x18C5C, A969/0x189EE) -> common tail (P807A write/read
  + A975 ramp + P8078 write) -> epilogue.

Reused verified leaves (called through their existing test models):
  0x18552  test_omp_stepper_waveform_driver.model
  0x18860  test_omp_waveform_state_machine_18860.model
  0x189EE  test_rotor_sync_position_detector.model
Port accessors 0x3ED3C/0x3EE58 and fault-flag leaf 0x3F050 are modelled
inline (complementary byte encoding, C6AC fault flag), matching
test_omp_accessors.py.

Run: python3 c/tests/test_omp_task_0x1825E.py [N]
     (N = random inputs per seed; default 30000 -> 150000 across 5 seeds)
"""
import os, sys, random, struct

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, s8
from test_omp_stepper_waveform_driver import model as wave_model
from test_omp_waveform_state_machine_18860 import model as inj_model
from test_rotor_sync_position_detector import model as rotor_model

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')

# ---- RAM map (see c/omp_task_0x1825E.c header) ----
A968 = 0xFFFFA968   # idle-state flag / dispatch gate (snapshotted at entry)
A969 = 0xFFFFA969   # rotor-sync dispatch flag
A96A = 0xFFFFA96A   # diag/rotor dispatch flag
A96B = 0xFFFFA96B   # purge-wave dispatch flag
A96C = 0xFFFFA96C   # engine-running flag (r10 snapshot)
A974 = 0xFFFFA974   # position target / ramp condition
A975 = 0xFFFFA975   # ramp value (0 / 4 / up-down)
A976 = 0xFFFFA976   # fault-inoperative flag
A977 = 0xFFFFA977   # warm-cal latch
A978 = 0xFFFFA978   # cold-cal latch
A979 = 0xFFFFA979
A97B = 0xFFFFA97B   # task countdown
A97C = 0xFFFFA97C   # wave step
A97D = 0xFFFFA97D
A97E = 0xFFFFA97E
A97F = 0xFFFFA97F   # wave position output
A980 = 0xFFFFA980   # 0x18C08 diag state
A981 = 0xFFFFA981   # 0x18860 state machine
A982 = 0xFFFFA982   # purge-enable latch
A983 = 0xFFFFA983
A984 = 0xFFFFA984   # rotor mode
A985 = 0xFFFFA985   # injection mode
A986 = 0xFFFFA986
A987 = 0xFFFFA987   # fault-latched flag
A988 = 0xFFFFA988
A989 = 0xFFFFA989   # ramp-enable flag
A98A = 0xFFFFA98A   # wave discriminator
A98D = 0xFFFFA98D
A998 = 0xFFFFA998   # wave-reload dispatch flag
A8F1 = 0xFFFFA8F1   # rotor sync compare target
ECD  = 0xFFFF9ECD   # hardware fault register, bit1 = OMP fault
CD06 = 0xFFFFCD06   # 0x18C08 gate
C6AC = 0xFFFFC6AC   # ADDRESS_VAL fault flag (leaf 0x3F050)
B5F3 = 0xFFFFB5F3   # diag-table writer 0x9668 footprint
AA10 = 0xFFFFAA10   # coolant temp (f32)
P78  = 0xFFFF8078   # ramp output port (complementary u16)
P7A  = 0xFFFF807A   # idle/off port (complementary u16)
P7C  = 0xFFFF807C   # purge port (complementary u16)
F746 = 0xFFFFF746   # stepper phase drive port

CAL35 = 0x02   # ROM 0x78E35: P8078 write value
CAL36 = 0x34   # ROM 0x78E36: ramp r7 threshold
CAL37 = 0x3C   # ROM 0x78E37: ramp A974 threshold


def model(ram, temp):
    """Python model of the whole task at 0x1825E.  Returns the full effect
    dict (0xFFFF-prefixed int keys; the inj leaf may leave a 'temp' key)."""
    m = dict(ram)

    def B(a): return m.get(a, 0) & 0xFF
    def W(a, v): m[a & 0xFFFFFFFF] = v & 0xFF
    def W16(a, v): W(a, (v >> 8) & 0xFF); W(a + 1, v & 0xFF)

    def read8_av(a, default):
        """0x3ED3C: complementary pair -> s8; else fault flag 0x3F050 + default."""
        b0 = B(a); b1 = B(a + 1)
        if b0 == ((~b1) & 0xFF):
            return s8(b0)
        W(C6AC, 1)
        return s8(default & 0xFF)

    def write8_av(a, val):
        """0x3EE58: complementary-encoded byte store."""
        v = ((val & 0xFF) << 8) | ((~val) & 0xFF)
        W16(a, v)

    def do_wave(wmode):
        step, a97d = B(A97C), B(A97D)
        a974 = B(A974); a98a = B(A98A); a969 = B(A969); a96a = B(A96A)
        port = (B(F746) << 8) | B(F746 + 1)
        nstep, na97d, wf_ok, wf, na98a, nport = wave_model(
            wmode, step, a97d, a974, a98a, a969, a96a, port)
        W(A97C, nstep); W(A97D, na97d); W(A98A, na98a); W(A98D, wmode)
        W16(F746, nport)
        if wf_ok:
            W(A97F, wf)

    def leaf_18C6C():
        """wave-reload leaf (inlined)."""
        a974 = B(A974)
        if a974 > 7:
            do_wave(3); W(A97B, 0x10)
        elif a974 == 7:
            do_wave(4); W(A97B, 4)
        else:
            do_wave(2); W(A97B, 0x10)

    def leaf_18C5C():
        """purge-wave leaf (inlined)."""
        do_wave(6)
        W(A97B, 8)

    def leaf_18C08():
        """diag+rotor leaf (inlined): 0x9668 diag store sets B5F3."""
        if B(A980) == 1:
            write8_av(P7C, 1)
            W(B5F3, 1)
            W(A980, 2)
        if B(A974) == B(A8F1):
            W(A97B, 0x30)
            W(A980, 1)
        else:
            eff = rotor_model(B(A984), dict(m))
            m.clear(); m.update(eff)

    # step 1: hardware fault gate (RAM9ECD bit1)
    if (B(ECD) & 2) == 0:
        W(A976, 0)
    else:
        old = B(A976)
        W(A976, 1)
        if old == 0:
            W(A987, 1)

    # step 2: engine-on accumulation
    if B(A988) == 1 and B(A96C) == 0:
        W(A989, 1)

    # step 3: idle-state reset
    if B(A968) == 0:
        W(A977, 0)
        W(A978, 0)

    # step 4: countdown decrement
    if B(A97B) != 0:
        W(A97B, (B(A97B) - 1) & 0xFF)

    # step 5: purge block
    if B(A97B) == 1 and B(A968) == 1 and B(A982) == 1:
        W(A974, 0)
        W(A97F, 0)
        write8_av(P7C, 0)
        W(A979, 1)
        if B(A977) == 1:
            W(A977, 0)
            W(A983, 1)
            v = read8_av(P78, 0)
            if v != 0:
                write8_av(P78, (v - 1) & 0xFF)
        if B(A978) == 1:
            W(A978, 0)

    # step 6: countdown still active -> partial epilogue
    if B(A97B) != 0:
        W(A988, B(A96C))
        return m

    # step 7: mode dispatch
    W(A974, B(A97F))
    a998 = B(A998)
    if a998 == 1:
        leaf_18C6C()
    elif B(A968) == 1:
        # 0x18860 gates on ADDRESS_VAL port reads (0x3ED3C): an invalid
        # complementary pair raises the C6AC fault flag (leaf 0x3F050).
        # Reads happen only when A985 != 0 (mode 0 clears A981 first) and
        # A981 == 1; P807C is read only if the P8078 read is non-zero.
        if B(A985) != 0 and B(A981) == 1:
            b = B(P78); b1 = B(P78 + 1)
            if b != ((~b1) & 0xFF):
                W(C6AC, 1)
            elif b != 0:
                c = B(P7C); c1 = B(P7C + 1)
                if c != ((~c1) & 0xFF):
                    W(C6AC, 1)
        st = dict(m); st['temp'] = temp
        eff = inj_model(B(A985), st)
        m.clear(); m.update(eff)
    elif B(A96A) == 1 and B(CD06) == 0:
        leaf_18C08()
    elif B(A96B) == 1:
        leaf_18C5C()
    elif B(A969) == 1:
        eff = rotor_model(B(A984), dict(m))
        m.clear(); m.update(eff)

    # step 8: common tail (port write/read + A975 ramp)
    if B(A96C) == 1 and B(A987) == 1:
        write8_av(P7A, B(A974))
    r807a = read8_av(P7A, 0x37)
    if B(A989) == 1:
        r7 = r807a & 0xFF
        a974 = B(A974)
        # 0x1847A bf -> increment when r7 < CAL36; fall-through increment when
        # r7>=CAL36 && A974>=CAL37 && A976==0 (sat8 via 0x2478); decrement only
        # when r7>=CAL36 && A974>=CAL37 && A976==1 && A975>0
        if r7 < CAL36:
            W(A975, min(B(A975) + 1, 255))
        elif a974 >= CAL37:
            if B(A976) == 0:
                W(A975, min(B(A975) + 1, 255))
            elif B(A976) == 1 and B(A975) > 0:
                W(A975, (B(A975) - 1) & 0xFF)
        # 0x184F4: write P8078 = CAL35 only when A975 == 0;
        # else (A975 not 0 and not 4) clear A979/A982
        if B(A975) == 0:
            write8_av(P78, CAL35)
        elif B(A975) != 4:
            W(A979, 0)
            W(A982, 0)

    # step 9: epilogue
    W(A983, 0)
    W(A987, 0)
    W(A989, 0)
    W(A985, B(A968))
    W(A984, B(A969))
    W(A986, B(A96A))
    W(A988, B(A96C))
    return m


def rand_temp():
    r = random.random()
    if r < 0.2:
        return random.choice([-40.0, -39.999, -50.0, 30.0, 0.0])
    return random.uniform(-100.0, 150.0)


def seed_ram():
    ram = {}
    for a in range(0xFFFFA968, 0xFFFFA99A):
        ram[a] = random.randint(0, 255)
    ram[A8F1] = random.randint(0, 255)
    ram[C6AC] = random.randint(0, 1)
    ram[ECD] = random.choice([0, 1, 2, 3, 6, 0x80])
    ram[CD06] = random.randint(0, 255)
    for p in (P78, P7A, P7C):
        if random.random() < 0.7:
            v = random.randint(0, 255)
            ram[p] = v; ram[p + 1] = (~v) & 0xFF
        else:
            ram[p] = random.randint(0, 255)
            ram[p + 1] = random.randint(0, 255)
    ram[F746] = random.randint(0, 255); ram[F746 + 1] = random.randint(0, 255)
    t = rand_temp()
    b = struct.unpack('>I', struct.pack('>f', t))[0]
    for i in range(4):
        ram[AA10 + i] = (b >> (8 * (3 - i))) & 0xFF
    return ram, t


def edge_bias(ram):
    roll = random.random()
    if roll < 0.30:
        ram[A97B] = 1          # purge + dispatch path
    elif roll < 0.40:
        ram[A97B] = 0          # dispatch path
    elif roll < 0.45:
        ram[A97B] = 2          # decrement to 1 -> partial epilogue
    elif roll < 0.50:
        ram[A97B] = 0xFF       # decrement to FE -> partial epilogue
    ram[A968] = random.choice([0, 1, 0, 1, random.randint(0, 255)])
    ram[A969] = random.choice([0, 1, 0, 1, random.randint(0, 255)])
    ram[A96A] = random.choice([0, 1, 0, 1, random.randint(0, 255)])
    ram[A96B] = random.choice([0, 1, 0, 1, random.randint(0, 255)])
    ram[A998] = random.choice([0, 1, 0, random.randint(0, 255)])
    ram[A988] = random.choice([0, 1, random.randint(0, 255)])
    ram[A96C] = random.choice([0, 1, random.randint(0, 255)])
    ram[A982] = random.choice([0, 1, random.randint(0, 255)])
    # ramp / ramp-condition edges
    if random.random() < 0.5:
        ram[A975] = random.choice([0, 4, 255, random.randint(0, 255)])
    if random.random() < 0.5:
        ram[A974] = random.choice([0, 59, 60, 0x3B, 0x3C, 0x3D, 0xFF,
                                   random.randint(0, 255)])
    if random.random() < 0.5:
        ram[A976] = random.choice([0, 1, 0xFF, random.randint(0, 255)])
    ram[A987] = random.choice([0, 1, random.randint(0, 255)])
    ram[A989] = random.choice([0, 1, random.randint(0, 255)])
    ram[A980] = random.choice([0, 1, 2, random.randint(0, 255)])
    ram[A981] = random.choice([0, 1, 2, random.randint(0, 255)])


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 30000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x1825E, 0xA97B, 0xCAFE, 0x1234, 0x5555)
    total_fails = 0

    for seed in seeds:
        random.seed(seed)
        fails = 0
        for it in range(N):
            ram, t = seed_ram()
            edge_bias(ram)
            want = model(ram, t)
            try:
                cpu.call(0x1825E, ram=ram, sr=0xF0)
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d: %s' % (seed, it, e))
                fails += 1
                break
            bad = []
            allk = set(k for k in want if isinstance(k, int)) | set(cpu.ram.keys())
            for k in allk:
                if 0xFFFFDE00 <= k <= 0xFFFFDF00:   # task stack area
                    continue
                got = cpu.ram.get(k, 0)
                exp = want.get(k, 0)
                if got != exp:
                    bad.append((k, got, exp))
            if bad:
                print('MISMATCH seed=0x%X iter=%d: %s' %
                      (seed, it, {hex(k): (hex(g), hex(e)) for k, g, e in bad[:12]}))
                print('  A968=%d A969=%d A96A=%d A96B=%d A998=%d A97B=%d A988=%d '
                      'A96C=%d A982=%d ECD=0x%X' %
                      (ram[A968], ram[A969], ram[A96A], ram[A96B], ram[A998],
                       ram[A97B], ram[A988], ram[A96C], ram[A982], ram[ECD]))
                fails += 1
                if fails >= 3:
                    break
        print('  seed 0x%X: %d inputs, fails=%d' % (seed, N, fails))
        total_fails += fails
        if total_fails:
            break

    if total_fails:
        print('\n%d FAILURE(S)' % total_fails)
        sys.exit(1)
    print('OK  0x1825E omp_control_task  (%d random inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    print('\nAll omp_task_0x1825E tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
