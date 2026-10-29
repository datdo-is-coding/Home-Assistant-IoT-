"""IR envelope durations. Protocol layout references are in data/README.md."""
import base64
import binascii
import struct

from ..registry import require

MAX_PULSES = 1024


def relative_panasonic_button(pulses):
    """Recognize the captured A75C4187 button protocol, not a climate state."""
    sections, bits = [], []
    for i in range(0, len(pulses)-1, 2):
        mark, space = pulses[i:i+2]
        if 2800 <= mark <= 4400 and 1200 <= space <= 2200:
            if bits:return None
        elif space > 5000:
            sections.append(bits);bits=[]
        elif 250 <= mark <= 650 and 200 <= space <= 1700:
            bits.append(int(space > 850))
        else:return None
    if bits:sections.append(bits)
    if [len(s) for s in sections] != [64,64]:return None
    state=bytes(sum(bit << j for j,bit in enumerate(s[i:i+8]))
                for s in sections for i in range(0,len(s),8))
    if (state[:8] != bytes.fromhex('0220e00400000006') or
            state[8:13] != bytes.fromhex('0220e00480') or
            sum(state[8:-1]) % 256 != state[-1]):return None
    return {0xa1:'power',0xa5:'temperature_up',0xa4:'temperature_down',
            0xa2:'mode',0xa3:'fan',0xa6:'swing',0x86:'powerful'}.get(state[13])


def validate(pulses, frequency):
    require(type(frequency) is int and 20000 <= frequency <= 60000, 'ir_frequency')
    require(isinstance(pulses, list) and 4 <= len(pulses) <= MAX_PULSES, 'ir_pulses')
    require(all(type(v) is int and 50 <= v <= (20000 if i % 2 == 0 else 200000)
                for i, v in enumerate(pulses)), 'ir_pulses')
    require(sum(pulses) <= 1200000, 'ir_duration')
    return pulses


def encode(pulses, frequency):
    validate(pulses, frequency)
    # 10 us units bound the wire message below 4 KiB; rounding error is <= 5 us.
    ticks = [max(1, (v + 5) // 10) for v in pulses]
    return base64.b64encode(struct.pack('<' + 'H' * len(ticks), *ticks)).decode()


def decode(encoded, frequency):
    require(isinstance(encoded, str) and 12 <= len(encoded) <= 2732, 'ir_pulses')
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        require(False, 'ir_pulses')
    require(len(data) % 2 == 0, 'ir_pulses')
    pulses = [v[0] * 10 for v in struct.iter_unpack('<H', data)]
    return validate(pulses, frequency)


def panasonic_seed(pulses):
    """Recognize two checksum-valid sections, never guess a Panasonic variant."""
    sections, bits = [], []
    for i in range(0, len(pulses) - 1, 2):
        mark, space = pulses[i:i + 2]
        if 2800 <= mark <= 4400 and 1200 <= space <= 2200:
            if bits:
                return None
            continue
        if space > 5000:
            sections.append(bits)
            bits = []
            continue
        if not 250 <= mark <= 650 or not 200 <= space <= 1700:
            return None
        bits.append(int(space > 850))
    if bits:
        sections.append(bits)
    if [len(section) for section in sections] != [64, 152]:
        return None
    state = bytes(sum(bit << j for j, bit in enumerate(section[i:i + 8]))
                  for section in sections for i in range(0, len(section), 8))
    if (state[:4] != b'\x02\x20\xe0\x04' or state[8:12] != state[:4]
            or sum(state[:7]) % 256 != state[7]
            or (sum(state[:-1]) + 244) % 256 != state[-1]):
        return None
    return state.hex()


def panasonic_climate(seed, settings):
    require(isinstance(seed, str) and len(seed) == 54, 'ir_climate_unsupported')
    require(isinstance(settings, dict) and set(settings) == {'power', 'temperature', 'mode', 'fan', 'swing'}, 'ir_state')
    modes = {'auto': 0, 'dry': 2, 'cool': 3, 'heat': 4, 'fan': 6}
    require(type(settings['power']) is bool and type(settings['temperature']) is int
            and 16 <= settings['temperature'] <= 30 and settings['mode'] in modes
            and type(settings['fan']) is int and 0 <= settings['fan'] <= 5
            and type(settings['swing']) is bool, 'ir_state')
    state = bytearray.fromhex(seed)
    # Preserve model-specific bytes from the verified profile; disable captured timers.
    state[13] = (state[13] & 8) | (modes[settings['mode']] << 4) | int(settings['power'])
    temp = 27 if settings['mode'] == 'fan' else settings['temperature']
    state[14] = (state[14] & ~0x3E) | (temp << 1)
    fan = 10 if settings['fan'] == 0 else settings['fan'] + 2
    state[16] = (fan << 4) | (15 if settings['swing'] else 3)
    state[-1] = (sum(state[:-1]) + 244) % 256
    pulses = []
    for section in (state[:8], state[8:]):
        pulses.extend([3456, 1728])
        for value in section:
            for bit in range(8):
                pulses.extend([432, 1296 if (value >> bit) & 1 else 432])
        pulses.extend([432, 10000 if len(section) == 8 else 100000])
    return validate(pulses, 36700)


def nec(address, command, extended=False):
    require(type(address) is int and 0 <= address <= (65535 if extended else 255)
            and type(command) is int and 0 <= command <= 255, 'ir_nec')
    values = [address & 255, (address >> 8) & 255 if extended else (~address & 255), command, ~command & 255]
    result = [9000, 4500]
    for value in values:
        for bit in range(8):
            result += [560, 1690 if value & (1 << bit) else 560]
    return result + [560, 40000]
