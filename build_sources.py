#!/usr/bin/env python3
"""
Full pipeline: convert Ghidra decompiler output to compilable ObjC source.

Outputs:
  WordPerfect.m       - Method implementations
  WordPerfect.h       - Method declarations
  WordPerfect_stubs.m - Stub definitions for unresolved extern symbols
  GNUmakefile         - Build system
"""

import re
import sys
import os

RETURN_TYPE_MAP = {
    'undefined4': 'void', 'undefined': 'void', 'int': 'int',
    'char': 'BOOL', 'long': 'long', 'short': 'short',
    'void': 'void', 'float': 'float', 'double': 'double',
}

TYPE_MAP = {
    'undefined4': 'uint32_t', 'undefined2': 'uint16_t',
    'undefined1': 'uint8_t', 'undefined8': 'uint64_t',
    'undefined': 'uint32_t',
    'longdouble': 'long double',
    'longlong': 'long long',
    'ulonglong': 'unsigned long long',
    'byte': 'uint8_t',
    'code': 'funcptr_t',
    'ushort': 'uint16_t',
    'uint': 'unsigned int',
}

CAST_MAP = {
    r'\(byte\)': '(uint8_t)', r'\(ushort\)': '(uint16_t)',
    r'\(uint\)': '(unsigned int)',
}

FUNC_MAP = {r'\bNAN\(': 'isnan('}

def ghidra_type_to_objc(enc):
    """Convert ObjC type encoding to (base_type, array_suffix).
    e.g. '@' -> ('id', ''), '[40c]' -> ('char', '[40]')"""
    if not enc: return ("id", "")
    m = {'@': 'id', '#': 'Class', ':': 'SEL', 'c': 'char', 'C': 'unsigned char',
         's': 'short', 'S': 'unsigned short', 'i': 'int', 'I': 'unsigned int',
         'l': 'long', 'L': 'unsigned long', 'q': 'long long', 'Q': 'unsigned long long',
         'f': 'float', 'd': 'double', 'B': 'BOOL', 'v': 'void', '*': 'char *',
         '?': 'void *', '%': 'void *'}
    if enc[0] in m: return (m[enc[0]], "")
    if enc[0] == '^': 
        inner, _ = ghidra_type_to_objc(enc[1:])
        return (inner + " *", "")
    if enc[0] == '[':
        rest = enc[1:]
        num_end = 0
        while num_end < len(rest) and rest[num_end].isdigit():
            num_end += 1
        count = int(rest[:num_end]) if num_end > 0 else 0
        after = rest[num_end:]
        close = after.index(']') if ']' in after else len(after)
        inner, _ = ghidra_type_to_objc(after[:close])
        return (inner, f"[{count}]")
    if enc[0] == '{': return ("void *", "")
    return (enc, "")

APP_NAME = "WordPerfect"
DOWN_ADDR = 0x06003003  # common NeXTSTEP _DOWN call


def parse_decompiled(raw_path):
    funcs = []
    with open(raw_path) as f:
        text = f.read()
    blocks = re.findall(
        r'FUNC_BEGIN 0x0x([0-9a-fA-F]+)\s+(.*?)\n(.*?)FUNC_END',
        text, re.DOTALL
    )
    for addr_str, sel_name, body in blocks:
        sel_name = sel_name.replace('(GhidraScript)', '').replace('INFO', '').strip()
        clean_body = []
        for line in body.split('\n'):
            line = re.sub(r'^.*DecompileBatch\.java>\s*', '', line)
            line = re.sub(r'\s*\(GhidraScript\)\s*$', '', line)
            if line.strip() and not line.startswith('INFO '):
                clean_body.append(line)
        body = '\n'.join(clean_body).strip()
        if body and sel_name:
            funcs.append((addr_str, sel_name, body))
    return funcs


def parse_c_signature(body):
    lines = body.split('\n')
    sig_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('/*') or stripped.startswith('*') or stripped.startswith('//'):
            continue
        sig_lines.append(line)
        if '{' in line:
            break
    sig_text = ' '.join(l.strip() for l in sig_lines if l.strip() and '{' not in l)
    m = re.match(r'(\w[\w\s*]*)\s+\w+\s*\((.*)\)\s*$', sig_text)
    if not m:
        return None, None, body
    ret_type = m.group(1).strip()
    params_str = m.group(2).strip()
    params = []
    if params_str:
        for p in re.split(r',\s*', params_str):
            p = p.strip()
            if ' ' in p:
                ptype, pname = p.rsplit(' ', 1)
                params.append((ptype.strip(), pname.strip()))
            else:
                params.append(('', p))
    full_text = '\n'.join(lines)
    brace_idx = full_text.index('{')
    body_rest = full_text[brace_idx:]
    return ret_type, params, body_rest


