/* Try loading nib via GSModelLoaderFactory which checks all registered loaders */
#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>
#include <GNUstepGUI/GSModelLoaderFactory.h>

int main(int argc, const char *argv[]) {
    if (argc < 3) {
        printf("Usage: nib2gmodel <input.nib> <output.gmodel>\n");
        return 1;
    }
    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    [NSApplication sharedApplication];
    
    NSString *inPath = [NSString stringWithUTF8String:argv[1]];
    NSString *outPath = [NSString stringWithUTF8String:argv[2]];
    
    // Get a model loader for the nib file
    GSModelLoader *loader = [GSModelLoaderFactory modelLoaderForFileName:inPath];
    if (loader) {
        printf("Got loader: %s\n", [[[loader class] description] UTF8String]);
        NSDictionary *nameTable = [NSDictionary dictionaryWithObject:NSApp forKey:@"NSOwner"];
        BOOL ok = [loader loadModelFile:inPath externalNameTable:nameTable withZone:NULL];
        if (ok) {
            printf("Loaded via model loader!\n");
            // Try to get the root object - the loader might populate NSApp's name table
            // Or the objects are already instantiated
            NSData *data = [NSArchiver archivedDataWithRootObject:nameTable];
            [data writeToFile:outPath atomically:NO];
            printf("Saved %lu bytes\n", (unsigned long)[data length]);
            [pool release]; return 0;
        }
    } else {
        printf("No model loader found for .nib files\n");
    }
    
    printf("Model loader approach failed\n");
    [pool release];
    return 1;
}
