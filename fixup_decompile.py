#!/usr/bin/env python3
"""Fixup decompiled ObjC output:
1. Convert C++-style method signatures to ObjC: Class::method_ -> - (type)method
2. Rename param_1/param_2 to self/_cmd
3. Replace ivar offset access (self + 0xNN) with named access (self->ivarName)
4. Translate (*(code *)&SUB_XXX)(..., @selector(...), ...) to [receiver message:]
"""

import re, sys, json, os


def load_ivar_map(class_info_path):
    with open(class_info_path) as f:
        ci = json.load(f)
    class_ivars = {}
    for cls in ci.get('classes', []):
        ivm = {}
        for iv in cls.get('ivars', []):
            ivm[iv['offset']] = (iv['name'], iv['type'])
        if ivm:
            class_ivars[cls['name']] = ivm
    return class_ivars


def fixup_method_signatures(text):
    """Convert ID Class::method_(ID self, SEL _cmd, ...) to - (void)method:(id) sender.
    Uses the // Selector: [name:] comment above each method to get colons right."""

    # First pass: collect selector info from comments
    sel_map = {}  # address -> selector_name
    for m in re.finditer(r'// Selector:\s*\[([^]]+)\]', text):
        sel_map[id(m)] = m.group(1)

    def fix_sig(m):
        ret = m.group(1).strip()
        cls = m.group(2).strip()
        method_full = m.group(3).strip()
        params = m.group(4).strip()

        ret = 'id' if ret == 'ID' else ret
        ret = 'void' if ret == 'undefined4' or ret == 'undefined' or ret == 'int' else ret

        # Parse params into list of (type, name), skip self and _cmd
        param_list = []
        if params:
            for p in re.split(r',\s*', params):
                p = p.strip()
                if ' ' in p:
                    pt, pn = p.rsplit(' ', 1)
                    param_list.append((pt.strip(), pn.strip()))
                else:
                    param_list.append(('id', p))

        # Determine selector name from comment above the method
        line_start = text.rfind('\n', 0, m.start()) + 1
        pre = text[max(0, line_start - 200):line_start]
        sel_inline = None
        for s in re.finditer(r'// Selector:\s*\[([^]]+)\]', pre):
            sel_inline = s.group(1)

        sel_name = sel_inline if sel_inline else method_full.rstrip('_')

        # Build ObjC method signature
        if ':' in sel_name:
            parts = [p for p in sel_name.split(':') if p]
            # Real params start at index 2 (after self, _cmd)
            real_params = param_list[2:] if len(param_list) > 2 else []

            sig = f'- ({ret})'
            for i, part in enumerate(parts):
                if i > 0:
                    sig += ' '
                sig += f'{part}:'
                if i < len(real_params):
                    ptype = real_params[i][0]
                    ptype = 'id' if ptype == 'ID' else ptype
                    sig += f'({ptype})sender'
                else:
                    sig += '(id)sender'
            return sig
        else:
            # No-colon method
            return f'- ({ret}){sel_name}'

    result = re.sub(
        r'^(\w[\w\s*]*)\s+(\w+)::(\w[\w:]*)\s*\(([^)]*)\)\s*$',
        fix_sig, text, flags=re.MULTILINE
    )
    return result


def fixup_param_names(text):
    """Rename param_N to self/_cmd/argN in method bodies.
    Handles both param_1 and ID param_1 style."""
    lines = text.split('\n')
    result = []
    in_method = False

    for line in lines:
        # Detect start of method body: a line starting with - (
        if re.match(r'^\s*-\s*\(', line):
            in_method = True
            result.append(line)
            continue

        if in_method:
            # param_1 -> self
            line = re.sub(r'(?<!\w)param_1(?!\w)', 'self', line)
            # param_2 -> _cmd
            line = re.sub(r'(?<!\w)param_2(?!\w)', '_cmd', line)
            # param_N -> sender (or argN for params beyond first)
            line = re.sub(r'(?<!\w)param_(\d+)(?!\w)',
                lambda m: 'sender' if int(m.group(1)) == 3 else f'arg{int(m.group(1)) - 2}', line)

            # Check for end of method body (next @interface/@end or empty line before new method)
            if re.match(r'^\s*@', line) or re.match(r'^\s*// Address:', line):
                in_method = False

        result.append(line)

    return '\n'.join(result)


