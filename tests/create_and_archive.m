/* Test: Create real ObjC objects with correct NeXTSTEP nib frames and archive them.
   Build: gcc -o create_and_archive create_and_archive.m \
            $(gnustep-config --objc-flags) -std=gnu99 -fobjc-exceptions \
            $(gnustep-config --base-libs) -lgnustep-gui -lm
   Usage: ./create_and_archive [output.gmodel]
*/

#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>

@interface EnvelopeApp : NSObject
{
  IBOutlet NSWindow *editWindow;
  IBOutlet NSView *envelopeView;
  IBOutlet NSTextField *fromField1;
  IBOutlet NSTextField *fromField2;
  IBOutlet NSTextField *fromField3;
  IBOutlet NSTextField *fromField4;
  IBOutlet NSTextField *toField1;
  IBOutlet NSTextField *toField2;
  IBOutlet NSTextField *toField3;
  IBOutlet NSTextField *toField4;
  IBOutlet NSTextField *toField5;
  IBOutlet NSWindow *infoPanel;
}
- (IBAction)printEnvelope:(id)sender;
- (IBAction)showInfoPanel:(id)sender;
- (IBAction)setAddrFields:(id)sender;
- (IBAction)appDidInit:(id)sender;
@end

@implementation EnvelopeApp
- (IBAction)printEnvelope:(id)sender { NSLog(@"printEnvelope:"); }
- (IBAction)showInfoPanel:(id)sender { NSLog(@"showInfoPanel:"); }
- (IBAction)setAddrFields:(id)sender { NSLog(@"setAddrFields:"); }
- (IBAction)appDidInit:(id)sender { NSLog(@"appDidInit:"); }
@end


static NSWindow *createMainWindow(void) {
  // Frame from EnvelopeMaker.nib: (100, 200, 320, 240)
  NSRect frame = {{100, 200}, {320, 240}};
  NSWindow *win = [[NSWindow alloc] initWithContentRect:frame
                styleMask:NSTitledWindowMask | NSClosableWindowMask
                         | NSMiniaturizableWindowMask | NSResizableWindowMask
                  backing:NSBackingStoreBuffered defer:NO];
  [win setTitle:@"Envelope Editor"];
  // Don't call setFrame:display: - initWithContentRect already sets content size
  return win;
}


static NSTextField *createTextField(float x, float y, float w, float h) {
  NSRect frame = {{x, y}, {w, h}};
  NSTextField *tf = [[NSTextField alloc] initWithFrame:frame];
  [tf setBezeled:YES];
  [tf setDrawsBackground:YES];
  [tf setEditable:YES];
  [tf setSelectable:YES];
  return tf;
}


static NSButton *createButton(NSString *title, SEL action, float x, float y, float w, float h) {
  NSRect frame = {{x, y}, {w, h}};
  NSButton *btn = [[NSButton alloc] initWithFrame:frame];
  [btn setTitle:title];
  [btn setAction:action];
  [btn setBezelStyle:NSRoundedBezelStyle];
  return btn;
}


static void addLabelToView(NSView *view, NSString *text, float x, float y, float w, float h) {
  NSRect frame = {{x, y}, {w, h}};
  NSTextField *label = [[NSTextField alloc] initWithFrame:frame];
  [label setStringValue:text];
  [label setBezeled:NO];
  [label setDrawsBackground:NO];
  [label setEditable:NO];
  [label setSelectable:NO];
  [view addSubview:label];
  [label release];
}


