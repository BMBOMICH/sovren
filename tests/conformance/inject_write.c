/* Linux x86-64 syscall-level fault injection for static/raw-syscall tools. */
#include <sys/ptrace.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/user.h>
#include <unistd.h>
#include <signal.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
int main(int argc,char **argv){
 if(argc<3)return 2;
 pid_t pid=fork();if(pid<0)return 2;
 if(!pid){if(ptrace(PTRACE_TRACEME,0,0,0)<0)_exit(126);raise(SIGSTOP);execv(argv[2],argv+2);_exit(127);}
 int status,entering=1,injected=0,override=0;
 if(waitpid(pid,&status,0)<0)return 2;
 if(ptrace(PTRACE_SETOPTIONS,pid,0,PTRACE_O_TRACESYSGOOD|PTRACE_O_EXITKILL)<0){kill(pid,SIGKILL);waitpid(pid,0,0);return 125;}
 if(ptrace(PTRACE_SYSCALL,pid,0,0)<0)return 125;
 for(;;){
  if(waitpid(pid,&status,0)<0){if(errno==EINTR)continue;return 125;}
  if(WIFEXITED(status))return injected?WEXITSTATUS(status):125;
  if(WIFSIGNALED(status))return 128+WTERMSIG(status);
  if(!WIFSTOPPED(status))continue;
  int sig=WSTOPSIG(status),deliver=0;
  if(sig==(SIGTRAP|0x80)){
   struct user_regs_struct r;
   if(ptrace(PTRACE_GETREGS,pid,0,&r)<0)return 125;
   if(entering&&!injected&&r.orig_rax==1&&r.rdi>2){
    injected=1;
    if(!strcmp(argv[1],"kill")){kill(pid,SIGKILL);waitpid(pid,&status,0);return 137;}
    if(!strcmp(argv[1],"short")){if(r.rdx>7)r.rdx=7;}
    else {override=!strcmp(argv[1],"eintr")?EINTR:EIO;r.orig_rax=(unsigned long)-1;}
    if(ptrace(PTRACE_SETREGS,pid,0,&r)<0)return 125;
   }else if(!entering&&override){r.rax=(unsigned long)-override;override=0;if(ptrace(PTRACE_SETREGS,pid,0,&r)<0)return 125;}
   entering=!entering;
  }else if(sig!=SIGTRAP&&sig!=SIGSTOP)deliver=sig;
  if(ptrace(PTRACE_SYSCALL,pid,0,deliver)<0)return 125;
 }
}
