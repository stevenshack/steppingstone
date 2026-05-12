/* nib2gmodel: stores raw nib data + extracted config in a gmodel for round-trip */
#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>

int main(int argc, const char *argv[]) {
    if (argc < 3) {
        printf("Usage: nib2gmodel <input.nib> <output.gmodel>\n");
        return 1;
    }
    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    [NSApplication sharedApplication];
    
    NSString *inPath = [NSString stringWithUTF8String:argv[1]];
    NSString *outPath = [NSString stringWithUTF8String:argv[2]];
    /* NSString *nibName = [[inPath lastPathComponent] stringByDeletingPathExtension]; */
    
    // Read entire nib as raw data
    NSData *rawData = [NSData dataWithContentsOfFile:inPath];
    if (!rawData) { printf("Cannot read %s\n", argv[1]); [pool release]; return 1; }
    
    // Build gmodel: contains raw data + extracted metadata
    NSMutableDictionary *gmodel = [NSMutableDictionary dictionary];
    [gmodel setObject:rawData forKey:@"rawData"];
    
    // Extract strings from nib for metadata
    const unsigned char *bytes = [rawData bytes];
    NSInteger len = [rawData length];
    NSMutableArray *strings = [NSMutableArray array];
    for (NSInteger i = 0; i < len - 3; i++) {
        if (bytes[i] >= 0x41 && bytes[i] <= 0x7a) {
            NSInteger start = i;
            while (i < len && bytes[i] >= 0x20 && bytes[i] <= 0x7e) i++;
            NSString *s = [[[NSString alloc] initWithBytes:bytes+start length:i-start encoding:NSASCIIStringEncoding] autorelease];
            if ([s length] >= 3) [strings addObject:s];
        }
    }
    [gmodel setObject:strings forKey:@"strings"];
    
    // Extract outlet field names
    NSMutableArray *fields = [NSMutableArray array];
    for (NSString *s in strings) {
        if ([s hasPrefix:@"fromField"] || [s hasPrefix:@"toField"]) {
            NSMutableString *label = [NSMutableString string];
            for (int i = 0; i < [s length]; i++) {
                unichar c = [s characterAtIndex:i];
                if (i == 0) [label appendFormat:@"%C", toupper(c)];
                else if (isupper(c)) [label appendFormat:@" %C", c];
                else [label appendFormat:@"%C", c];
            }
            BOOL found = NO;
            for (NSDictionary *f in fields)
                if ([[f objectForKey:@"name"] isEqual:s]) found = YES;
            if (!found)
                [fields addObject:[NSDictionary dictionaryWithObjectsAndKeys:s,@"name",label,@"label",nil]];
        }
    }
    [gmodel setObject:fields forKey:@"fields"];
    
    // Archive
    @try {
        NSData *data = [NSArchiver archivedDataWithRootObject:gmodel];
        [data writeToFile:outPath atomically:NO];
        printf("Created %s (%lu bytes raw + %lu metadata = %lu total)\n",
               argv[2], (unsigned long)[rawData length], (unsigned long)[data length] - [rawData length],
               (unsigned long)[data length]);
    } @catch (NSException *e) {
        printf("Error: %s\n", [[e description] UTF8String]);
        [pool release]; return 1;
    }
    [pool release];
    return 0;
}