def sel_to_objc_sig(sel_name, ret_type):
    objc_ret = RETURN_TYPE_MAP.get(ret_type, 'void')
    if ':' in sel_name:
        n_colons = sel_name.count(':')
        parts = sel_name.split(':')[:n_colons]
        sig = f'- ({objc_ret})'
        for i, p in enumerate(parts):
            if i == 0:
                sig += f"{p}:(id)arg{i+1}"
            else:
                sig += f" {p}:(id)arg{i+1}"
        return sig
    else:
        return f'- ({objc_ret}){sel_name}'


def c_to_objc_body(body, params, ivar_map=None):
    """Convert C function body to ObjC method body by renaming params.

    param_1 -> self, param_2 -> _cmd, param_3+ -> arg names.
    If ivar_map provided, replaces (uintptr_t)self + N with self->ivarName.
    """
    if not params:
        return body

    rename = {}
    for i, (ptype, pname) in enumerate(params):
        escaped = re.escape(pname)
        if pname == 'param_1':
            rename[(rf'(?<!\w){escaped}(?!\w)', pname)] = 'self'
        elif pname == 'param_2':
            rename[(rf'(?<!\w){escaped}(?!\w)', pname)] = '_cmd'
        else:
            arg_idx = i - 1
            rename[(rf'(?<!\w){escaped}(?!\w)', pname)] = f'arg{arg_idx}'

    result = body
    for (pattern, _), replacement in rename.items():
        result = re.sub(pattern, replacement, result)

    result = re.sub(r'(?<!\w)param_([0-9]+)(?!\w)',
        lambda m: f'arg{int(m.group(1)) - 2}' if int(m.group(1)) > 2
                  else ('self' if m.group(1) == '1' else '_cmd'),
        result)

    # Replace ivar offsets with named access if we have the map
    if ivar_map:
        for offset, (ivar_name, ivar_type) in sorted(ivar_map.items(), key=lambda x: -x[0]):
            is_array = ivar_type and ivar_type.startswith('[')
            hex_vals = [f"0x{offset:x}", str(offset)]
            for hv in hex_vals:
                if is_array:
                    # Array ivar: *(type *)(self + OFF) -> self->ivar[0]
                    result = re.sub(
                        rf'\*\([^)]*\)\s*\(self\s*\+\s*{re.escape(hv)}\)',
                        f'self->{ivar_name}[0]', result
                    )
                    # (self + OFF) -> self->ivar  (bare array name as pointer)
                    result = re.sub(
                        rf'\(self\s*\+\s*{re.escape(hv)}\)',
                        f'self->{ivar_name}', result
                    )
                    result = re.sub(
                        rf'(?<!\w)self\s*\+\s*{re.escape(hv)}(?!\w)',
                        f'self->{ivar_name}', result
                    )
                else:
                    # Non-array ivar: *(type *)(self + OFF) -> self->ivar
                    result = re.sub(
                        rf'\*\([^)]*\)\s*\(self\s*\+\s*{re.escape(hv)}\)',
                        f'self->{ivar_name}', result
                    )
                    result = re.sub(
                        rf'\(self\s*\+\s*{re.escape(hv)}\)',
                        f'self->{ivar_name}', result
                    )
                    result = re.sub(
                        rf'(?<!\w)self\s*\+\s*{re.escape(hv)}(?!\w)',
                        f'self->{ivar_name}', result
                    )

    # Fix self ivar access for remaining unmapped offsets: self + N -> (uintptr_t)self + N
    result = re.sub(r'\(self \+ (0x[0-9a-fA-F]+|\d+)\)', r'((uintptr_t)self + \1)', result)

    result = re.sub(r'=\s*self(?:\s*\))?', r'= (int)(uintptr_t)self', result)

    return result


def fix_types(body):
    result = body
    for ghidra_type, c_type in TYPE_MAP.items():
        result = re.sub(rf'(?<!\w){re.escape(ghidra_type)}(?!\w)', c_type, result)
    for ghidra_cast, c_cast in CAST_MAP.items():
        result = re.sub(ghidra_cast, c_cast, result)
    for ghidra_func, c_func in FUNC_MAP.items():
        result = re.sub(ghidra_func, c_func, result)
    return result


