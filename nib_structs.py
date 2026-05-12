"""nib_structs.py - Parse NeXTSTEP nib struct data.
Extracts UI layout from raw struct bytes inside Storage objects,
and typedstream objects (0x94 and 84 84 class definitions).
"""

import struct, os, re

NEXTDATA = os.path.expanduser('~/Code/nextdata')
NIB_PATHS = {
    'EnvelopeMaker': os.path.join(NEXTDATA, 'LocalApps/EnvelopeMaker.app/EnvelopeMaker.nib'),
    'Info': os.path.join(NEXTDATA, 'LocalApps/EnvelopeMaker.app/Info.nib'),
}

TE2CLASS = {
    '@@@@s': 'NibData', '%ii': 'Storage', 'i%': 'List',
    '*@': 'CustomObject', '*@ss': 'Cell', '*@ssffi@': 'ButtonCell',
    '*@ss@': 'Control', 'ff': 'MenuTemplate',
    'iiii***@s@': 'WindowTemplate', '%%%%i@@': 'HeaderClass',
    '*@sss@': 'ActionCell', '*fss': 'Font', 's*': 'NXImage',
    '@@:': 'TextField', '@': 'Matrix',
}

CLASS2TE = {
    'WindowTemplate': 'iiii***@s@',
    'MenuTemplate': 'ff', 'Button': '*@ss@',
    'TextField': '@@:', 'TextFieldCell': '*@ss',
    'ButtonCell': '*@ssffi@', 'ActionCell': '*@sss@',
    'Cell': '*@ss', 'Control': '*@ss@', 'Matrix': '@',
    'CustomObject': '*@', 'CustomView': '', 'View': '',
    'Box': '@@', 'Font': '*fss', 'NXImage': 's*',
    'HashTable': 'i%%', 'Object': '', 'List': 'i%',
    'NibData': '@@@@s', 'Storage': '%ii', 'HeaderClass': '%%%%i@@',
    'Responder': '', 'MenuCell': '', 'Menu': '', 'Panel': '',
}


def find_arrays(data):
    arrays = []
    i = 0
    while i < len(data):
        if data[i]==0x84 and i+2<len(data) and data[i+1] in (0x05,0x06,0x07):
            s = i+2
            e = data.find(b']', s, s+32)
            if e > s and data[s]==ord('['):
                decl = data[s:e+1].decode('latin-1',errors='replace')
                try: sz = int(decl[1:-2])
                except: sz = 0
                raw = data[e+1:e+1+sz]
                arrays.append({'decl': decl, 'size': sz, 'data': raw, 'offset': i})
                i = e+1+sz; continue
        i += 1
    return arrays


def extract_strings_and_selectors(raw_data):
    result = {'selectors': set(), 'strings': set()}
    for m in re.finditer(b'[A-Za-z_][A-Za-z0-9_]+:', raw_data):
        try: result['selectors'].add(m.group().decode('ascii'))
        except: pass
    for m in re.finditer(b'[A-Za-z_][A-Za-z0-9_]{2,60}', raw_data):
        try: result['strings'].add(m.group().decode('ascii'))
        except: pass
    i = 0
    while i < len(raw_data) - 5:
        if raw_data[i] == 0x97:
            st = raw_data[i+1]
            if st in (0x0c, 0x84, 0x0e):
                l = raw_data[i+2] if i+2 < len(raw_data) else 0
                if 0 < l < 60 and i+3+l <= len(raw_data):
                    s = raw_data[i+3:i+3+l].decode('latin-1',errors='replace')
                    if st == 0x0e: result['selectors'].add(s)
                    else: result['strings'].add(s)
                i += 3; continue
        i += 1
    return result


# --- Direct struct extraction from raw nib data ---

def decode_short_frame(raw, offset):
    """Decode a NeXTSTEP NXRect from 4 big-endian shorts at offset.
    Returns (x, y, w, h) or None."""
    if offset + 8 > len(raw):
        return None
    x = struct.unpack_from('>h', raw, offset)[0]
    y = struct.unpack_from('>h', raw, offset+2)[0]
    w = struct.unpack_from('>h', raw, offset+4)[0]
    h = struct.unpack_from('>h', raw, offset+6)[0]
    if 0 <= x <= 1200 and 0 <= y <= 1200 and 10 <= w <= 1200 and 10 <= h <= 800:
        return (x, y, w, h)
    return None


def find_window_frames(raw):
    """Find all possible window frames in raw struct data."""
    frames = []
    for i in range(0, len(raw) - 7, 2):
        result = decode_short_frame(raw, i)
        if result:
            frames.append({'offset': i, 'frame': result})
    return frames


def find_strings_in_data(raw):
    """Find C strings (null-terminated ASCII) in raw data."""
    strings = []
    i = 0
    while i < len(raw):
        if 0x20 <= raw[i] <= 0x7e:
            j = i
            while j < len(raw) and 0x20 <= raw[j] <= 0x7e:
                j += 1
            s = raw[i:j].decode('ascii', errors='replace')
            if len(s) >= 3:
                strings.append({'offset': i, 'string': s})
            i = j
        else:
            i += 1
    return strings


def find_windows_in_nib(name):
    """Find window frames and titles from raw nib struct data."""
    path = NIB_PATHS[name]
    with open(path, 'rb') as f:
        data = f.read()

    arrays = find_arrays(data)
    results = []

    for arr in arrays:
        raw = arr['data']
        if len(raw) < 50: continue
        frames = find_window_frames(raw)
        strings = find_strings_in_data(raw)

        if frames:
            for f in frames:
                results.append({
                    'array': arr['decl'],
                    'frame': f['frame'],
                    'offset_in_array': f['offset'],
                })

        if strings:
            pass  # strings are collected below

    return results


def find_all_strings(name):
    """Find all strings in a nib file."""
    path = NIB_PATHS[name]
    with open(path, 'rb') as f:
        data = f.read()
    arrays = find_arrays(data)
    all_strings = set()
    for arr in arrays:
        raw = arr['data']
        strings = find_strings_in_data(raw)
        for s in strings:
            all_strings.add(s['string'])
    return sorted(all_strings)


def find_selectors_in_nib(name):
    """Find all selectors in a nib file using flat regex scan."""
    path = NIB_PATHS[name]
    with open(path, 'rb') as f:
        data = f.read()
    result = extract_strings_and_selectors(data)
    return sorted(result['selectors'])


def find_struct_in_raw(raw, target_string, max_offset=200):
    """Find a UI object struct by looking for a known title string
    and extracting the preceding frame data."""
    s_bytes = target_string.encode('ascii')
    pos = raw.find(s_bytes)
    if pos < 0 or pos > max_offset:
        return None
    # Look backward for a 4-short frame (x, y, w, h) within 100 bytes
    search_start = max(0, pos - 100)
    for offset in range(pos - 8, search_start, -2):
        frame = decode_short_frame(raw, offset)
        if frame:
            return {'frame': frame, 'title_pos': pos, 'frame_offset': offset}
    return None


def load_nib(name):
    """Load a nib file and return metadata."""
    path = NIB_PATHS[name]
    with open(path, 'rb') as f:
        data = f.read()
    arrays = find_arrays(data)
    selectors = find_selectors_in_nib(name)

    return {
        'name': name,
        'path': path,
        'size': len(data),
        'arrays': [{'decl': a['decl'], 'size': a['size']} for a in arrays],
        'selectors': selectors,
    }
