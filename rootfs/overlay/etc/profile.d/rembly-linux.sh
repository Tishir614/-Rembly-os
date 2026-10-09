# Environment that makes ordinary Linux GUI programs behave on this tablet (touch screen, 140 dpi, no GPU, no user namespaces).
export GDK_BACKEND=x11 QT_QPA_PLATFORM=xcb SDL_VIDEODRIVER=x11 MOZ_ENABLE_WAYLAND=0
export QT_QPA_PLATFORMTHEME=gtk2          # Qt apps follow the GTK dark theme (package qt5-gtk-platformtheme)
export QT_AUTO_SCREEN_SCALE_FACTOR=0 QT_ENABLE_HIGHDPI_SCALING=0   # DPI comes from Xft.dpi, no double scaling
export MOZ_USE_XINPUT2=1                   # Firefox: smooth touch scrolling
export GTK_USE_PORTAL=0 NO_AT_BRIDGE=0
export LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe LP_NUM_THREADS=2   # no GPU: Mesa software rendering, 2 threads max
export _JAVA_OPTIONS="-Dawt.useSystemAAFontSettings=on -Dswing.aatext=true -Dsun.java2d.xrender=true -Xshare:auto -XX:+UseSerialGC"
export JAVA_TOOL_OPTIONS=-Xmx768m        # keep Java apps from eating the tablet's RAM
export ELECTRON_OZONE_PLATFORM_HINT=x11
export PYTHONDONTWRITEBYTECODE=0 PIP_DISABLE_PIP_VERSION_CHECK=1
export MAKEFLAGS="-j2"                      # the A53 has little RAM: don't spawn 4+ compiler jobs
