/* Simple ObjC program to decode and dump nib contents via NSUnarchiver. */
#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>

@interface NibDumper : NSObject
+ (void)dumpObject:(id)obj indent:(int)indent;
+ (void)dumpNib:(NSString *)path;
@end

@implementation NibDumper

+ (void)dumpObject:(id)obj indent:(int)indent
{
  NSString *pad = [@"" stringByPaddingToLength:indent*2 withString:@" " startingAtIndex:0];
  if (obj == nil) {
    printf("%snil\n", [pad UTF8String]);
    return;
  }

  if ([obj isKindOfClass:[NSString class]]) {
    printf("%sNSString: \"%s\"\n", [pad UTF8String], [(NSString *)obj UTF8String]);
  } else if ([obj isKindOfClass:[NSNumber class]]) {
    printf("%sNSNumber: %@\n", [pad UTF8String], obj);
  } else if ([obj isKindOfClass:[NSData class]]) {
    printf("%sNSData: %lu bytes\n", [pad UTF8String], (unsigned long)[(NSData *)obj length]);
  } else if ([obj isKindOfClass:[NSArray class]]) {
    printf("%sNSArray (%lu items):\n", [pad UTF8String], (unsigned long)[(NSArray *)obj count]);
    for (id item in (NSArray *)obj) {
      [self dumpObject:item indent:indent+1];
    }
  } else if ([obj isKindOfClass:[NSDictionary class]]) {
    printf("%sNSDictionary (%lu keys):\n", [pad UTF8String], (unsigned long)[(NSDictionary *)obj count]);
    for (id key in (NSDictionary *)obj) {
      printf("%s  key: \"%s\" ->\n", [pad UTF8String], [[key description] UTF8String]);
      [self dumpObject:[(NSDictionary *)obj objectForKey:key] indent:indent+2];
    }
  } else if ([obj isKindOfClass:[NSValue class]]) {
    printf("%sNSValue: %s\n", [pad UTF8String], [[obj description] UTF8String]);
  } else {
    printf("%s%s: %s\n", [pad UTF8String], 
           [[obj className] UTF8String],
           [[obj description] UTF8String]);
    // Try to dump ivars via KVC for known classes
    @try {
      if ([obj respondsToSelector:@selector(frame)]) {
        NSRect f = [obj frame];
        printf("%s  frame: {{%0.1f, %0.1f}, {%0.1f, %0.1f}}\n", [pad UTF8String],
               f.origin.x, f.origin.y, f.size.width, f.size.height);
      }
    } @catch(...) {}
  }
}

+ (void)dumpNib:(NSString *)path
{
  NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];

  printf("Loading nib: %s\n\n", [path UTF8String]);

  NSData *data = [NSData dataWithContentsOfFile:path];
  if (!data) {
    printf("ERROR: Cannot read file\n");
    [pool release];
    return;
  }

  @try {
    // Try NSUnarchiver (old-style)
    NSUnarchiver *unarchiver = [[NSUnarchiver alloc] initForReadingWithData:data];
    if (unarchiver) {
      printf("NSUnarchiver version: %d\n", [unarchiver versionForClassName:@"NSObject"]);
      
      id root = [unarchiver decodeObject];
      printf("Root object:\n");
      [self dumpObject:root indent:1];
      
      // Decode more objects if available
      @try {
        while (1) {
          id obj = [unarchiver decodeObject];
          if (obj == nil) break;
          printf("\nAdditional object:\n");
          [self dumpObject:obj indent:1];
        }
      } @catch(...) {}
      
      [unarchiver finishDecoding];
      [unarchiver release];
    } else {
      printf("NSUnarchiver failed\n");
    }
  } @catch(NSException *e) {
    printf("ERROR: %s - %s\n", [[e name] UTF8String], [[e reason] UTF8String]);
  }

  printf("\nDone.\n");
  [pool release];
}

@end

int main(int argc, char **argv)
{
  if (argc < 2) {
    printf("Usage: nib_dump <nibfile>\n");
    return 1;
  }
  NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
  [NSApplication sharedApplication]; // ensure AppKit is loaded
  [NibDumper dumpNib:[NSString stringWithUTF8String:argv[1]]];
  [pool release];
  return 0;
}
