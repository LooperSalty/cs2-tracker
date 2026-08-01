// Structures affichees par l'overlay, remplies depuis l'API locale.
#pragma once

#include <string>
#include <vector>

namespace cs2t {

// Palier de verdict renvoye par le moteur anti-triche.
enum class Verdict { Unknown, Clean, Low, Moderate, High, Critical };

Verdict VerdictFromString(const std::string& text);
const wchar_t* VerdictLabel(Verdict verdict);

struct PlayerRow {
    std::wstring name;
    std::string steamid;
    std::wstring team;      // "CT" ou "T"
    int kills = 0;
    int deaths = 0;
    int assists = 0;
    double adr = 0.0;
    double headshotRate = 0.0;
    bool alive = true;
    int health = 100;

    // Renseignes uniquement si une analyse existe pour ce joueur.
    bool analysed = false;
    double suspicion = 0.0;
    Verdict verdict = Verdict::Unknown;
    std::wstring topReason;
};

struct MatchState {
    bool connected = false;
    std::wstring map;
    std::wstring mode;
    std::wstring phase;
    int roundNumber = 0;
    int scoreCt = 0;
    int scoreT = 0;
    double bombCountdown = -1.0;

    // Etat du joueur local, toujours transmis meme en partie classique.
    bool hasLocal = false;
    std::wstring localName;
    int localKills = 0;
    int localDeaths = 0;
    int localHealth = 0;
    int localMoney = 0;
    int localRoundKills = 0;

    std::vector<PlayerRow> players;
};

// Etat global de l'overlay, unique source de verite du rendu.
struct OverlayState {
    bool apiReachable = false;
    std::wstring statusMessage = L"Connexion a CS2 Tracker...";
    MatchState match;
};

}  // namespace cs2t
