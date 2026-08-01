cmake_minimum_required(VERSION 3.20)

project(cs2tracker_overlay VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT WIN32)
    message(FATAL_ERROR "L'overlay repose sur l'API Win32 et ne cible que Windows.")
endif()

add_executable(CS2TrackerOverlay WIN32
    src/main.cpp
    src/overlay_window.cpp
    src/api_client.cpp
    src/json.cpp
)

target_include_directories(CS2TrackerOverlay PRIVATE src)

target_compile_definitions(CS2TrackerOverlay PRIVATE
    UNICODE
    _UNICODE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
)

target_link_libraries(CS2TrackerOverlay PRIVATE
    winhttp
    gdiplus
    user32
    gdi32
    shell32
)

if(MSVC)
    target_compile_options(CS2TrackerOverlay PRIVATE /W4 /permissive- /utf-8)
    # Lien statique de la runtime : l'executable fonctionne sans redistribuable.
    set_property(TARGET CS2TrackerOverlay PROPERTY
                 MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
endif()

install(TARGETS CS2TrackerOverlay RUNTIME DESTINATION .)
