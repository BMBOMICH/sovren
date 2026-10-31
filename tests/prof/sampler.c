#include <sys/ptrace.h>
#include <sys/user.h>
#include <sys/wait.h>
#include <unistd.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
static void dump_maps(pid_t pid){
    char path[64]; snprintf(path, sizeof path, "/proc/%d/maps", pid);
    FILE* f = fopen(path, "r"); if(!f) return;
    FILE* o = fopen("/tmp/maps.txt", "w"); if(!o){ fclose(f); return; }
    char buf[4096]; size_t n;
    while((n = fread(buf, 1, sizeof buf, f)) > 0) fwrite(buf, 1, n, o);
    fclose(f); fclose(o);
}
int main(int argc, char** argv){
    pid_t pid = fork();
    if(pid == 0){
        int dn = open("/dev/null", O_WRONLY);
        dup2(dn, 1); dup2(dn, 2);
        ptrace(PTRACE_TRACEME, 0, 0, 0);
        execv(argv[1], &argv[1]);
        _exit(127);
    }
    int st;
    waitpid(pid, &st, 0);
    ptrace(PTRACE_CONT, pid, 0, 0);
    int dumped = 0;
    for(int i = 0; i < 20000; i++){
        usleep(120);
        if(kill(pid, SIGSTOP) != 0) break;
        if(waitpid(pid, &st, 0) < 0) break;
        if(WIFEXITED(st) || WIFSIGNALED(st)) break;
        if(!dumped){ dump_maps(pid); dumped = 1; }
        struct user_regs_struct r;
        if(ptrace(PTRACE_GETREGS, pid, 0, &r) == 0)
            printf("%llx\n", (unsigned long long)r.rip);
        ptrace(PTRACE_CONT, pid, 0, 0);
    }
    kill(pid, SIGKILL);
    return 0;
}