def convert_to_objc(addr_str, sel_name, body, ivar_map=None):
    ret_type, params, body_rest = parse_c_signature(body)
    if ret_type is None:
        return None
    sig = sel_to_objc_sig(sel_name, ret_type)
    objc_body = c_to_objc_body(body_rest, params, ivar_map)
    objc_body = fix_types(objc_body)
    return sig, objc_body


def scan_externals(funcs):
    func_refs = set(); data_refs = set(); class_refs = set()
    obj_refs = set()  # data_refs that appear as objc_msgSend receivers
    known_funcs = {'func_0x05003477', 'func_0x05003478'}
    from collections import Counter
    counts = Counter()
    for addr_str, sel_name, body in funcs:
        for m in re.finditer(r'\bfunc_0x([0-9a-fA-F]+)\b', body):
            counts[m.group(1).lower()] += 1
    known_funcs = {'func_0x05003477', 'func_0x05003478'}
    if counts:
        known_funcs.add(f'func_0x{counts.most_common(1)[0][0]}')

    for addr_str, sel_name, body in funcs:
        for m in re.finditer(r'\bfunc_0x([0-9a-fA-F]+)\b', body):
            full = m.group(0)
            if full not in known_funcs:
                func_refs.add(full)
        for m in re.finditer(r'\bSUB_([0-9a-fA-F]+)\b', body):
            full = m.group(0)
            func_refs.add(full)
        # Detect object refs: DAT symbols used as objc_msgSend receivers
        # (appear before @selector in the raw decompile)
        for m in re.finditer(r'func_0x[0-9a-fA-F]+\((_DAT_[0-9a-fA-F]+)\s*,', body):
            obj_refs.add(m.group(1))
        for m in re.finditer(r'func_0x[0-9a-fA-F]+\((DAT_[0-9a-fA-F]+)\s*,', body):
            obj_refs.add(m.group(1))
        for m in re.finditer(r'\b_DAT_[0-9a-fA-F]+\b', body):
            data_refs.add(m.group(0))
        for m in re.finditer(r'\bDAT_[0-9a-fA-F]+\b', body):
            data_refs.add(m.group(0))
        for m in re.finditer(r'\bUNK_[0-9a-fA-F]+\b', body):
            data_refs.add(m.group(0))
        for m in re.finditer(r'\bDOUBLE_[0-9a-fA-F]+\b', body):
            data_refs.add(m.group(0))
        for m in re.finditer(r'\bFLOAT_[0-9a-fA-F]+\b', body):
            data_refs.add(m.group(0))
        for m in re.finditer(r'\bs__[0-9a-fA-F_]+\b', body):
            data_refs.add(m.group(0))
        for m in re.finditer(r'\bs_[A-Za-z][A-Za-z0-9]*_[0-9a-fA-F]+\b', body):
            data_refs.add(m.group(0))
        for m in re.finditer(r'\bPTR_s_[A-Za-z0-9_]+\b', body):
            class_refs.add(m.group(0))
        for m in re.finditer(r'\b(uRam|cRam|iRam|fRam|dRam)[0-9a-fA-F]+\b', body):
            data_refs.add(m.group(0))
        for m in re.finditer(r'\bst_ack[0-9a-fA-F]+\b', body):
            data_refs.add(m.group(0))
        # stack0x* references - Ghidra stack variable artifacts
        for m in re.finditer(r'\bstack0x[0-9a-fA-F]+\b', body):
            data_refs.add(m.group(0))
        for m in re.finditer(r'\b_acStack[_0-9]*\b', body):
            data_refs.add(m.group(0))

    return sorted(func_refs), sorted(data_refs), sorted(class_refs), obj_refs


