#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>
#include <GNUstepGUI/GSNibContainer.h>

int main() {
    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    
    // Create GSNibContainer
    id container = [[NSClassFromString(@"GSNibContainer") alloc] init];
    
    // Set up name table (owner = NSApp)
    NSMutableDictionary *nameTable = [NSMutableDictionary dictionary];
    [nameTable setObject:[NSApplication sharedApplication] forKey:@"NSOwner"];
    
    // Create window
    NSRect r = NSMakeRect(100, 200, 300, 200);
    NSWindow *win = [[NSWindow alloc] initWithContentRect:r
        styleMask:NSTitledWindowMask backing:NSBackingStoreBuffered defer:NO];
    [win setTitle:@"Test GModel"];
    
    // Create text field
    NSTextField *tf = [[NSTextField alloc] initWithFrame:NSMakeRect(20, 80, 200, 22)];
    [tf setStringValue:@"Hello from gmodel!"];
    [[win contentView] addSubview:tf];
    
    // Set up top level objects
    NSSet *topLevel = [NSSet setWithObject:win];
    
    // Set via KVC since we don't have the header
    [container setValue:nameTable forKey:@"nameTable"];
    [container setValue:topLevel forKey:@"topLevelObjects"];
    
    // Archive and save
    NSData *data = [NSArchiver archivedDataWithRootObject:container];
    [data writeToFile:@"/tmp/test_container.gmodel" atomically:NO];
    NSLog(@"Created gmodel: %lu bytes", (unsigned long)[data length]);
    
    // Test loading
    id loaded = [NSUnarchiver unarchiveObjectWithData:data];
    NSLog(@"Loaded: %@", loaded);
    
    [pool release];
    return 0;
}
