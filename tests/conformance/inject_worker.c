/* Trace only the parent. Exercise real pipe/fork/read/wait failure routes. */
#include <sys/ptrace.h>
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
 const char *mode=argv[1];pid_t pid=fork();if(pid<0)return 2;
 if(!pid){ptrace(PTRACE_TRACEME,0,0,0);raise(SIGSTOP);execv(argv[2],argv+2);_exit(127);}
 int status,entry=1,hit=0,over=0,forks=0,pipes=0;long first_child=-1;
 if(waitpid(pid,&status,0)<0)return 125;
 if(ptrace(PTRACE_SETOPTIONS,pid,0,PTRACE_O_TRACESYSGOOD|PTRACE_O_EXITKILL)<0)return 125;
 ptrace(PTRACE_SYSCALL,pid,0,0);
 for(;;){
  if(waitpid(pid,&status,0)<0){if(errno==EINTR)continue;return 125;}
  if(WIFEXITED(status)){fprintf(stderr,"INJECTION hit=%d forks=%d pipes=%d\n",hit,forks,pipes);return hit?WEXITSTATUS(status):125;}
  if(WIFSIGNALED(status))return 128+WTERMSIG(status);
  if(!WIFSTOPPED(status))continue;
  int sig=WSTOPSIG(status),deliver=0;
  if(sig==(SIGTRAP|0x80)){
   struct user_regs_struct r;if(ptrace(PTRACE_GETREGS,pid,0,&r)<0)return 125;
   if(entry){
    if(r.orig_rax==57)forks++;
    if(r.orig_rax==22)pipes++;
    if(!hit){
     if(!strcmp(mode,"fork-second")&&r.orig_rax==57&&forks==2)over=EAGAIN;
     if(!strcmp(mode,"pipe-second")&&r.orig_rax==22&&pipes==2)over=EMFILE;
     if(!strcmp(mode,"read-eintr")&&r.orig_rax==0&&r.rdi>2&&first_child>0)over=EINTR;
     if(!strcmp(mode,"wait-eintr")&&r.orig_rax==61)over=EINTR;
     if(over){hit=1;r.orig_rax=(unsigned long)-1;if(ptrace(PTRACE_SETREGS,pid,0,&r)<0)return 125;}
    }
   }else{
    if(over){r.rax=(unsigned long)-over;over=0;if(ptrace(PTRACE_SETREGS,pid,0,&r)<0)return 125;}
    else if(r.orig_rax==57&&(long)r.rax>0){
     if(first_child<0)first_child=r.rax;
     if(!hit&&!strcmp(mode,"worker-kill")){if(kill((pid_t)r.rax,SIGKILL)<0)return 125;hit=1;}
    }
    if(!hit&&!strcmp(mode,"worker-partial")&&r.orig_rax==0&&r.rdi>2&&(long)r.rax>0&&first_child>0){if(kill((pid_t)first_child,SIGKILL)<0)return 125;hit=1;}
   }
   entry=!entry;
  }else if(sig!=SIGTRAP&&sig!=SIGSTOP)deliver=sig;
  if(ptrace(PTRACE_SYSCALL,pid,0,deliver)<0)return 125;
 }
}