def generate_m(funcs, output_path, class_info=None):
    """Generate .m file with ObjC method implementations.

    If class_info provided, routes methods to their actual
    classes and replaces ivar offsets with named access.
    """
    imp_to_class = {}
    class_ivars = {}
    if class_info:
        imp_to_class = {int(k): v for k, v in class_info.get('imp_to_class', {}).items()}
        for cls in class_info.get('classes', []):
            om = {}
            for iv in cls.get('ivars', []):
                om[iv['offset']] = (iv['name'], iv['type'])
            class_ivars[cls['name']] = om

    class_groups = {}
    for addr_str, sel_name, body in funcs:
        try:
            addr = int(addr_str, 16)
        except ValueError:
            addr = 0
        cn = imp_to_class.get(addr, f"{APP_NAME}Decompiled")
        class_groups.setdefault(cn, []).append((addr_str, sel_name, body, addr))

    func_refs, data_refs, class_refs, obj_refs = scan_externals(funcs)

    lines = []
    lines.append(f"// NeXTSTEP Decompiled Methods - {APP_NAME}.app")
    lines.append("// Auto-generated\n")
    lines.append("#import <Foundation/Foundation.h>")
    lines.append("#include <stdint.h>")
    lines.append("#include <math.h>")
    lines.append("")

    if func_refs:
        lines.append("// External function references (define in stubs)")
        for ref in func_refs:
            lines.append(f"extern uint32_t {ref}();")
        lines.append("")
    if data_refs:
        lines.append("// External data references (define in stubs)")
        for ref in data_refs:
            if ref in obj_refs:
                lines.append(f"extern id {ref};  // ObjC object pointer")
            else:
                lines.append(f"extern uint32_t {ref};")
        lines.append("")
    if class_refs:
        lines.append("// External ObjC class references (define in stubs)")
        for ref in class_refs:
            lines.append(f"extern Class {ref};")
        lines.append("")

    lines.append("// Forward declare objc_msgSend (implementation in stubs)")
    lines.append("id objc_msgSend();")
    lines.append("")
    lines.append("// Ghidra function pointer type")
    lines.append("typedef void (*funcptr_t)();")
    lines.append("// Ghidra decompiler compatibility macros")
    lines.append("#define ROUND(x) lround(x)")
    lines.append("#define CONCAT16(a,b)  ((a << 8) | b)")
    lines.append("#define CONCAT31(a,b)  ((a << 1) | b)")
    lines.append("#define CONCAT22(a,b)  ((a << 2) | b)")
    lines.append("#define CONCAT24(a,b)  ((a << 4) | b)")
    lines.append("#define CONCAT44(a,b)  ((a << 4) | b)")
    lines.append("")

    converted = 0; failed = 0
    for cn in sorted(class_groups.keys()):
        ivm = class_ivars.get(cn, {})
        lines.append(f"\n#pragma mark - {cn}\n")
        # Find full ivar list from class_info for proper @interface
        ivar_decls = []
        if class_info:
            for cls in class_info.get('classes', []):
                if cls['name'] == cn:
                    for iv in cls.get('ivars', []):
                        objc_t, arr_suffix = ghidra_type_to_objc(iv['type'])
                        ivar_decls.append(f"    {objc_t} {iv['name']}{arr_suffix};")
                    break
        if ivar_decls:
            lines.append(f"@interface {cn} : NSObject {{")
            lines.extend(ivar_decls)
            lines.append("}")
        else:
            lines.append(f"@interface {cn} : NSObject {{ }}")
        lines.append("@end")
        lines.append(f"@implementation {cn}")
        seen = set()
        for addr_str, sel_name, body, addr in class_groups[cn]:
            if sel_name in seen:
                converted += 1; continue
            seen.add(sel_name)
            lines.append(f"\n// Address: 0x{addr_str}")
            r = convert_to_objc(addr_str, sel_name, body, ivm)
            if r:
                sig, ob = r
                lines.append(sig); lines.append(ob)
                converted += 1
            else:
                lines.append(f"// Selector: [{sel_name}]"); lines.append(body)
                failed += 1
        lines.append("@end\n")

    with open(output_path, "w") as f:
        f.write("\n".join(lines))
    print(f"  {output_path}: {converted} converted, {failed} fallback")


def generate_h(funcs, output_path, class_info=None):
    """Generate .h file with ObjC method declarations per class."""
    imp_to_class = {}
    if class_info:
        imp_to_class = {int(k): v for k, v in class_info.get('imp_to_class', {}).items()}

    class_groups = {}
    for addr_str, sel_name, body in funcs:
        try:
            addr = int(addr_str, 16)
        except ValueError:
            addr = 0
        cn = imp_to_class.get(addr, f"{APP_NAME}Decompiled")
        class_groups.setdefault(cn, []).append((addr_str, sel_name, body))

    lines = []
    lines.append(f"// NeXTSTEP Decompiled Method Declarations - {APP_NAME}.app\n")
    lines.append("#import <Foundation/Foundation.h>\n")

    for cn in sorted(class_groups.keys()):
        lines.append(f"@interface {cn} : NSObject {{ }}")
        seen = set()
        for addr_str, sel_name, body in class_groups[cn]:
            r = parse_c_signature(body)
            rt = r[0] if r[0] else 'void'
            sig = sel_to_objc_sig(sel_name, rt) + ';'
            if sig not in seen:
                seen.add(sig)
                lines.append(f"    {sig}")
        lines.append("@end\n")

    with open(output_path, "w") as f:
        f.write("\n".join(lines))
    print(f"  {output_path}")


