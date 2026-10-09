# Rembly OS shell setup (interactive shells). Prompt in the style of Kali: two lines, a box-drawing frame; green in the hacker style, white otherwise.
case $- in *i*) ;; *) return ;; esac
HISTCONTROL=ignoreboth; HISTSIZE=5000; HISTFILESIZE=10000; shopt -s histappend checkwinsize 2>/dev/null
[ -r /usr/share/bash-completion/bash_completion ] && . /usr/share/bash-completion/bash_completion
if [ -x /usr/bin/dircolors ]; then eval "$(dircolors -b)"; alias ls='ls --color=auto' grep='grep --color=auto' diff='diff --color=auto'; fi
alias ll='ls -lah' la='ls -A' ..='cd ..' update='rembly-update' doctor='rembly-doctor' top='htop' df='df -h' free='free -m'
case "$(cat ~/.config/rembly/style 2>/dev/null)" in
  hacker) c='\[\e[1;32m\]'; d='\[\e[0;32m\]'; w='\[\e[1;37m\]' ;;
  *)      c='\[\e[1;37m\]'; d='\[\e[0;37m\]'; w='\[\e[1;37m\]' ;;
esac
r='\[\e[0m\]'
if [ "$(id -u)" = 0 ]; then u=root; sym='#'; else u=$USER; sym='$'; fi
PS1="${d}┌──(${c}${u}${d}@${c}\h${d})-[${w}\w${d}]\n${d}└─${c}${sym}${r} "
case "$TERM" in xterm*|rxvt*|screen*) PS1="\[\e]0;${u}@\h: \w\a\]$PS1" ;; esac
unset c d w r u sym
# banner: once per terminal, only in the hacker style (REMBLY_NOBANNER=1 turns it off)
if [ -z "$REMBLY_NOBANNER" ] && [ "$(cat ~/.config/rembly/style 2>/dev/null)" = hacker ] && [ -r /usr/share/rembly/banner.txt ]; then
  printf '\e[1;32m'; cat /usr/share/rembly/banner.txt; printf '\e[0;32m  kernel %s | %s | type "doctor" if something looks wrong\e[0m\n\n' "$(uname -r)" "$(uname -m)"
fi
export REMBLY_NOBANNER=1
