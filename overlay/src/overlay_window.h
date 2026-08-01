// Fenetre d'overlay : couche transparente posee PAR-DESSUS le jeu.
//
// Aucun code n'est injecte dans CS2 et aucune API du jeu n'est interceptee.
// Il s'agit d'une fenetre Win32 ordinaire, en propriete de ce processus, rendue
// transparente et non cliquable. Le jeu ignore totalement son existence.
#pragma once

#include <windows.h>

#include <memory>

#include "api_client.h"
#include "model.h"

namespace cs2t {

struct OverlayConfig {
    int x = 24;
    int y = 24;
    int width = 460;
    int height = 560;
    int refreshMs = 700;
    std::wstring host = L"127.0.0.1";
    int port = 8642;
    // Opacite globale, 0-255. Combinee a l'alpha du fond, elle doit rester
    // haute : la lisibilite du panneau prime sur la vue du jeu derriere lui.
    BYTE opacity = 250;
};

class OverlayWindow {
public:
    explicit OverlayWindow(OverlayConfig config);
    ~OverlayWindow();

    OverlayWindow(const OverlayWindow&) = delete;
    OverlayWindow& operator=(const OverlayWindow&) = delete;

    bool Create(HINSTANCE instance);
    int RunMessageLoop();

private:
    static LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp);
    LRESULT Handle(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp);

    void Tick();
    void Redraw();
    void ToggleVisible();
    void CycleCorner();

    OverlayConfig config_;
    ApiClient client_;
    OverlayState state_;
    HWND hwnd_ = nullptr;
    ULONG_PTR gdiplusToken_ = 0;
    bool visible_ = true;
    int corner_ = 0;
};

}  // namespace cs2t