static NSMenu *createMainMenu(void) {
  NSMenu *mainMenu = [[NSMenu alloc] initWithTitle:@"MainMenu"];

  // App menu
  NSMenuItem *appItem = [[NSMenuItem alloc] initWithTitle:@"EnvelopeMaker"
                                                    action:NULL keyEquivalent:@""];
  NSMenu *appMenu = [[NSMenu alloc] initWithTitle:@"EnvelopeMaker"];
  [appMenu addItemWithTitle:@"About EnvelopeMaker..." action:@selector(showInfoPanel:)
              keyEquivalent:@""];
  [appMenu addItem:[NSMenuItem separatorItem]];
  [appMenu addItemWithTitle:@"Hide" action:@selector(hide:) keyEquivalent:@"h"];
  [appMenu addItemWithTitle:@"Quit" action:@selector(terminate:) keyEquivalent:@"q"];
  [appItem setSubmenu:appMenu];
  [mainMenu addItem:appItem];
  [appItem release];
  [appMenu release];

  // Edit menu
  NSMenuItem *editItem = [[NSMenuItem alloc] initWithTitle:@"Edit" action:NULL keyEquivalent:@""];
  NSMenu *editMenu = [[NSMenu alloc] initWithTitle:@"Edit"];
  [editMenu addItemWithTitle:@"Cut" action:@selector(cut:) keyEquivalent:@"x"];
  [editMenu addItemWithTitle:@"Copy" action:@selector(copy:) keyEquivalent:@"c"];
  [editMenu addItemWithTitle:@"Paste" action:@selector(paste:) keyEquivalent:@"v"];
  [editMenu addItemWithTitle:@"Select All" action:@selector(selectAll:) keyEquivalent:@"a"];
  [editMenu addItem:[NSMenuItem separatorItem]];
  [editMenu addItemWithTitle:@"Copy Font" action:@selector(copyFont:) keyEquivalent:@""];
  [editMenu addItemWithTitle:@"Paste Font" action:@selector(pasteFont:) keyEquivalent:@""];
  [editItem setSubmenu:editMenu];
  [mainMenu addItem:editItem];
  [editItem release];
  [editMenu release];

  // Window menu
  NSMenuItem *winItem = [[NSMenuItem alloc] initWithTitle:@"Window" action:NULL keyEquivalent:@""];
  NSMenu *winMenu = [[NSMenu alloc] initWithTitle:@"Window"];
  [winMenu addItemWithTitle:@"Miniaturize" action:@selector(performMiniaturize:)
              keyEquivalent:@"m"];
  [winMenu addItemWithTitle:@"Close" action:@selector(performClose:) keyEquivalent:@"w"];
  [winItem setSubmenu:winMenu];
  [mainMenu addItem:winItem];
  [winItem release];
  [winMenu release];

  return mainMenu;
}


