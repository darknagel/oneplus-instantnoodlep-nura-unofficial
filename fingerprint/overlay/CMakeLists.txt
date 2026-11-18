cmake_minimum_required(VERSION 3.16)
project(goodix-fp-overlay LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_AUTOMOC ON)
find_package(Qt6 REQUIRED COMPONENTS Gui DBus WaylandClient)
find_package(Qt6 COMPONENTS WaylandClientPrivate)
find_package(LayerShellQt REQUIRED)
find_package(PlasmaWaylandProtocols REQUIRED)

add_executable(goodix-fp-overlay goodix-fp-overlay.cpp)
set(LOCKSCREEN_XML ${PLASMA_WAYLAND_PROTOCOLS_DIR}/kde-lockscreen-overlay-v1.xml)
# needs C enabled: Qt also generates the wayland-scanner interface code (.c)
qt6_generate_wayland_protocol_client_sources(goodix-fp-overlay FILES ${LOCKSCREEN_XML})
target_link_libraries(goodix-fp-overlay Qt6::Gui Qt6::DBus Qt6::WaylandClient
    Qt6::WaylandClientPrivate LayerShellQt::Interface)

install(TARGETS goodix-fp-overlay DESTINATION bin)
# KWin reads X-KDE-Wayland-Interfaces from the application entry whose Exec
# matches the executable; the autostart entry only starts it
install(FILES goodix-fp-overlay.desktop DESTINATION share/applications)
install(FILES goodix-fp-overlay.desktop DESTINATION /etc/xdg/autostart)
# restart.conf (restart after a KWin crash) belongs in
# lib/systemd/user/app-goodix\x2dfp\x2doverlay@autostart.service.d/; cmake turns
# those backslashes into path separators, so the package installs it itself
