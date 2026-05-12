/* Extract NXRect frames from NeXTSTEP nib by scanning float markers */
#import <Foundation/Foundation.h>

int main(int argc, const char *argv[]) {
    if (argc < 2) { printf("Usage: extract_nib_frames <nib>\n"); return 1; }
    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    
    NSString *path = [NSString stringWithUTF8String:argv[1]];
    NSData *data = [NSData dataWithContentsOfFile:path];
    const unsigned char *bytes = [data bytes];
    NSUInteger len = [data length];
    
    // Find all strings in the nib to label frames
    NSMutableArray *strings = [NSMutableArray array];
    int i;
    for (i = 0; i < (int)len - 3; i++) {
        if (bytes[i] >= 0x20 && bytes[i] <= 0x7e) {
            int start = i;
            while (i < (int)len && bytes[i] >= 0x20 && bytes[i] <= 0x7e) i++;
            if (i - start >= 3) {
                NSString *s = [[[NSString alloc] initWithBytes:bytes+start length:i-start encoding:NSASCIIStringEncoding] autorelease];
                if (![s hasPrefix:@"typedstream"] && [s length] < 100)
                    [strings addObject:s];
            }
        }
    }
    
    // Scan for float patterns: 97 05 followed by 4 bytes BE float
    NSMutableArray *floats = [NSMutableArray array];
    for (i = 0; i < (int)len - 5; i++) {
        if (bytes[i] == 0x97 && bytes[i+1] == 0x05) {
            float f;
            memcpy(&f, bytes + i + 2, 4);
            // Swap endianness (big-endian in file, running on LE)
            f = ntohl(*(unsigned int*)&f);
            *(unsigned int*)&f = ntohl(*(unsigned int*)&f);
            // Actually just read as big-endian
            unsigned int raw = (bytes[i+2] << 24) | (bytes[i+3] << 16) | (bytes[i+4] << 8) | bytes[i+5];
            memcpy(&f, &raw, 4);
            [floats addObject:[NSNumber numberWithFloat:f]];
        }
    }
    
    printf("{\n");
    printf("  \"strings\": %s,\n", [[[NSString stringWithFormat:@"%@", strings] description] UTF8String]);
    printf("  \"floats\": [");
    int j;
    for (j = 0; j < [floats count]; j++) {
        if (j > 0) printf(",");
        printf("%.1f", [[floats objectAtIndex:j] floatValue]);
    }
    printf("]\n}\n");
    
    [pool release];
    return 0;
}