def generate_stubs(funcs, stubs_path):
    """Generate stub implementations + objc_msgSend bridge + main()."""
    func_refs, data_refs, class_refs, obj_refs = scan_externals(funcs)
    lines = []
    lines.append(f"// Stub definitions for {APP_NAME} - replace with real implementations")
    lines.append("// Auto-generated\n")
    lines.append("#import <Foundation/Foundation.h>")
    lines.append("#import <AppKit/AppKit.h>")
    lines.append("#include <stdint.h>")
    lines.append("#include <stdio.h>")
    lines.append("")

    if func_refs:
        lines.append("#pragma mark - Function stubs\n")
        for ref in func_refs:
            lines.append(f"uint32_t {ref}() {{ return 0; }}")
        lines.append("")

    lines.append("#pragma mark - objc_msgSend bridge\n")
    lines.append("#import <objc/objc.h>")
    lines.append("#import <objc/message.h>")
    lines.append("id objc_msgSend(id self, SEL op, ...) {")
    lines.append("    IMP imp = objc_msg_lookup(self, op);")
    lines.append("    if (!imp) return nil;")
    lines.append("    void *args = __builtin_apply_args();")
    lines.append("    void *result = __builtin_apply((void (*)())imp, args, 128);")
    lines.append("    if (result) return *(id *)result;")
    lines.append("    return nil;")
    lines.append("}")
    lines.append("")
    lines.append("#pragma mark - NeXTSTEP nib compat")
    lines.append("@implementation NSApplication (NibCompat)")
    lines.append("- (void)loadNibSection:(NSString *)name owner:(id)owner {")
    lines.append("    NSString *nibName = [name stringByDeletingPathExtension];")
    lines.append("    [NSBundle loadNibNamed:nibName owner:owner];")
    lines.append("}")
    lines.append("@end")
    lines.append("")

    if data_refs:
        lines.append("#pragma mark - Data stubs\n")
        for ref in data_refs:
            if ref in obj_refs:
                lines.append(f"id {ref} = nil;  // ObjC object - set in app_startup()")
            else:
                lines.append(f"uint32_t {ref} = 0;")
        if obj_refs:
            lines.append("")
            lines.append("// ObjC object pointers (initialized in main() before NSApplicationMain)")
        lines.append("")

    if class_refs:
        lines.append("#pragma mark - Class stubs\n")
    for ref in class_refs:
        lines.append(f"Class {ref} = nil;")
    lines.append("")

    if DOWN_ADDR:
        lines.append("#pragma mark - Runtime helpers\n")
        lines.append("void _DOWN() {}")
        lines.append("")



    lines.append("#pragma mark - App initialization\n")
    lines.append("// Forward declare NSApplicationMain (GNUstep provides it)")
    lines.append("int NSApplicationMain(int argc, const char *argv[]);")
    lines.append("")
    lines.append("// Forward declare UI_Loader (from UI_setup.m)")
    lines.append("@interface UI_Loader : NSObject")
    lines.append("+(void)setupUIForOwner:(id)owner;")
    lines.append("@end")
    lines.append("")
    lines.append("// Forward: build UI from .gmodel config")
    lines.append("static NSMenu *createMainMenu(void) {")
    lines.append("    NSMenu *main = [[NSMenu alloc] initWithTitle:@\"Main\"];")
    lines.append("    // Application menu")
    lines.append("    NSMenu *appMenu = [[NSMenu alloc] initWithTitle:@\"App\"];")
    lines.append("    [appMenu addItemWithTitle:@\"Quit\" action:@selector(terminate:) keyEquivalent:@\"q\"];")
    lines.append("    NSMenuItem *appItem = [[NSMenuItem alloc] initWithTitle:@\"App\" action:NULL keyEquivalent:@\"\"];")
    lines.append("    [appItem setSubmenu:appMenu]; [main addItem:appItem];")
    lines.append("    // Edit menu")
    lines.append("    NSMenu *editMenu = [[NSMenu alloc] initWithTitle:@\"Edit\"];")
    lines.append("    [editMenu addItemWithTitle:@\"Cut\" action:@selector(cut:) keyEquivalent:@\"x\"];")
    lines.append("    [editMenu addItemWithTitle:@\"Copy\" action:@selector(copy:) keyEquivalent:@\"c\"];")
    lines.append("    [editMenu addItemWithTitle:@\"Paste\" action:@selector(paste:) keyEquivalent:@\"v\"];")
    lines.append("    [editMenu addItemWithTitle:@\"Delete\" action:@selector(delete:) keyEquivalent:@\"\"];")
    lines.append("    [editMenu addItem:[NSMenuItem separatorItem]];")
    lines.append("    [editMenu addItemWithTitle:@\"Select All\" action:@selector(selectAll:) keyEquivalent:@\"a\"];")
    lines.append("    NSMenuItem *editItem = [[NSMenuItem alloc] initWithTitle:@\"Edit\" action:NULL keyEquivalent:@\"\"];")
    lines.append("    [editItem setSubmenu:editMenu]; [main addItem:editItem];")
    lines.append("    // Window menu")
    lines.append("    NSMenu *windowMenu = [[NSMenu alloc] initWithTitle:@\"Window\"];")
    lines.append("    [windowMenu addItemWithTitle:@\"Miniaturize\" action:@selector(performMiniaturize:) keyEquivalent:@\"m\"];")
    lines.append("    NSMenuItem *windowItem = [[NSMenuItem alloc] initWithTitle:@\"Window\" action:NULL keyEquivalent:@\"\"];")
    lines.append("    [windowItem setSubmenu:windowMenu]; [main addItem:windowItem];")
    lines.append("    return main;")
    lines.append("}")
    lines.append("")
    lines.append("static void loadUI(void) {")
    lines.append("    [NSApp setMainMenu:createMainMenu()];")
    lines.append("    NSBundle *bndl = [NSBundle mainBundle];")
    lines.append(f"    NSString *path = [bndl pathForResource:@\"{APP_NAME}\" ofType:@\"gmodel\"];")
    lines.append("    if (!path) return;")
    lines.append("    NSDictionary *cfg = [NSUnarchiver unarchiveObjectWithFile:path];")
    lines.append("    if (!cfg) return;")
    lines.append("    NSRect r = NSMakeRect(100, 200,")
    lines.append("        [[cfg objectForKey:@\"windowWidth\"] floatValue],")
    lines.append("        [[cfg objectForKey:@\"windowHeight\"] floatValue]);")
    lines.append("    NSWindow *win = [[NSWindow alloc] initWithContentRect:r")
    lines.append("        styleMask:(NSTitledWindowMask|NSClosableWindowMask")
    lines.append("                |NSMiniaturizableWindowMask)")
    lines.append("        backing:NSBackingStoreBuffered defer:NO];")
    lines.append("    [win setTitle:[cfg objectForKey:@\"windowTitle\"]];")
    lines.append("    NSArray *fields = [cfg objectForKey:@\"fields\"];")
    lines.append("    if (fields) { int i;")
    lines.append("        for (i = 0; i < [fields count]; i++) {")
    lines.append("            NSDictionary *f = [fields objectAtIndex:i];")
    lines.append("            float fy = [[f objectForKey:@\"y\"] floatValue];")
    lines.append("            // Label")
    lines.append("            NSString *label = [f objectForKey:@\"label\"];")
    lines.append("            if (label) {")
    lines.append("                NSTextField *lbl = [[NSTextField alloc]")
    lines.append("                    initWithFrame:NSMakeRect(10, fy, 90, 24)];")
    lines.append("                [lbl setStringValue:label];")
    lines.append("                [lbl setBezeled:NO];")
    lines.append("                [lbl setDrawsBackground:NO];")
    lines.append("                [lbl setEditable:NO];")
    lines.append("                [[win contentView] addSubview:lbl];")
    lines.append("            }")
    lines.append("            // Field")
    lines.append("            NSTextField *tf = [[NSTextField alloc]")
    lines.append("                initWithFrame:NSMakeRect(100, fy, 280, 24)];")
    lines.append("            [tf setBezeled:YES]; [tf setDrawsBackground:YES];")
    lines.append("            [[win contentView] addSubview:tf];")
    lines.append("        }")
    lines.append("    }")
    lines.append("    [win makeKeyAndOrderFront:nil];")
    lines.append("}")
    lines.append("")
    lines.append("int main(int argc, const char *argv[]) {")
    lines.append("    id app = [NSApplication sharedApplication];")
    if obj_refs:
        for ref in obj_refs:
            lines.append(f"    {ref} = app;")
    lines.append("    loadUI();")
    lines.append("    [NSApp activateIgnoringOtherApps:YES];")
    lines.append("    return NSApplicationMain(argc, argv);")
    lines.append("}")

    with open(stubs_path, "w") as f:
        f.write("\n".join(lines))
    print(f"  {stubs_path}: {len(func_refs)} funcs, {len(data_refs)} data, {len(class_refs)} classes")


