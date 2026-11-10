/* Crash catcher: run a child, on SIGSEGV/SIGILL dump regs + maps excerpt. */
#include <sys/ptrace.h>
#include <sys/user.h>
#include <sys/wait.h>
#include <unistd.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
int main(int argc, char** argv){
    pid_t pid = fork();
    if(pid == 0){
        ptrace(PTRACE_TRACEME, 0, 0, 0);
        execv(argv[1], &argv[1]);
        _exit(127);
    }
    int st;
    waitpid(pid, &st, 0);
    ptrace(PTRACE_CONT, pid, 0, 0);
    for(;;){
        if(waitpid(pid, &st, 0) < 0) break;
        if(WIFEXITED(st)){ fprintf(stderr,"exit %d\n", WEXITSTATUS(st)); break; }
        if(WIFSIGNALED(st)){ fprintf(stderr,"killed %d\n", WTERMSIG(st)); break; }
        if(WIFSTOPPED(st)){
            int sig = WSTOPSIG(st);
            if(sig == SIGSEGV || sig == SIGILL || sig == SIGBUS || sig == SIGTRAP){
                struct user_regs_struct r;
                ptrace(PTRACE_GETREGS, pid, 0, &r);
                fprintf(stderr,"FAULT sig=%d rip=%llx rsp=%llx rax=%llx rdi=%llx rsi=%llx rdx=%llx rcx=%llx r8=%llx r9=%llx r10=%llx r11=%llx\n",
                    sig,(unsigned long long)r.rip,(unsigned long long)r.rsp,(unsigned long long)r.rax,
                    (unsigned long long)r.rdi,(unsigned long long)r.rsi,(unsigned long long)r.rdx,
                    (unsigned long long)r.rcx,(unsigned long long)r.r8,(unsigned long long)r.r9,
                    (unsigned long long)r.r10,(unsigned long long)r.r11);
                char pth[64]; snprintf(pth,sizeof pth,"/proc/%d/maps",pid);
                FILE* f=fopen(pth,"r"); char buf[512];
                while(f && fgets(buf,sizeof buf,f)) fputs(buf,stderr);
                if(f) fclose(f);
                ptrace(PTRACE_KILL,pid,0,0);
                kill(pid,SIGKILL);
                break;
            }
            ptrace(PTRACE_CONT, pid, 0, sig == SIGTRAP ? 0 : sig);
        }
    }
    return 0;
}