def fixup_ivar_access(text, class_ivars):
    """Replace self + offset / param_1 + offset with self->ivarName."""
    for class_name, ivm in class_ivars.items():
        for offset, (ivar_name, ivar_type) in sorted(ivm.items(), key=lambda x: -x[0]):
            hex_v = f"0x{offset:x}"
            # Match *(undefined4 *)(self + 0xNN) -> self->ivarName
            text = re.sub(
                rf'\*\([^)]*\)\s*\(\s*(?:self|param_1)\s*\+\s*{re.escape(hex_v)}\)',
                f'self->{ivar_name}', text
            )
            text = re.sub(
                rf'\(\s*(?:self|param_1)\s*\+\s*{re.escape(hex_v)}\)',
                f'self->{ivar_name}', text
            )
            text = re.sub(
                rf'(?<!\w)(?:self|param_1)\s*\+\s*{re.escape(hex_v)}(?!\w)',
                f'self->{ivar_name}', text
            )
            # Also match decimal offsets
            text = re.sub(
                rf'\*\([^)]*\)\s*\(\s*(?:self|param_1)\s*\+\s*{re.escape(str(offset))}\)',
                f'self->{ivar_name}', text
            )

    return text


def detect_msg_send_addr(text):
    """Auto-detect the objc_msgSend SUB address from decompiled output.
    It's the SUB_XXXX used with @selector() the most often."""
    counts = {}
    for m in re.finditer(r'SUB_([0-9a-fA-F]+)', text):
        if '@selector' in text[max(0, m.start()-200):m.end()+200]:
            addr = m.group(1).lower()
            counts[addr] = counts.get(addr, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


def translate_msg_send(text):
    """Convert objc_msgSend/receiver calls to ObjC message syntax.
    Handles: (*(code *)&SUB_XXX)(receiver, @selector(msg:), args...)"""
    
    # Step 1: Detect which SUB is objc_msgSend
    msg_send_sub = detect_msg_send_addr(text)
    if not msg_send_sub:
        return text

    # Step 1: Convert only (*(code *)&SUB_MSGSEND)(...) to objc_msgSend(...)
    text = re.sub(
        rf'\(\s*\*\s*\(code\s*\*\)\s*&?SUB_{msg_send_sub}\s*\)\s*\(',
        'objc_msgSend(', text
    )

    def replace_msg_send(m):
        receiver = m.group(1).strip()
        sel_name = m.group(2).strip()
        args_str = (m.group(3) or '').strip()

        # Parse selector and args
        if args_str:
            args = [a.strip() for a in re.split(r',\s*(?![^(]*\))', args_str)]
        else:
            args = []

        if '::' in sel_name:
            sel_name = sel_name.replace('::', ':')

        if ':' in sel_name:
            label_parts = [p for p in sel_name.split(':') if p]
            if len(label_parts) != len(args):
                arg_tail = ', '.join(args) if args else ''
                return f'[{receiver} {sel_name} {arg_tail}];'
            msg = []
            for i, label in enumerate(label_parts):
                msg.append(f'{label}:{args[i]}')
            return f'[{receiver} ' + ' '.join(msg) + '];'
        else:
            arg_tail = ' ' + ', '.join(args) if args else ''
            return f'[{receiver} {sel_name}{arg_tail}];'

    # Match objc_msgSend(receiver, @selector(name:), ...) with semicolon
    pattern = r'objc_msgSend\s*\(\s*([^,]+)\s*,\s*@selector\(([^)]+)\)\s*(?:,\s*(.*?))?\s*\)\s*;?'
    text = re.sub(pattern, replace_msg_send, text)

    # Handle cases where closing paren is on next line
    text = re.sub(r'objc_msgSend\(([^)]*)\s*\n\s*([^)]*)\)', 
        lambda m: f'objc_msgSend({m.group(1).strip()} {m.group(2).strip()})', text)

    # Keep any remaining bare objc_msgSend calls as-is (non-ObjC subroutines
    # that Ghidra routed through the same address by coincidence)

    return text


def extract_c_functions(text):
    """Strip C functions from @implementation blocks to global scope.
    Targets the *Decompiled catch-all class created by build_sources.py."""
    lines = text.split('\n')
    result = []
    i = 0
    c_funcs = []

    while i < len(lines):
        line = lines[i]

        # Detect @implementation for the decompiled catch-all class
        if re.match(r'^\s*@implementation\s+\w+Decompiled\b', line):
            i += 1
            impl_body_lines = []

            # Collect lines until @end
            while i < len(lines) and not re.match(r'^\s*@end\b', lines[i]):
                impl_body_lines.append(lines[i])
                i += 1
            # Skip @end line
            if i < len(lines):
                i += 1

            # The entire body of this class is C functions - extract all of it
            c_funcs.extend(impl_body_lines)
            continue

        # Detect @implementation for regular ObjC classes (keep as-is)
        if re.match(r'^\s*@implementation\s+', line):
            result.append(line)
            i += 1
            while i < len(lines) and not re.match(r'^\s*@end\b', lines[i]):
                result.append(lines[i])
                i += 1
            if i < len(lines):
                result.append(lines[i])
                i += 1
            continue

        # Also strip the @interface for decompiled catch-all
        if re.match(r'^\s*@interface\s+\w+Decompiled\b', line):
            if '@end' in line:
                # @end on the same line; just skip this one line
                i += 1
                continue
            # Multi-line @interface block; skip until @end
            i += 1
            while i < len(lines) and not re.match(r'^\s*@end\b', lines[i]):
                i += 1
            if i < len(lines):
                i += 1
            continue

        # Also strip #pragma mark for the catch-all class
        if re.match(r'^\s*#pragma mark - \w+Decompiled', line):
            i += 1
            continue

        result.append(line)
        i += 1

    # Append extracted C functions at end, outside any @implementation
    if c_funcs:
        c_text = '\n'.join(c_funcs)
        # Replace _main with standard C main()
        # Handles: - (int)_main(...), int _main(...), - (void)_main (no params)
        c_text = re.sub(
            r'(?:-\s*\(.*?\)\s*)?_main(?:\s*\(.*?\))?\s*',
            'int main(int argc, const char *argv[]) ',
            c_text
        )
        c_text = re.sub(
            r'return\s+\w+;\s*\n\s*\}',
            'return NSApplicationMain(argc, argv);\n}',
            c_text
        )
        # Strip any - (type) prefix from other C functions
        c_text = re.sub(r'^\s*-\s*\((\w+)\)\s+(\w+\s*\(.*?\))\s*', r'\1 \2', c_text, flags=re.MULTILINE)
        result.append('\n// C functions extracted from @implementation\n')
        result.append(c_text)

    return '\n'.join(result)


def fixup_source(source_path, class_info_path, output_path=None):
    with open(source_path) as f:
        text = f.read()

    original = text
    changes = []

    class_ivars = {}
    if class_info_path and os.path.exists(class_info_path):
        class_ivars = load_ivar_map(class_info_path)
        changes.append(f"ivar map ({sum(len(v) for v in class_ivars.values())} ivars)")

    # Convert C++ method sigs to ObjC
    text = fixup_method_signatures(text)
    changes.append("method sig fixup")

    # Rename param_N -> self/_cmd/argN
    text = fixup_param_names(text)
    changes.append("param rename")

    # Replace ivar offsets -> names
    if class_ivars:
        text = fixup_ivar_access(text, class_ivars)
        changes.append("ivar names")

    # Translate objc_msgSend calls
    text = translate_msg_send(text)
    changes.append("msgSend translate")

    # Move C functions out of @implementation blocks
    text = extract_c_functions(text)
    changes.append("C func extraction")

    # Cleanup
    text = re.sub(r'(\w+)_\(', r'\1:(', text)
    text = re.sub(r'\{\s*\{', '{', text)

    out_path = output_path or source_path
    with open(out_path, 'w') as f:
        f.write(text)

    diffs = sum(1 for a, b in zip(original.split('\n'), text.split('\n')) if a != b)
    print(f"  {os.path.basename(out_path)}: {diffs} lines changed ({', '.join(changes)})")


def main():
    if len(sys.argv) < 3:
        print("Usage: fixup_decompile.py <source.m> <class_info.json> [output.m]")
        sys.exit(1)
    fixup_source(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)


if __name__ == '__main__':
    main()