def generate_makefile(makefile_path, app_name):
    lines = []
    lines.append(f"include $(GNUSTEP_MAKEFILES)/common.make")
    lines.append("")
    lines.append(f"TOOL_NAME = {app_name}")
    lines.append(f"{app_name}_OBJC_FILES = {app_name}.m {app_name}_stubs.m")
    lines.append(f"{app_name}_C_FILES = ")
    lines.append(f"{app_name}_OBJCFLAGS = -fobjc-exceptions -std=gnu99 -fpermissive")
    lines.append(f"ADDITIONAL_LDFLAGS += -lgnustep-gui -lgnustep-base -lobjc")
    lines.append("")
    lines.append(f"include $(GNUSTEP_MAKEFILES)/tool.make")
    lines.append("")
    lines.append("# To run: GNUSTEP_PATH=Info.plist ./obj/EnvelopeMaker")
    lines.append("# Or: openapp ./EnvelopeMaker.app (if built as application)")

    with open(makefile_path, "w") as f:
        f.write("\n".join(lines))
    print(f"  {makefile_path}")


def generate_infoplist(plist_path, app_name):
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<!DOCTYPE plist PUBLIC "-//GNUstep//DTD plist 0.9//EN" "http://www.gnustep.org/plist-0_9.xml">')
    lines.append('<plist version="0.9">')
    lines.append('<dict>')
    lines.append('    <key>ApplicationName</key>')
    lines.append(f'    <string>{app_name}</string>')
    lines.append('    <key>ApplicationDescription</key>')
    lines.append(f'    <string>{app_name} (decompiled from NeXTSTEP binary)</string>')
    lines.append('    <key>ApplicationRelease</key>')
    lines.append('    <string>0.1</string>')
    lines.append('    <key>Authors</key>')
    lines.append('    <string>Decompiled by nextthunk pipeline</string>')
    lines.append('    <key>Copyright</key>')
    lines.append('    <string>Original NeXTSTEP app</string>')
    lines.append('    <key>NSPrincipalClass</key>')
    lines.append('    <string>NSApplication</string>')
    lines.append('</dict>')
    lines.append('</plist>')
    with open(plist_path, "w") as f:
        f.write("\n".join(lines))
    print(f"  {plist_path}")


