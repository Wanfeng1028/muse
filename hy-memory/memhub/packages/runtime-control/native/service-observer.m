#import <Foundation/Foundation.h>
#import <ServiceManagement/ServiceManagement.h>
#include <pwd.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

int main(int argc, const char *argv[]) {
  if (argc != 2 || strcmp(argv[1], "--status") != 0) {
    fputs("Usage: service-observer --status\n", stderr);
    return 2;
  }
  @autoreleasepool {
    NSString *eligibility = @"unknown";
    @try {
      uid_t uid = getuid();
      struct passwd *account = getpwuid(uid);
      NSString *accountHome = account && account->pw_dir
          ? [NSString stringWithUTF8String:account->pw_dir] : nil;
      NSString *home = NSHomeDirectory();
      // Do not query another home through an inherited environment or elevated UID.
      if (uid > 0 && geteuid() == uid && accountHome &&
          [home isEqualToString:accountHome] && [home hasPrefix:@"/Users/"]) {
        if (@available(macOS 13.0, *)) {
          NSString *plist = [home stringByAppendingPathComponent:
              @"Library/LaunchAgents/com.tencent.onememory.runtime.plist"];
          SMAppServiceStatus status = [SMAppService statusForLegacyURL:
              [NSURL fileURLWithPath:plist isDirectory:NO]];
          switch (status) {
            case SMAppServiceStatusEnabled: eligibility = @"registered"; break;
            case SMAppServiceStatusRequiresApproval: eligibility = @"requires_approval"; break;
            case SMAppServiceStatusNotRegistered: eligibility = @"not_registered"; break;
            case SMAppServiceStatusNotFound: eligibility = @"unknown"; break;
            default: eligibility = @"unknown"; break;
          }
        }
      }
    } @catch (__unused NSException *exception) {
      eligibility = @"unknown";
    }
    // Only fixed literals reach stdout; no system exception or path is disclosed.
    printf("{\"schemaVersion\":1,\"systemEligibility\":\"%s\"}\n",
        [eligibility UTF8String]);
  }
  return 0;
}
