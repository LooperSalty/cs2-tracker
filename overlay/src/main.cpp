// CS2 Tracker Overlay — affichage par-dessus le jeu.
//
// Ce programme ne touche jamais au processus de Counter-Strike 2 : ni lecture
// memoire, ni injection, ni interception d'appels graphiques. Il cree sa propre
// fenetre Win32 transparente et non cliquable, et se contente d'interroger
// l'API locale de CS2 Tracker en HTTP.
//
// Contrainte a connaitre : une fenetre superposee n'apparait pas au-dessus d'un
// jeu en plein ecran exclusif. Regle CS2 sur « Plein ecran fenetre ».

#include <windows.h>
#include <shellapi.h>

#include <string>

#include "overlay_window.h"

namespace {

// Une seule instance : deux overlays superposes seraient illisibles.
constexpr wchar_t kMutexName[] = L"Local\\CS2TrackerOverlaySingleton";

int ReadIntArgument(int argc, wchar_t** argv, const wchar_t* name, int fallback) {
    for (int i = 1; i + 1 < argc; ++i) {
        if (_wcsicmp(argv[i], name) == 0) {
            const int value = _wtoi(argv[i + 1]);
            if (value > 0) return value;
        }
    }
    return fallback;
}

}  // namespace

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, PWSTR, int) {
    HANDLE singleton = CreateMutexW(nullptr, TRUE, kMutexName);
    if (singleton != nullptr && GetLastError() == ERROR_ALREADY_EXISTS) {
        MessageBoxW(nullptr,
                    L"L'overlay est deja lance.\n\n"
                    L"F8 pour l'afficher ou le masquer, "
                    L"Ctrl+Maj+F8 pour le fermer.",
                    L"CS2 Tracker Overlay", MB_OK | MB_ICONINFORMATION);
        return 0;
    }

    int argc = 0;
    wchar_t** argv = CommandLineToArgvW(GetCommandLineW(), &argc);

    cs2t::OverlayConfig config;
    config.port = ReadIntArgument(argc, argv, L"--port", config.port);
    config.width = ReadIntArgument(argc, argv, L"--width", config.width);
    config.height = ReadIntArgument(argc, argv, L"--height", config.height);
    config.refreshMs = ReadIntArgument(argc, argv, L"--refresh", config.refreshMs);
    if (argv != nullptr) LocalFree(argv);

    // Un overlay mal positionne sur ecran haute densite serait inutilisable.
    SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);

    cs2t::OverlayWindow overlay(config);
    if (!overlay.Create(instance)) {
        MessageBoxW(nullptr, L"Creation de la fenetre d'overlay impossible.",
                    L"CS2 Tracker Overlay", MB_OK | MB_ICONERROR);
        return 1;
    }

    const int code = overlay.RunMessageLoop();
    if (singleton != nullptr) CloseHandle(singleton);
    return code;
}