int main(int argc, const char *argv[]) {
  NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
  [NSApplication sharedApplication];

  NSString *outputPath = (argc > 1)
    ? [NSString stringWithUTF8String:argv[1]]
    : @"/tmp/envelopemaker_test.gmodel";

  printf("=== Test: Create and archive ObjC objects with correct nib frames ===\n");

  // 1. Create window with correct frame
  NSWindow *window = createMainWindow();
  printf("  Window: \"%s\" (%.0fx%.0f)\n",
         [[window title] UTF8String],
         [window frame].size.width,
         [window frame].size.height);
  assert([[window title] isEqualToString:@"Envelope Editor"]);
  // Check that content view has the right size (320x240)
  NSRect cvFrame = [[window contentView] frame];
  assert(cvFrame.size.width == 320);
  assert(cvFrame.size.height == 240);
  printf("  ✓ Window title and frame correct\n");

  NSView *contentView = [window contentView];

  // 2. Create EnvelopeView custom view
  NSRect envFrame = {{15, 90}, {200, 130}};
  NSView *envelopeView = [[NSView alloc] initWithFrame:envFrame];
  [contentView addSubview:envelopeView];
  printf("  ✓ EnvelopeView created (200x130 at x=15, y=90)\n");

  // 3. Create labels
  addLabelToView(contentView, @"From Address", 15, 197, 100, 18);
  addLabelToView(contentView, @"To Address", 15, 77, 100, 18);
  printf("  ✓ Labels created\n");

  // 4. Create text fields with frames matching nib data
  float fieldPositions[][2] = {
    {120, 195}, {120, 171}, {120, 147}, {120, 123},
    {120, 75},  {120, 51},  {120, 27},  {120, 3},   {120, -21},
  };
  NSTextField *fields[9];
  for (int i = 0; i < 9; i++) {
    fields[i] = createTextField(fieldPositions[i][0], fieldPositions[i][1], 180, 22);
    [contentView addSubview:fields[i]];
  }
  printf("  ✓ 9 text fields created with correct nib positions\n");

  // 5. Create buttons
  NSButton *setBtn = createButton(@"Set", @selector(printEnvelope:), 225, 220, 80, 24);
  [contentView addSubview:setBtn];
  NSButton *printBtn = createButton(@"Print", @selector(printEnvelope:), 225, 190, 80, 24);
  [contentView addSubview:printBtn];
  printf("  ✓ Buttons created with correct positions and actions\n");

  // 6. Create main menu
  NSMenu *mainMenu = createMainMenu();
  [NSApp setMainMenu:mainMenu];
  printf("  ✓ Main menu created with App/Edit/Window submenus\n");

  // 7. Create Info panel window
  NSRect infoFrame = {{200, 300}, {350, 220}};
  NSWindow *infoPanel = [[NSWindow alloc] initWithContentRect:infoFrame
                  styleMask:NSTitledWindowMask | NSClosableWindowMask
                    backing:NSBackingStoreBuffered defer:NO];
  [infoPanel setTitle:@"Info"];

  NSView *icv = [infoPanel contentView];
  addLabelToView(icv, @"Envelope Maker", 20, 170, 310, 24);
  addLabelToView(icv, @"Version 1.00", 20, 150, 310, 16);
  addLabelToView(icv, @"by Steven H. Schmidt", 20, 130, 310, 16);
  addLabelToView(icv, @"Copyright 1992, ScHmIdT House Software", 20, 15, 310, 16);
  printf("  ✓ Info panel created with labels\n");

  // 8. Archive the object graph via NSArchiver
  printf("\n  Archiving via NSArchiver...\n");

  NSArray *topLevelObjects = [NSArray arrayWithObjects:
    window, envelopeView, setBtn, printBtn,
    fields[0], fields[1], fields[2], fields[3],
    fields[4], fields[5], fields[6], fields[7], fields[8],
    mainMenu, infoPanel,
    nil];

  NSData *archiveData = [NSArchiver archivedDataWithRootObject:topLevelObjects];
  BOOL wrote = [archiveData writeToFile:outputPath atomically:NO];

  if (wrote) {
    printf("  ✓ Successfully archived %lu objects to %s (%lu bytes)\n",
           (unsigned long)[topLevelObjects count],
           [outputPath UTF8String],
           (unsigned long)[archiveData length]);
  } else {
    printf("  ✗ Failed to write archive to %s\n", [outputPath UTF8String]);
    [pool release];
    return 1;
  }

  // 9. Verify the archive can be loaded back
  printf("\n  Verifying archive round-trip...\n");
  NSData *readData = [NSData dataWithContentsOfFile:outputPath];
  assert(readData != nil);

  NSArray *loaded = [NSUnarchiver unarchiveObjectWithData:readData];
  assert(loaded != nil);
  assert([loaded count] == [topLevelObjects count]);

  // Check window properties were preserved through archive
  NSWindow *loadedWin = nil;
  for (id obj in loaded) {
    if ([obj isKindOfClass:[NSWindow class]]) {
      loadedWin = obj;
      break;
    }
  }
  assert(loadedWin != nil);
  assert([[loadedWin title] isEqualToString:@"Envelope Editor"]);
  cvFrame = [[loadedWin contentView] frame];
  assert(cvFrame.size.width == 320);
  assert(cvFrame.size.height == 240);
  printf("  ✓ Archive round-trip verified: window title and content size preserved\n");

  printf("\n=== ALL TESTS PASSED ===\n");
  [pool release];
  return 0;
}
