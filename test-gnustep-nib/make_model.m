#include <Foundation/Foundation.h>
#include <AppKit/AppKit.h>

int main(int argc, const char *argv[]) {
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  [NSApplication sharedApplication];

  NSRect winRect = {{100, 100}, {400, 300}};
  NSWindow *window = [[NSWindow alloc] initWithContentRect:winRect
                                                styleMask:NSTitledWindowMask
                                                          | NSClosableWindowMask
                                                          | NSResizableWindowMask
                                                  backing:NSBackingStoreBuffered
                                                    defer:NO];
  [window setTitle:@"Test Window"];

  NSRect btnRect = {{150, 130}, {100, 30}};
  NSButton *button = [[NSButton alloc] initWithFrame:btnRect];
  [button setTitle:@"Click Me"];
  [button setBezelStyle:NSRoundedBezelStyle];
  [[window contentView] addSubview:button];

  NSArray *objects = [NSArray arrayWithObjects:window, button, nil];
  BOOL result = [NSArchiver archiveRootObject:objects toFile:@"Model.gmodel"];

  if (result) {
    NSLog(@"Model.gmodel created successfully");
  } else {
    NSLog(@"Failed to create Model.gmodel");
  }

  [pool release];
  return result ? 0 : 1;
}
