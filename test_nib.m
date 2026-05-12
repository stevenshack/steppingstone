#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>

int main(int argc, const char *argv[]) {
    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    
    [NSApplication sharedApplication];
    
    // Try loading the nib using various methods
    NSString *paths[] = {
        @"EnvelopeMaker.nib",
        @"EnvelopeMaker",
        @"./EnvelopeMaker.nib",
        @"../EnvelopeMaker.nib",
    };
    
    for (int i = 0; i < 4; i++) {
        NSString *path = paths[i];
        BOOL ok = [NSBundle loadNibNamed:path owner:NSApp];
        NSLog(@"loadNibNamed:\"%@\" owner:NSApp -> %d", path, ok);
    }
    
    // Try with explicit bundle
    NSBundle *mainBundle = [NSBundle mainBundle];
    NSLog(@"Main bundle: %@", mainBundle);
    NSLog(@"Bundle path: %@", [mainBundle bundlePath]);
    NSLog(@"Resources: %@", [mainBundle pathsForResourcesOfType:@"nib" inDirectory:nil]);
    
    // Try loading from Resources
    NSString *resPath = [mainBundle pathForResource:@"EnvelopeMaker" ofType:@"nib"];
    NSLog(@"pathForResource: %@", resPath);
    if (resPath) {
        BOOL ok2 = [mainBundle loadNibFile:resPath externalNameTable:[NSDictionary dictionaryWithObject:NSApp forKey:@"NSOwner"] withZone:nil];
        NSLog(@"loadNibFile result: %d", ok2);
    }
    
    [pool release];
    return 0;
}
