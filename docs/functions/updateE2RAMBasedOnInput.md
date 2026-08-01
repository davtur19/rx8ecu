# updateE2RAMBasedOnInput @ 0x361AC

_source: AI (Haiku) draft, unverified_

**Purpose:** Dispatcher that routes adaptive/calibration data from external input (UDS, CAN, serial) to appropriate E2 EEPROM regions. Large switch statement mapping input command codes to E2 index + length pairs.

**Inputs:**
- r4: command code (u8: 0-15, 0xFF reserved)
  - 0=?, 1=?, 2=?, ..., 13=?, 14=?, 15=?
  - 0xFF=special command
- r5: unused (zeros out in some paths)
- r6: length parameter or fixed per command
- r7,r8: scratch/work registers

**Outputs / side effects:**
- Calls writeToE2RAMArea_INDEX_ADDR_LEN for each command (with specific index/address/length)
- Modifies E2 EEPROM regions corresponding to command
- Does NOT return data; all outputs are via E2 writes

**Calls:**
- writeToE2RAMArea_INDEX_ADDR_LEN @ 0x385C4: main E2 writer
  - Args: r4=index, r5=RAM address, r6=byte count
  - Called 30+ times with different index/addr combinations

**Behavior:**
1. Load writeToE2RAMArea function address into r14
2. Load E2 index base addresses: r12=0xFFFFC291, r13=0xC1EF (word)
3. Dispatch on r4:
   - **cmd=1**: write 8 bytes from addr 0xFFFFC288 to index 2
   - **cmd=2**: write 2 bytes from addr 0xFFFFC288 to index 2
   - **cmd=13**: write 1 byte from addr 0xFFFFC29E to index 30
   - **cmd=3**: write 1 byte from addr 0xFFFFC284 to index 0
   - **cmd=4**: write 1 byte from addr 0xFFFFC291 to index 12; also write 1 byte from 0xC1EE to index 14; also write 1 byte from 0xC1F0 to index 16; also write 1 byte from 0xFFFFC294 to index 19
   - **cmd=5**: write 1 byte from 0xC1F0 (index 18)
   - **cmd=6**: write 1 byte from 0xFFFFC294 (index 19)
   - **cmd=7**: write 2 bytes from 0xFFFFC296 (index 22)
   - **cmd=8**: write 2 bytes from 0xFFFFC298 (index 24)
   - **cmd=12**: write multiple (index 12, 13, 14, 15, 16, 20, 18, 19)
   - **cmd=9**: write 1 byte from addr r12 (index 12)
   - **cmd=10**: write 8 bytes from 0xFFFFC288 (index 2)
   - **cmd=11**: write 8 bytes from 0xFFFFC288 (index 2) then 1 byte from 0xFFFFC290 (index 10)
   - **cmd=14**: write 1 byte from 0xFFFFC292 (index 13)
   - **cmd=15**: write 1 byte from 0xFFFFC293 (index 15)
   - **cmd=0xFF**: write 1 byte from 0xFFFFC284 (index 0) then write 8 bytes from 0xFFFFC288 (index 2) then 1 byte from 0xFFFFC290 (index 10)
   - Default: no operation (bra to exit)

**Draft C:**
```c
void updateE2RAMBasedOnInput(u8 cmd) {
  // Index addresses (where to write in E2)
  const u16 indices[] = {
    0xFFFFC284,  // index 0
    0xFFFFC288,  // index 2
    0xFFFFC290,  // index 10
    0xFFFFC291,  // index 12
    0xFFFFC292,  // index 13
    0xFFFFC293,  // index 14
    0xFFFFC294,  // index 15
    0xFFFFC295,  // index 16
    0xFFFFC296,  // index 18
    0xFFFFC298,  // index 19
    0xC1EE,      // index 14 (alternative?)
    0xC1F0,      // index 16 (alternative?)
  };
  
  switch (cmd) {
    case 1:
      writeToE2RAMArea(2, (u8*)0xFFFFC288, 8);
      break;
    case 2:
      writeToE2RAMArea(2, (u8*)0xFFFFC288, 2);
      break;
    case 4:
      writeToE2RAMArea(12, (u8*)0xFFFFC291, 1);
      writeToE2RAMArea(14, (u8*)0xC1EE, 1);
      writeToE2RAMArea(16, (u8*)0xC1F0, 1);
      break;
    // ... many more cases ...
    case 0xFF:
      writeToE2RAMArea(0, (u8*)0xFFFFC284, 1);
      writeToE2RAMArea(2, (u8*)0xFFFFC288, 8);
      writeToE2RAMArea(10, (u8*)0xFFFFC290, 1);
      break;
    default:
      break;
  }
}
```

**Confidence:** high
- Function dispatch structure (command-based switch) very clear from assembly
- E2 index/address/length tuples directly readable from jsr calls
- All function calls and addresses are definite (no speculation on control flow)

**Uncertainties:**
- What do the E2 index values (0, 2, 10, 12-15, 18-19, 22, 24, 26-30) represent in ECU calibration/adaptive data layout?
- Why are some indices accessed multiple times in a single command (e.g., cmd=4)?
- What is the semantic meaning of cmd codes 0-15 in the UDS/CAN protocol?
- Are the RAM addresses (0xFFFFCxxx, 0xC1Ex) temporary buffers or persistent adaptive data structures?
