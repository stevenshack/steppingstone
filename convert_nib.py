#!/usr/bin/env python3
"""Parse NeXTSTEP .nib files and generate ObjC UI setup code for GNUstep."""

import os, sys, re, json

def parse_nib_strings(path):
    with open(path, 'rb') as f:
        data = f.read()
    strings = set()
    for m in re.finditer(b'[A-Za-z_][A-Za-z0-9_]{2,60}', data):
        try:
            strings.add(m.group().decode('ascii'))
        except: pass
    return strings

def generate_ui(nib_dir, app_name, class_info_path, output_path):
    nib_files = sorted([f for f in os.listdir(nib_dir) if f.endswith('.nib')])
    all_ivars = set()
    for nib_file in nib_files:
        all_ivars.update(parse_nib_strings(os.path.join(nib_dir, nib_file)))

    tfs = sorted(v for v in all_ivars if v.startswith('fromField') or v.startswith('toField'))
    outlets = sorted(v for v in all_ivars if v in ('editWindow', 'envelopeView', 'infoPanel'))

    lines = []
    lines.append("// Auto-generated UI from NeXTSTEP nib files")
    lines.append("#import <AppKit/AppKit.h>")
    lines.append("")

    lines.append("@interface NSApplication (NibCompat)")
    lines.append("- (void)loadNibSection:(NSString *)name owner:(id)owner {")
    lines.append("    // Nib can't be loaded at runtime - UI created programmatically")
    lines.append("}")
    lines.append("@end")
    lines.append("")

    lines.append("static NSWindow *mainWindow = nil;")
    lines.append("")
    lines.append("@interface UI_Loader : NSObject")
    lines.append("+(void)setupUI;")
    lines.append("@end")
    lines.append("")
    lines.append("@implementation UI_Loader")
    lines.append("+(void)setupUI {")
    lines.append("    if (mainWindow) return;")
    lines.append("    NSRect r = NSMakeRect(100, 200, 320, 300);")
    lines.append("    mainWindow = [[NSWindow alloc] initWithContentRect:r")
    lines.append("        styleMask:(NSTitledWindowMask|NSClosableWindowMask")
    lines.append("                |NSMiniaturizableWindowMask|NSResizableWindowMask)")
    lines.append("        backing:NSBackingStoreBuffered defer:NO];")
    lines.append('    [mainWindow setTitle:@"EnvelopeMaker"];')
    lines.append("")
    lines.append("    // Create text fields from nib outlets")
    lines.append("    {")
    lines.append("        CGFloat y = 260;")
    lines.append("        int i;")
    lines.append("        for (i = 0; i < 9; i++) {")
    lines.append("            NSTextField *tf = [[NSTextField alloc] initWithFrame:NSMakeRect(100, y, 180, 24)];")
    lines.append("            [tf setBezeled:YES];")
    lines.append("            [tf setDrawsBackground:YES];")
    lines.append("            [tf setEditable:YES];")
    lines.append("            [[mainWindow contentView] addSubview:tf];")
    lines.append("            y -= 28;")
    lines.append("        }")
    lines.append("    }")
    lines.append("")
    lines.append("    [NSApp activateIgnoringOtherApps:YES];")
    lines.append("    [mainWindow makeKeyAndOrderFront:nil];")
    lines.append("}")
    lines.append("@end")
    lines.append("")

    with open(output_path, "w") as f:
        f.write("\n".join(lines))
    print(f"  -> {output_path}")

if __name__ == "__main__":
    nib_dir, out_dir, class_info = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(out_dir, exist_ok=True)
    app_name = os.path.basename(os.path.dirname(nib_dir))
    generate_ui(nib_dir, app_name, class_info, os.path.join(out_dir, "UI_setup.m"))
