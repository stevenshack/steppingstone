/* gmodel2nib: extract raw nib data from a gmodel and write it back */
#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>

int main(int argc, const char *argv[]) {
    if (argc < 3) {
        printf("Usage: gmodel2nib <input.gmodel> <output.nib>\n");
        return 1;
    }
    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    [NSApplication sharedApplication];
    
    NSString *inPath = [NSString stringWithUTF8String:argv[1]];
    NSString *outPath = [NSString stringWithUTF8String:argv[2]];
    
    NSDictionary *gmodel = [NSUnarchiver unarchiveObjectWithFile:inPath];
    if (!gmodel) { printf("Cannot read %s\n", argv[1]); [pool release]; return 1; }
    
    NSData *rawData = [gmodel objectForKey:@"rawData"];
    if (!rawData) { printf("No rawData in gmodel\n"); [pool release]; return 1; }
    
    [rawData writeToFile:outPath atomically:NO];
    printf("Extracted %s (%lu bytes) -> %s\n",
           argv[1], (unsigned long)[rawData length], argv[2]);
    
    [pool release];
    return 0;
}
