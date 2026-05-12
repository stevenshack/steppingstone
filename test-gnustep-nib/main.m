#include <Foundation/Foundation.h>
#include <AppKit/AppKit.h>

int main(int argc, const char *argv[]) {
  NSAutoreleasePool *pool = [NSAutoreleasePool new];

  [NSApplication sharedApplication];

  NSString *path = @"Model.gmodel";
  NSData *data = [NSData dataWithContentsOfFile:path];
  if (!data) {
    NSLog(@"Failed to find %@", path);
    [pool release];
    return 1;
  }

  NSUnarchiver *unarchiver = [[NSUnarchiver alloc] initForReadingWithData:data];
  NSArray *root = [unarchiver decodeObject];
  [unarchiver release];

  for (id obj in root) {
    if ([obj isKindOfClass:[NSWindow class]]) {
      [(NSWindow *)obj makeKeyAndOrderFront:nil];
    }
  }

  [[NSApplication sharedApplication] run];
  [pool release];
  return 0;
}
