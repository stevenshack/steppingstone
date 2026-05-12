/* Use GormCore framework to load a NeXTSTEP nib and save as .gmodel */
#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>
#include <GormCore/GormDocument.h>

int main(int argc, const char *argv[]) {
    if (argc < 3) {
        printf("Usage: nib2gmodel <input.nib> <output.gmodel>\n");
        return 1;
    }
    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    [NSApplication sharedApplication];
    
    NSString *inPath = [NSString stringWithUTF8String:argv[1]];
    NSString *outPath = [NSString stringWithUTF8String:argv[2]];
    
    // Approach: read the nib data and use GormCore to unarchive it
    NSData *nibData = [NSData dataWithContentsOfFile:inPath];
    if (!nibData) { printf("Cannot read %s\n", argv[1]); [pool release]; return 1; }
    
    // Try using NSUnarchiver with GormCore's support for typedstream
    id root = nil;
    @try {
        root = [NSUnarchiver unarchiveObjectWithData:nibData];
    } @catch (NSException *e) {
        // Expected - GNUstep NSUnarchiver doesn't support NeXTSTEP format
    }
    
    if (root) {
        printf("Unarchived directly\n");
        NSData *data = [NSArchiver archivedDataWithRootObject:root];
        [data writeToFile:outPath atomically:NO];
        printf("Saved %ld bytes\n", (long)[data length]);
    } else {
        printf("Direct unarchive failed - trying GormDocument...\n");
        // Load using NSDocument API
        NSError *error = nil;
        GormDocument *doc = [[GormDocument alloc] initWithContentsOfURL:[NSURL fileURLWithPath:inPath]
                                                                 ofType:@"nib" error:&error];
        if (!doc) {
            // Try older API
            doc = [[GormDocument alloc] initWithContentsOfFile:inPath ofType:@"nib"];
        }
        if (doc) {
            printf("Loaded via GormDocument\n");
            NSData *data = [doc archiverData];
            if (data) {
                [data writeToFile:outPath atomically:NO];
                printf("Saved %ld bytes\n", (long)[data length]);
            } else {
                printf("No archiverData, trying topLevelObjects...\n");
                NSSet *objects = [doc topLevelObjects];
                if (objects) {
                    data = [NSArchiver archivedDataWithRootObject:objects];
                    [data writeToFile:outPath atomically:NO];
                    printf("Saved %ld bytes\n", (long)[data length]);
                }
            }
        } else {
            printf("Failed to load via GormDocument\n");
        }
    }
    
    [pool release];
    return 0;
}