def write_pipeline_script(script_path, app_dir, i386_path, ghidra_scripts_dir, ghidra_home):
    """Write a single pipeline runner script."""
    content = f'''#!/bin/bash
# Automated decompilation pipeline for NeXTSTEP ObjC binaries
set -e
BIN="$1"
if [ -z "$BIN" ]; then
    echo "Usage: $0 <path-to-universal-binary-or-i386-slice>"
    exit 1
fi

DIR=$(dirname "$BIN")
NAME=$(basename "$BIN")
I386="$DIR/$NAME.i386"
OUTDIR="$DIR/analysis"
GHIDRA="{ghidra_home}"
JAVA_HOME="/usr/lib/jvm/java-25-openjdk-amd64"
export JAVA_HOME

mkdir -p "$OUTDIR"

# Step 1: Extract i386 slice if needed
echo "=== Step 1: Extract i386 ==="
python3 -c "
import struct
with open('$BIN', 'rb') as f:
    data = f.read()
magic = struct.unpack_from('>I', data, 0)[0]
if magic == 0xCAFEBABE:
    narchs = struct.unpack_from('>I', data, 4)[0]
    for i in range(narchs):
        off = 8 + i * 20
        cputype = struct.unpack_from('>I', data, off)[0]
        foff = struct.unpack_from('>I', data, off+8)[0]
        fsz = struct.unpack_from('>I', data, off+12)[0]
        if cputype == 7:
            with open('$I386', 'wb') as out: out.write(data[foff:foff+fsz])
            print(f'  Extracted i386: {{fsz}} bytes')
            import sys; sys.exit(0)
    import sys; sys.exit(1)
elif magic == 0xCEFAEDFE or magic == 0xFEEDFACE:
    import shutil; shutil.copy('$BIN', '$I386'); print('  Already i386')
else:
    import sys; sys.exit(1)
"

# Step 2: Dump ObjC metadata
echo "=== Step 2: ObjC metadata ==="
python3 {ghidra_scripts_dir}/../dump_objc_metadata.py "$I386" "$OUTDIR"

# Step 3: Ghidra decompilation
echo "=== Step 3: Ghidra decompilation ==="
rm -rf /tmp/ghidra_projects/${{NAME}}_decomp.* 2>/dev/null
"$GHIDRA/support/analyzeHeadless" /tmp/ghidra_projects "${{NAME}}_decomp" \
    -import "$I386" -overwrite -noanalysis \
    -scriptPath {ghidra_scripts_dir} \
    -postScript DecompileBatch.java "$OUTDIR/addr_list.txt" > "$OUTDIR/raw_decompile.txt" 2>&1 || true

# Generate addr_list from metadata
grep -oP '0x[0-9a-fA-F]+\\s+\\[.*?\\]' "$OUTDIR/objc_metadata.txt" | sed 's/\\[/|/;s/\\]//' | tr '|' ' ' > "$OUTDIR/addr_list.txt" 2>/dev/null

# Re-run Ghidra with proper addr_list
if [ -s "$OUTDIR/addr_list.txt" ]; then
    rm -rf /tmp/ghidra_projects/${{NAME}}_decomp.* 2>/dev/null
    "$GHIDRA/support/analyzeHeadless" /tmp/ghidra_projects "${{NAME}}_decomp" \
        -import "$I386" -overwrite -noanalysis \
        -scriptPath {ghidra_scripts_dir} \
        -postScript DecompileBatch.java "$OUTDIR/addr_list.txt" > "$OUTDIR/raw_decompile.txt" 2>&1 || true
fi

# Step 4: Build ObjC sources
echo "=== Step 4: Build ObjC sources ==="
python3 {ghidra_scripts_dir}/../build_sources.py

# Step 5: Resolve selectors
echo "=== Step 5: Resolve selectors ==="
python3 {ghidra_scripts_dir}/../resolve_selectors.py "$I386" /tmp/wp_analysis/WordPerfect.m 2>/dev/null > "$OUTDIR/WordPerfect.m"
cp /tmp/wp_analysis/WordPerfect.h "$OUTDIR/WordPerfect.h"
cp /tmp/wp_analysis/WordPerfect_stubs.m "$OUTDIR/WordPerfect_stubs.m"
cp /tmp/wp_analysis/GNUmakefile "$OUTDIR/GNUmakefile"

echo "=== Done! Output in $OUTDIR/ ==="
ls -la "$OUTDIR/WordPerfect."* "$OUTDIR/GNUmakefile"
'''
    with open(script_path, "w") as f:
        f.write(content)
    os.chmod(script_path, 0o755)
    print(f"  {script_path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Convert Ghidra decompiler output to ObjC source")
    parser.add_argument("raw_decompile", help="Path to raw_decompile.txt from Ghidra")
    parser.add_argument("output_dir", help="Directory for generated source files")
    parser.add_argument("--app-name", default=None, help="Application name")
    parser.add_argument("--class-info", default=None, help="Path to class_info.json")
    args = parser.parse_args()

    global APP_NAME
    if args.app_name:
        APP_NAME = args.app_name
    else:
        APP_NAME = os.path.splitext(os.path.basename(args.raw_decompile))[0].replace("raw_decompile", "App")

    class_info = None
    if args.class_info:
        import json
        with open(args.class_info) as f:
            class_info = json.load(f)
        print(f"  Loaded {len(class_info.get('classes',[]))} classes from class_info.json")

    out_dir = args.output_dir
    os.makedirs(out_dir, exist_ok=True)

    print("Parsing decompiled output...")
    funcs = parse_decompiled(args.raw_decompile)
    print(f"  Found {len(funcs)} decompiled functions")

    m_path = os.path.join(out_dir, f"{APP_NAME}.m")
    h_path = os.path.join(out_dir, f"{APP_NAME}.h")
    stubs_path = os.path.join(out_dir, f"{APP_NAME}_stubs.m")
    makefile_path = os.path.join(out_dir, "GNUmakefile")

    print("Generating ObjC .m file...")
    generate_m(funcs, m_path, class_info)

    print("Generating ObjC .h file...")
    generate_h(funcs, h_path, class_info)

    print("Generating stubs...")
    generate_stubs(funcs, stubs_path)

    print("Generating GNUmakefile...")
    generate_makefile(makefile_path, APP_NAME)

    plist_path = os.path.join(out_dir, "Info.plist")
    print("Generating Info.plist...")
    generate_infoplist(plist_path, APP_NAME)

    print("Done.")


if __name__ == "__main__":
    main()
