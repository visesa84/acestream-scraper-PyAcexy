// LD_PRELOAD library to remap bind ports dynamically based on env vars
// Usage:
//   ACE_BIND_REMAP=1 ACE_BIND_REMAP_FROM=6878 ACE_BIND_REMAP_TO=6879 \
//     LD_PRELOAD=/path/to/bind_remap.so ./start-engine ...

#define _GNU_SOURCE
#include <dlfcn.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

typedef int (*orig_bind_f_type)(int, const struct sockaddr *, socklen_t);

static int parse_env_port(const char *envname, unsigned short fallback) {
    const char *val = getenv(envname);
    if (!val) return fallback;
    char *endptr = NULL;
    long v = strtol(val, &endptr, 10);
    if (endptr == val || v <= 0 || v > 65535) return fallback;
    return (unsigned short)v;
}

int bind(int sockfd, const struct sockaddr *addr, socklen_t addrlen) {
    static orig_bind_f_type orig_bind = NULL;
    if (!orig_bind) {
        orig_bind = (orig_bind_f_type)dlsym(RTLD_NEXT, "bind");
        if (!orig_bind) {
            fprintf(stderr, "[bind_remap] dlsym(bind) failed\n");
            return -1;
        }
    }

    const char *env = getenv("ACE_BIND_REMAP");
    if (env && strcmp(env, "1") == 0 && addr) {
        unsigned short from_port = parse_env_port("ACE_BIND_REMAP_FROM", 8621);
        unsigned short to_port = parse_env_port("ACE_BIND_REMAP_TO", 8622);
        unsigned short from_p2p = parse_env_port("ACE_BIND_REMAP_FROM_P2P", 8621);
        unsigned short to_p2p = parse_env_port("ACE_BIND_REMAP_TO_P2P", 8622);

        if (addr->sa_family == AF_INET && addrlen >= sizeof(struct sockaddr_in)) {
            const struct sockaddr_in *in = (const struct sockaddr_in *)addr;
            unsigned short port = ntohs(in->sin_port);
            if (port == from_port) {
                struct sockaddr_in mod;
                memcpy(&mod, in, sizeof(mod));
                mod.sin_port = htons(to_port);
                return orig_bind(sockfd, (const struct sockaddr *)&mod, addrlen);
            }
            if (port == from_p2p) {
                struct sockaddr_in mod;
                memcpy(&mod, in, sizeof(mod));
                mod.sin_port = htons(to_p2p);
                return orig_bind(sockfd, (const struct sockaddr *)&mod, addrlen);
            }
        }
#ifdef AF_INET6
        if (addr->sa_family == AF_INET6 && addrlen >= sizeof(struct sockaddr_in6)) {
            const struct sockaddr_in6 *in6 = (const struct sockaddr_in6 *)addr;
            unsigned short port = ntohs(in6->sin6_port);
            if (port == from_port) {
                struct sockaddr_in6 mod6;
                memcpy(&mod6, in6, sizeof(mod6));
                mod6.sin6_port = htons(to_port);
                return orig_bind(sockfd, (const struct sockaddr *)&mod6, addrlen);
            }
            if (port == from_p2p) {
                struct sockaddr_in6 mod6;
                memcpy(&mod6, in6, sizeof(mod6));
                mod6.sin6_port = htons(to_p2p);
                return orig_bind(sockfd, (const struct sockaddr *)&mod6, addrlen);
            }
        }
#endif
    }

    return orig_bind(sockfd, addr, addrlen);
}
