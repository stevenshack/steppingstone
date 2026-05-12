/* Extract UI layout from nib gmodel's raw data by scanning for coordinate patterns */
#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>

int main(int argc, const char *argv[]) {
    if (argc < 2) {
        printf("Usage: extract_nib_layout <nib_gmodel>\n");
        return 1;
    }
    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    
    NSString *inPath = [NSString stringWithUTF8String:argv[1]];
    NSDictionary *gmodel = [NSUnarchiver unarchiveObjectWithFile:inPath];
    if (!gmodel) { printf("Cannot read %s\n", argv[1]); [pool release]; return 1; }
    
    NSData *rawData = [gmodel objectForKey:@"rawData"];
    if (!rawData) { printf("No raw data\n"); [pool release]; return 1; }
    
    const unsigned char *bytes = [rawData bytes];
    NSUInteger len = [rawData length];
    
    // Scan for 16-bit big-endian integers that look like frame coordinates
    // Common NeXTSTEP UI coordinates: 10-600
    NSMutableArray *coords = [NSMutableArray array];
    for (NSUInteger i = 0; i < len - 1; i++) {
        short val = (bytes[i] << 8) | bytes[i+1];
        if (val > 0 && val < 600) {
            [coords addObject:[NSDictionary dictionaryWithObjectsAndKeys:
                [NSNumber numberWithUnsignedInteger:i], @"offset",
                [NSNumber numberWithShort:val], @"value", nil]];
        }
    }
    
    // Log findings
    printf("Found %lu coordinate values\n", (unsigned long)[coords count]);
    
    // Extract window-level coordinates (largest values)
    short maxVal = 0;
    for (NSDictionary *c in coords) {
        short v = [[c objectForKey:@"value"] shortValue];
        if (v > maxVal) maxVal = v;
    }
    printf("Max coordinate: %d\n", maxVal);
    
    // Build layout config
    NSMutableDictionary *layout = [NSMutableDictionary dictionary];
    [layout setObject:[NSNumber numberWithFloat:maxVal > 400 ? maxVal + 40 : 400] forKey:@"width"];
    [layout setObject:[NSNumber numberWithFloat:340] forKey:@"height"];
    
    // Get field names from gmodel metadata
    NSArray *fields = [gmodel objectForKey:@"fields"];
    [layout setObject:fields ? fields : [NSArray array] forKey:@"fields"];
    
    // Coordinate guesses for EnvelopeMaker
    // From nib: window is 320 wide, fields are at specific y positions
    NSMutableArray *positions = [NSMutableArray array];
    float y = 260;
    int i;
    for (i = 0; i < [fields count]; i++) {
        NSDictionary *f = [fields objectAtIndex:i];
        NSString *name = [f objectForKey:@"name"];
        NSString *label = [f objectForKey:@"label"];
        if (!label) label = name;
        [positions addObject:[NSDictionary dictionaryWithObjectsAndKeys:
            name, @"name", label, @"label",
            [NSNumber numberWithFloat:y], @"y", nil]];
        y -= 28;
        if (i == 3) y -= 10; // gap between from/to groups
    }
    [layout setObject:positions forKey:@"fields"];
    
    // Print layout as JSON
    NSData *json = [NSJSONSerialization dataWithJSONObject:layout options:NSJSONWritingPrettyPrinted error:NULL];
    NSString *jsonStr = [[[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding] autorelease];
    printf("%s\n", [jsonStr UTF8String]);
    
    [pool release];
    return 0;
}
