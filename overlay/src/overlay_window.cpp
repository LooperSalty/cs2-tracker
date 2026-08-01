#include "overlay_window.h"

#include <objidl.h>
#include <gdiplus.h>

#include <string>
#include <vector>

#pragma comment(lib, "gdiplus.lib")
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "gdi32.lib")

namespace cs2t {
namespace {

using namespace Gdiplus;

constexpr wchar_t kClassName[] = L"CS2TrackerOverlayWindow";
constexpr UINT_PTR kRefreshTimer = 1;
constexpr int kHotkeyToggle = 1;
constexpr int kHotkeyCorner = 2;
constexpr int kHotkeyQuit = 3;

// Palette : reprend celle de l'interface web pour que les deux se repondent.
// Le fond est presque opaque : un panneau trop translucide laisse remonter les
// couleurs vives du jeu et rend le texte illisible au pire moment.
const Color kBackground(243, 11, 14, 19);
const Color kBorder(255, 43, 53, 66);
const Color kBone(255, 232, 237, 242);
const Color kAsh(255, 125, 139, 156);
const Color kDust(255, 86, 97, 111);
const Color kFlash(255, 255, 106, 61);
const Color kCt(255, 106, 166, 221);
const Color kT(255, 217, 164, 65);
const Color kClean(255, 76, 195, 138);
const Color kModerate(255, 217, 164, 65);
const Color kHigh(255, 255, 106, 61);
const Color kCritical(255, 255, 61, 61);

Color ColorForVerdict(Verdict verdict) {
    switch (verdict) {
        case Verdict::Clean: return kClean;
        case Verdict::Low: return kCt;
        case Verdict::Moderate: return kModerate;
        case Verdict::High: return kHigh;
        case Verdict::Critical: return kCritical;
        default: return kDust;
    }
}

std::wstring Format(const wchar_t* pattern, ...) {
    wchar_t buffer[512];
    va_list args;
    va_start(args, pattern);
    _vsnwprintf_s(buffer, _TRUNCATE, pattern, args);
    va_end(args);
    return buffer;
}

void DrawText(Graphics& g, const std::wstring& text, const Font& font,
              const Color& color, REAL x, REAL y,
              StringAlignment align = StringAlignmentNear) {
    SolidBrush brush(color);
    StringFormat format;
    format.SetAlignment(align);
    format.SetLineAlignment(StringAlignmentNear);
    format.SetFormatFlags(StringFormatFlagsNoWrap);
    g.DrawString(text.c_str(), -1, &font, PointF(x, y), &format, &brush);
}

}  // namespace

OverlayWindow::OverlayWindow(OverlayConfig config)
    : config_(std::move(config)), client_(config_.host, config_.port) {
    GdiplusStartupInput input;
    GdiplusStartup(&gdiplusToken_, &input, nullptr);
}

OverlayWindow::~OverlayWindow() {
    if (hwnd_ != nullptr) {
        UnregisterHotKey(hwnd_, kHotkeyToggle);
        UnregisterHotKey(hwnd_, kHotkeyCorner);
        UnregisterHotKey(hwnd_, kHotkeyQuit);
    }
    if (gdiplusToken_ != 0) GdiplusShutdown(gdiplusToken_);
}

bool OverlayWindow::Create(HINSTANCE instance) {
    WNDCLASSEXW wc = {};
    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc = &OverlayWindow::WndProc;
    wc.hInstance = instance;
    wc.lpszClassName = kClassName;
    wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
    if (RegisterClassExW(&wc) == 0) return false;

    // WS_EX_LAYERED  : composition avec canal alpha par pixel.
    // WS_EX_TRANSPARENT : les clics traversent vers le jeu.
    // WS_EX_NOACTIVATE  : la fenetre ne vole jamais le focus clavier.
    // WS_EX_TOOLWINDOW  : absente de la barre des taches et d'Alt+Tab.
    const DWORD exStyle = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST
                        | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW;

    hwnd_ = CreateWindowExW(exStyle, kClassName, L"CS2 Tracker Overlay",
                            WS_POPUP, config_.x, config_.y,
                            config_.width, config_.height,
                            nullptr, nullptr, instance, this);
    if (hwnd_ == nullptr) return false;

    RegisterHotKey(hwnd_, kHotkeyToggle, 0, VK_F8);
    RegisterHotKey(hwnd_, kHotkeyCorner, 0, VK_F9);
    RegisterHotKey(hwnd_, kHotkeyQuit, MOD_CONTROL | MOD_SHIFT, VK_F8);

    ShowWindow(hwnd_, SW_SHOWNOACTIVATE);
    SetTimer(hwnd_, kRefreshTimer, static_cast<UINT>(config_.refreshMs), nullptr);
    Tick();
    return true;
}

int OverlayWindow::RunMessageLoop() {
    MSG msg;
    while (GetMessageW(&msg, nullptr, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
    return static_cast<int>(msg.wParam);
}

LRESULT CALLBACK OverlayWindow::WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    OverlayWindow* self = nullptr;
    if (msg == WM_NCCREATE) {
        auto* create = reinterpret_cast<CREATESTRUCTW*>(lp);
        self = static_cast<OverlayWindow*>(create->lpCreateParams);
        SetWindowLongPtrW(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(self));
    } else {
        self = reinterpret_cast<OverlayWindow*>(GetWindowLongPtrW(hwnd, GWLP_USERDATA));
    }
    if (self != nullptr) return self->Handle(hwnd, msg, wp, lp);
    return DefWindowProcW(hwnd, msg, wp, lp);
}

LRESULT OverlayWindow::Handle(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
        case WM_TIMER:
            if (wp == kRefreshTimer) Tick();
            return 0;

        case WM_HOTKEY:
            if (wp == kHotkeyToggle) ToggleVisible();
            else if (wp == kHotkeyCorner) CycleCorner();
            else if (wp == kHotkeyQuit) PostQuitMessage(0);
            return 0;

        case WM_DESTROY:
            KillTimer(hwnd, kRefreshTimer);
            PostQuitMessage(0);
            return 0;

        default:
            return DefWindowProcW(hwnd, msg, wp, lp);
    }
}

void OverlayWindow::Tick() {
    client_.Refresh(state_);
    if (visible_) Redraw();
}

void OverlayWindow::ToggleVisible() {
    visible_ = !visible_;
    ShowWindow(hwnd_, visible_ ? SW_SHOWNOACTIVATE : SW_HIDE);
    if (visible_) Redraw();
}

void OverlayWindow::CycleCorner() {
    corner_ = (corner_ + 1) % 4;
    const int screenW = GetSystemMetrics(SM_CXSCREEN);
    const int screenH = GetSystemMetrics(SM_CYSCREEN);
    const int margin = 24;

    int x = margin;
    int y = margin;
    if (corner_ == 1 || corner_ == 2) x = screenW - config_.width - margin;
    if (corner_ == 2 || corner_ == 3) y = screenH - config_.height - margin;

    config_.x = x;
    config_.y = y;
    SetWindowPos(hwnd_, HWND_TOPMOST, x, y, 0, 0,
                 SWP_NOSIZE | SWP_NOACTIVATE);
    Redraw();
}

void OverlayWindow::Redraw() {
    const int width = config_.width;
    const int height = config_.height;

    // Bitmap 32 bits a alpha premultiplie : exigence d'UpdateLayeredWindow.
    BITMAPINFO info = {};
    info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    info.bmiHeader.biWidth = width;
    info.bmiHeader.biHeight = -height;  // origine en haut
    info.bmiHeader.biPlanes = 1;
    info.bmiHeader.biBitCount = 32;
    info.bmiHeader.biCompression = BI_RGB;

    HDC screenDc = GetDC(nullptr);
    void* bits = nullptr;
    HBITMAP bitmap = CreateDIBSection(screenDc, &info, DIB_RGB_COLORS, &bits, nullptr, 0);
    HDC memDc = CreateCompatibleDC(screenDc);
    HGDIOBJ previous = SelectObject(memDc, bitmap);

    {
        // UpdateLayeredWindow exige un alpha *premultiplie*. Dessiner via un
        // simple `Graphics(memDc)` produirait de l'ARGB brut, que Windows
        // interpreterait comme bien plus transparent que voulu. On enveloppe
        // donc la memoire du DIB dans un Bitmap declare 32bppPARGB.
        Bitmap surface(width, height, width * 4, PixelFormat32bppPARGB,
                       static_cast<BYTE*>(bits));
        Graphics g(&surface);
        g.SetSmoothingMode(SmoothingModeAntiAlias);
        // ClearType suppose un fond opaque : sur une surface a canal alpha il
        // produit des franges colorees. L'anticrenelage classique convient.
        g.SetTextRenderingHint(TextRenderingHintAntiAliasGridFit);
        g.Clear(Color(0, 0, 0, 0));

        FontFamily uiFamily(L"Segoe UI");
        FontFamily monoFamily(L"Consolas");
        Font titleFont(&uiFamily, 15, FontStyleBold, UnitPixel);
        Font labelFont(&uiFamily, 10, FontStyleBold, UnitPixel);
        Font bodyFont(&uiFamily, 12, FontStyleRegular, UnitPixel);
        Font monoFont(&monoFamily, 12, FontStyleBold, UnitPixel);
        Font smallFont(&uiFamily, 10, FontStyleRegular, UnitPixel);

        // Fond et cadre.
        SolidBrush background(kBackground);
        g.FillRectangle(&background, 0, 0, width, height);
        Pen borderPen(kBorder, 1.0f);
        g.DrawRectangle(&borderPen, 0, 0, width - 1, height - 1);
        SolidBrush accent(kFlash);
        g.FillRectangle(&accent, 0, 0, 3, 26);

        REAL y = 10;
        DrawText(g, L"CS2 TRACKER", labelFont, kFlash, 14, y);
        DrawText(g, L"F8 masquer · F9 deplacer", smallFont, kDust,
                 static_cast<REAL>(width - 14), y + 1, StringAlignmentFar);
        y += 24;

        Pen rule(kBorder, 1.0f);
        g.DrawLine(&rule, 12.0f, y, static_cast<REAL>(width - 12), y);
        y += 12;

        const MatchState& match = state_.match;

        if (!state_.statusMessage.empty()) {
            DrawText(g, state_.statusMessage, bodyFont, kAsh, 14, y);
            y += 22;
            DrawText(g, L"L'overlay affichera la partie des qu'elle demarre.",
                     smallFont, kDust, 14, y);
        } else {
            // Bandeau de score.
            DrawText(g, Format(L"%d", match.scoreCt), monoFont, kCt, 14, y);
            DrawText(g, L":", monoFont, kDust, 44, y);
            DrawText(g, Format(L"%d", match.scoreT), monoFont, kT, 56, y);
            DrawText(g, match.map, bodyFont, kBone, 100, y);
            DrawText(g, Format(L"Manche %d · %s", match.roundNumber,
                               match.phase.c_str()),
                     smallFont, kAsh, static_cast<REAL>(width - 14), y + 2,
                     StringAlignmentFar);
            y += 24;

            if (match.bombCountdown >= 0.0) {
                DrawText(g, Format(L"BOMBE  %.1f s", match.bombCountdown),
                         labelFont, kHigh, 14, y);
                y += 18;
            }

            if (match.hasLocal) {
                DrawText(g, Format(L"%s  %d/%d  ·  %d PV  ·  %d $",
                                   match.localName.c_str(), match.localKills,
                                   match.localDeaths, match.localHealth,
                                   match.localMoney),
                         smallFont, kAsh, 14, y);
                y += 20;
            }

            g.DrawLine(&rule, 12.0f, y, static_cast<REAL>(width - 12), y);
            y += 10;

            if (match.players.empty()) {
                DrawText(g, L"Seul ton etat est transmis en partie classique.",
                         smallFont, kAsh, 14, y);
                y += 16;
                DrawText(g, L"Colle un `status` dans l'application pour analyser",
                         smallFont, kDust, 14, y);
                y += 14;
                DrawText(g, L"les dix joueurs du lobby.", smallFont, kDust, 14, y);
            } else {
                DrawText(g, L"JOUEUR", labelFont, kDust, 14, y);
                DrawText(g, L"K/D", labelFont, kDust, 262, y);
                DrawText(g, L"ADR", labelFont, kDust, 316, y);
                DrawText(g, L"RISQUE", labelFont, kDust,
                         static_cast<REAL>(width - 14), y, StringAlignmentFar);
                y += 18;

                for (const PlayerRow& player : match.players) {
                    if (y > height - 26) break;
                    const Color teamColor = player.team == L"CT" ? kCt : kT;
                    const Color nameColor = player.alive ? teamColor : kDust;

                    DrawText(g, player.name, bodyFont, nameColor, 14, y);
                    DrawText(g, Format(L"%d/%d", player.kills, player.deaths),
                             monoFont, kAsh, 262, y);
                    DrawText(g, Format(L"%.0f", player.adr), monoFont, kAsh, 316, y);

                    if (player.analysed) {
                        const Color verdictColor = ColorForVerdict(player.verdict);
                        DrawText(g, Format(L"%.0f  %s", player.suspicion,
                                           VerdictLabel(player.verdict)),
                                 monoFont, verdictColor,
                                 static_cast<REAL>(width - 14), y, StringAlignmentFar);
                    } else {
                        DrawText(g, L"non analyse", smallFont, kDust,
                                 static_cast<REAL>(width - 14), y + 1,
                                 StringAlignmentFar);
                    }
                    y += 20;
                }
            }
        }

        // Rappel permanent : le score est une estimation, pas une preuve.
        DrawText(g, L"Score statistique — ne constitue pas une preuve de triche.",
                 smallFont, kDust, 14, static_cast<REAL>(height - 20));
    }

    POINT origin = {config_.x, config_.y};
    SIZE size = {width, height};
    POINT source = {0, 0};
    BLENDFUNCTION blend = {};
    blend.BlendOp = AC_SRC_OVER;
    blend.SourceConstantAlpha = config_.opacity;
    blend.AlphaFormat = AC_SRC_ALPHA;

    UpdateLayeredWindow(hwnd_, screenDc, &origin, &size, memDc, &source, 0,
                        &blend, ULW_ALPHA);

    SelectObject(memDc, previous);
    DeleteObject(bitmap);
    DeleteDC(memDc);
    ReleaseDC(nullptr, screenDc);
}

}  // namespace cs2t
