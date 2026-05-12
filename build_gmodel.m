/* Build-time tool: generates .gmodel from class layout + nib-derived frame positions */
#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>

// Nib-derived field positions for EnvelopeMaker (hardcoded fallback until parser is complete)
static const char *fieldNames[] = {"editWindow","envelopeView","infoPanel",
    "fromField1","fromField2","fromField3","fromField4",
    "toField1","toField2","toField3","toField4","toField5"};
// Y positions for each field (nib-derived), 0 = skip showing
static const float fieldY[] = {0,0,0, 260,232,204,176, 148,120,92,64,36};

int main(int argc, const char *argv[]) {
    if (argc < 3) {
        printf("Usage: build_gmodel <class_info.json> <output.gmodel>\n");
        return 1;
    }
    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    [NSApplication sharedApplication];
    
    NSMutableDictionary *config = [NSMutableDictionary dictionary];
    [config setObject:[NSNumber numberWithFloat:400.0] forKey:@"windowWidth"];
    [config setObject:[NSNumber numberWithFloat:340.0] forKey:@"windowHeight"];
    [config setObject:@"Envelope Maker" forKey:@"windowTitle"];
    
    NSMutableArray *fieldSpecs = [NSMutableArray array];
    int i;
    for (i = 0; i < 12; i++) {
        if (fieldY[i] == 0) continue; // skip non-field outlets
        NSString *name = [NSString stringWithUTF8String:fieldNames[i]];
        // Build label: "fromField1" -> "From Field 1"
        NSMutableString *label = [NSMutableString string];
        int k, first = 1;
        for (k = 0; k < [name length]; k++) {
            unichar c = [name characterAtIndex:k];
            if (k == 0) { [label appendFormat:@"%C", toupper(c)]; }
            else if (isupper(c)) { [label appendFormat:@" %C", c]; }
            else { [label appendFormat:@"%C", c]; }
        }
        NSMutableDictionary *field = [NSMutableDictionary dictionary];
        [field setObject:name forKey:@"name"];
        [field setObject:label forKey:@"label"];
        [field setObject:[NSNumber numberWithFloat:fieldY[i]] forKey:@"y"];
        [fieldSpecs addObject:field];
    }
    [config setObject:fieldSpecs forKey:@"fields"];
    
    @try {
        NSData *data = [NSArchiver archivedDataWithRootObject:config];
        if (argc > 3) {
            // If nib config JSON provided, read it for frame positions
            NSString *cfgPath = [NSString stringWithUTF8String:argv[3]];
            NSData *cfgData = [NSData dataWithContentsOfFile:cfgPath];
            if (cfgData) {
                NSDictionary *nibCfg = [NSJSONSerialization JSONObjectWithData:cfgData options:0 error:NULL];
                if (nibCfg) {
                    // Merge nib config overrides here when parser is complete
                }
            }
        }
        [data writeToFile:[NSString stringWithUTF8String:argv[2]] atomically:NO];
        printf("Created %s (%lu bytes, %d fields)\n", argv[2],
               (unsigned long)[data length], (int)[fieldSpecs count]);
    } @catch (NSException *e) {
        printf("Error: %s\n", [[e description] UTF8String]);
        [pool release]; return 1;
    }
    [pool release];
    return 0;
}
