# System-wide bashrc — sourced by interactive non-login bash
# (bash is built with sysconfdir=/etc, so this is the system bashrc path).
# Login shells go through /etc/profile, which already sources profile.d/*;
# this file covers the non-login case (e.g. terminals that exec `bash -i`
# rather than `bash -l`).

case $- in *i*) ;; *) return 0 ;; esac

for script in /etc/profile.d/*.sh; do
    [ -r "$script" ] && . "$script"
done
unset script
