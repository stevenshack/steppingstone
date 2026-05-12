#!/usr/bin/env python3
"""patch_stubs.py - Patch generated stubs for gmodel runtime loading."""

import re, sys

def patch_stubs(stubs_path, app_name):
    with open(stubs_path) as f:
        content = f.read()

    # Remove old programmatic UI code
    content = re.sub(r'// Forward: build UI from \.gmodel config\n.*?(?=int main)', '', content, flags=re.DOTALL)
    content = re.sub(r'static void loadUI.*?\n\}', '', content, flags=re.DOTALL)
    content = re.sub(r'static NSMenu \*createMainMenu.*?\n\}', '', content, flags=re.DOTALL)

    # Replace main() to load _runtime.gmodel
    content = re.sub(
        r'int main\(int argc, const char \*argv\[\]\) \{[^}]*'
        r'_DAT_\w+ = app;[^}]*'
        r'return NSApplicationMain\(argc, argv\);\n\}',
        'int main(int argc, const char *argv[]) {\n'
        '    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];\n'
        '    id app = [NSApplication sharedApplication];\n'
        '    _DAT_04030000 = app;\n'
        '    id fileOwner = [[EnvelopeApp alloc] init];\n'
        '    [NSBundle loadNibNamed:@"%s_runtime" owner:fileOwner];\n'
        '    [NSApp activateIgnoringOtherApps:YES];\n'
        '    [pool release];\n'
        '    return NSApplicationMain(argc, argv);\n'
        '}' % app_name,
        content
    )

    # Remove stale forward declarations
    content = re.sub(r'// Forward declare UI_Loader.*?\n@end\n', '', content)
    content = re.sub(r'// Forward declare NSApplicationMain.*?\n', '', content)

    # Add import for GMArchiver and EnvelopeMaker header
    content = content.replace(
        '#import <AppKit/AppKit.h>',
        '#import <AppKit/AppKit.h>\n#import <GNUstepGUI/GMArchiver.h>\n#import "EnvelopeMaker.h"'
    )

    # Append helper code
    content += '''
static NSComparisonResult compareViewY(id v1, id v2, void *ctx)
{
  float y1 = [v1 frame].origin.y;
  float y2 = [v2 frame].origin.y;
  if (y1 > y2) return NSOrderedAscending;
  if (y1 < y2) return NSOrderedDescending;
  return NSOrderedSame;
}

static NSMenu *buildMainMenu(void)
{
  NSMenu *main = [[NSMenu alloc] initWithTitle:@"MainMenu"];
  NSMenu *appMenu = [[NSMenu alloc] initWithTitle:@"EnvelopeMaker"];
  [appMenu addItemWithTitle:@"About EnvelopeMaker..." action:@selector(showInfoPanel:) keyEquivalent:@""];
  [appMenu addItem:[NSMenuItem separatorItem]];
  [appMenu addItemWithTitle:@"Hide" action:@selector(hide:) keyEquivalent:@"h"];
  [appMenu addItemWithTitle:@"Quit" action:@selector(terminate:) keyEquivalent:@"q"];
  NSMenuItem *appItem = [[NSMenuItem alloc] initWithTitle:@"EnvelopeMaker" action:NULL keyEquivalent:@""];
  [appItem setSubmenu:appMenu]; [main addItem:appItem];
  NSMenu *editMenu = [[NSMenu alloc] initWithTitle:@"Edit"];
  [editMenu addItemWithTitle:@"Cut" action:@selector(cut:) keyEquivalent:@"x"];
  [editMenu addItemWithTitle:@"Copy" action:@selector(copy:) keyEquivalent:@"c"];
  [editMenu addItemWithTitle:@"Paste" action:@selector(paste:) keyEquivalent:@"v"];
  [editMenu addItemWithTitle:@"Select All" action:@selector(selectAll:) keyEquivalent:@"a"];
  [editMenu addItem:[NSMenuItem separatorItem]];
  [editMenu addItemWithTitle:@"Copy Font" action:@selector(copyFont:) keyEquivalent:@""];
  [editMenu addItemWithTitle:@"Paste Font" action:@selector(pasteFont:) keyEquivalent:@""];
  [editMenu addItemWithTitle:@"Copy Ruler" action:@selector(copyRuler:) keyEquivalent:@""];
  [editMenu addItemWithTitle:@"Paste Ruler" action:@selector(pasteRuler:) keyEquivalent:@""];
  NSMenuItem *editItem = [[NSMenuItem alloc] initWithTitle:@"Edit" action:NULL keyEquivalent:@""];
  [editItem setSubmenu:editMenu]; [main addItem:editItem];
  NSMenu *windowMenu = [[NSMenu alloc] initWithTitle:@"Window"];
  [windowMenu addItemWithTitle:@"Miniaturize" action:@selector(performMiniaturize:) keyEquivalent:@"m"];
  [windowMenu addItemWithTitle:@"Close" action:@selector(performClose:) keyEquivalent:@"w"];
  NSMenuItem *windowItem = [[NSMenuItem alloc] initWithTitle:@"Window" action:NULL keyEquivalent:@""];
  [windowItem setSubmenu:windowMenu]; [main addItem:windowItem];
  return main;
}

@implementation EnvelopeApp (NibConnector)
- (void)awakeFromNib
{
  [NSApp setMainMenu:buildMainMenu()];
  NSArray *wins = [NSApp windows];
  for (NSWindow *win in wins) {
    if (![NSStringFromClass([win class]) hasPrefix:@"NSWindow"]) continue;
    if (![self valueForKey:@"editWindow"])
      [self setValue:win forKey:@"editWindow"];
    [win setContentSize:NSMakeSize(320, 240)];
    [win center];
    NSView *cv = [win contentView];
    [cv setFrame:NSMakeRect(0, 0, 320, 240)];

    // Fix subview frames (unarchiver may give wrong frames)
    NSMutableArray *fields = [NSMutableArray array];
    float fieldY[] = {195, 171, 147, 123, 75, 51, 27, 3, -21};
    int fi = 0;
    float labelY[] = {197, 77};
    float buttonY[] = {220, 190};
    int bi = 0, li = 0;
    for (NSView *sub in [cv subviews]) {
      if ([sub isKindOfClass:[EnvelopeView class]]) {
        [self setValue:sub forKey:@"envelopeView"];
        [sub setFrame:NSMakeRect(15, 90, 200, 130)];
      } else if ([sub isKindOfClass:[NSTextField class]]) {
        // Check if it's an editable field or a label
        if (fi < 9 && ([[sub stringValue] length] == 0 || [[sub stringValue] isEqual:@""])) {
          [sub setFrame:NSMakeRect(120, fieldY[fi], 180, 22)];
          [sub setBezeled:YES];
          [fields addObject:sub];
          fi++;
        } else if (li < 2) {
          labelY[li] = (li == 0) ? 197 : 77;
          [sub setFrame:NSMakeRect(15, labelY[li], 100, 18)];
          li++;
        }
      } else if ([sub isKindOfClass:[NSButton class]]) {
        if (bi < 2) {
          [sub setFrame:NSMakeRect(225, buttonY[bi], 80, 24)];
          bi++;
        }
      }
    }
    [fields sortUsingFunction:compareViewY context:NULL];
    if ([fields count] >= 9) {
      [self setValue:[fields objectAtIndex:0] forKey:@"fromField1"];
      [self setValue:[fields objectAtIndex:1] forKey:@"fromField2"];
      [self setValue:[fields objectAtIndex:2] forKey:@"fromField3"];
      [self setValue:[fields objectAtIndex:3] forKey:@"fromField4"];
      [self setValue:[fields objectAtIndex:4] forKey:@"toField1"];
      [self setValue:[fields objectAtIndex:5] forKey:@"toField2"];
      [self setValue:[fields objectAtIndex:6] forKey:@"toField3"];
      [self setValue:[fields objectAtIndex:7] forKey:@"toField4"];
      [self setValue:[fields objectAtIndex:8] forKey:@"toField5"];
    }
    [win makeKeyAndOrderFront:nil];
  }
}
@end
'''

    with open(stubs_path, 'w') as f:
        f.write(content)

    print(f"  Patched stubs: {stubs_path}")

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        patch_stubs(sys.argv[1], sys.argv[2])
    else:
        print("Usage: patch_stubs.py <stubs_path> <app_name>")
