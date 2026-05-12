/* Build runtime UI gmodel from nib gmodel metadata (not class layout) */
#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>

int main(int argc, const char *argv[]) {
    if (argc < 3) {
        printf("Usage: build_runtime_gmodel <nib_gmodel> <output.gmodel>\n");
        return 1;
    }
    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    [NSApplication sharedApplication];
    
    NSString *inPath = [NSString stringWithUTF8String:argv[1]];
    NSString *outPath = [NSString stringWithUTF8String:argv[2]];
    
    // Read the nib gmodel containing raw data + metadata
    NSDictionary *nibGmodel = [NSUnarchiver unarchiveObjectWithFile:inPath];
    if (!nibGmodel) { printf("Cannot read %s\n", argv[1]); [pool release]; return 1; }
    
    // Get field specs from metadata
    NSArray *fieldSpecs = [nibGmodel objectForKey:@"fields"];
    if (!fieldSpecs) fieldSpecs = [NSArray array];
    
    // Build runtime config
    NSMutableDictionary *config = [NSMutableDictionary dictionary];
    float windowH = 200 + [fieldSpecs count] * 28;
    [config setObject:[NSNumber numberWithFloat:400] forKey:@"windowWidth"];
    [config setObject:[NSNumber numberWithFloat:windowH] forKey:@"windowHeight"];
    
    // Use nib name without _nib suffix as window title
    NSString *nibName = [[[inPath lastPathComponent] stringByDeletingPathExtension] 
                           stringByReplacingOccurrencesOfString:@"_nib" withString:@""];
    [config setObject:[nibName capitalizedString] forKey:@"windowTitle"];
    
    // Build field specs with positions
    NSMutableArray *fields = [NSMutableArray array];
    float y = windowH - 40;
    int i;
    for (i = 0; i < [fieldSpecs count]; i++) {
        NSDictionary *spec = [fieldSpecs objectAtIndex:i];
        NSString *name = [spec objectForKey:@"name"];
        NSString *label = [spec objectForKey:@"label"];
        // Default label if missing
        if (!label) {
            NSMutableString *l = [NSMutableString string];
            int k;
            for (k = 0; k < [name length]; k++) {
                unichar c = [name characterAtIndex:k];
                if (k == 0) [l appendFormat:@"%C", toupper(c)];
                else if (isupper(c)) [l appendFormat:@" %C", c];
                else [l appendFormat:@"%C", c];
            }
            label = l;
        }
        NSDictionary *field = [NSDictionary dictionaryWithObjectsAndKeys:
            name, @"name", label, @"label",
            [NSNumber numberWithFloat:y], @"y", nil];
        [fields addObject:field];
        y -= 28;
    }
    [config setObject:fields forKey:@"fields"];
    
    // Archive
    @try {
        NSData *data = [NSArchiver archivedDataWithRootObject:config];
        [data writeToFile:outPath atomically:NO];
        printf("Created %s (%lu bytes, %lu fields from nib)\n",
               argv[2], (unsigned long)[data length], (unsigned long)[fields count]);
    } @catch (NSException *e) {
        printf("Error: %s\n", [[e description] UTF8String]);
        [pool release]; return 1;
    }
    [pool release];
    return 0;
}
