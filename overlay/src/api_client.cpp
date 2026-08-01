#include "api_client.h"

#include <windows.h>
#include <winhttp.h>

#include <algorithm>
#include <map>

#include "json.h"

#pragma comment(lib, "winhttp.lib")

namespace cs2t {
namespace {

// L'API est locale : au-dela de ce delai elle est consideree absente.
constexpr int kTimeoutMs = 1500;
constexpr size_t kMaxResponseBytes = 4 * 1024 * 1024;

std::wstring Widen(const std::string& utf8) {
    if (utf8.empty()) return {};
    const int size = MultiByteToWideChar(CP_UTF8, 0, utf8.c_str(),
                                         static_cast<int>(utf8.size()), nullptr, 0);
    if (size <= 0) return {};
    std::wstring wide(static_cast<size_t>(size), L'\0');
    MultiByteToWideChar(CP_UTF8, 0, utf8.c_str(), static_cast<int>(utf8.size()),
                        wide.data(), size);
    return wide;
}

}  // namespace

Verdict VerdictFromString(const std::string& text) {
    if (text == "CLEAN") return Verdict::Clean;
    if (text == "LOW") return Verdict::Low;
    if (text == "MODERATE") return Verdict::Moderate;
    if (text == "HIGH") return Verdict::High;
    if (text == "CRITICAL") return Verdict::Critical;
    return Verdict::Unknown;
}

const wchar_t* VerdictLabel(Verdict verdict) {
    switch (verdict) {
        case Verdict::Clean: return L"OK";
        case Verdict::Low: return L"FAIBLE";
        case Verdict::Moderate: return L"MOYEN";
        case Verdict::High: return L"ELEVE";
        case Verdict::Critical: return L"CRITIQUE";
        default: return L"—";
    }
}

ApiClient::ApiClient(std::wstring host, int port)
    : host_(std::move(host)), port_(port) {
    session_ = WinHttpOpen(L"CS2TrackerOverlay/1.0",
                           WINHTTP_ACCESS_TYPE_NO_PROXY,
                           WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (session_ != nullptr) {
        WinHttpSetTimeouts(session_, kTimeoutMs, kTimeoutMs, kTimeoutMs, kTimeoutMs);
    }
}

ApiClient::~ApiClient() {
    if (session_ != nullptr) WinHttpCloseHandle(session_);
}

std::string ApiClient::Get(const wchar_t* path) {
    if (session_ == nullptr) return {};

    HINTERNET connection = WinHttpConnect(session_, host_.c_str(),
                                          static_cast<INTERNET_PORT>(port_), 0);
    if (connection == nullptr) return {};

    HINTERNET request = WinHttpOpenRequest(connection, L"GET", path, nullptr,
                                           WINHTTP_NO_REFERER,
                                           WINHTTP_DEFAULT_ACCEPT_TYPES, 0);
    if (request == nullptr) {
        WinHttpCloseHandle(connection);
        return {};
    }

    std::string body;
    if (WinHttpSendRequest(request, WINHTTP_NO_ADDITIONAL_HEADERS, 0,
                           WINHTTP_NO_REQUEST_DATA, 0, 0, 0)
        && WinHttpReceiveResponse(request, nullptr)) {
        DWORD available = 0;
        while (WinHttpQueryDataAvailable(request, &available) && available > 0) {
            if (body.size() + available > kMaxResponseBytes) break;
            const size_t offset = body.size();
            body.resize(offset + available);
            DWORD read = 0;
            if (!WinHttpReadData(request, body.data() + offset, available, &read)) {
                body.resize(offset);
                break;
            }
            body.resize(offset + read);
        }
    }

    WinHttpCloseHandle(request);
    WinHttpCloseHandle(connection);
    return body;
}

bool ApiClient::Refresh(OverlayState& state) {
    const std::string stateBody = Get(L"/api/live/state");
    if (stateBody.empty()) {
        state.apiReachable = false;
        state.statusMessage = L"CS2 Tracker introuvable — lance l'application.";
        return false;
    }

    JsonPtr root = JsonParse(stateBody);
    if (!root || !(*root)["success"].flag()) {
        state.apiReachable = false;
        state.statusMessage = L"Reponse inattendue de CS2 Tracker.";
        return false;
    }

    state.apiReachable = true;
    MatchState match;

    const JsonValue& data = (*root)["data"];
    match.connected = data["connected"].flag();
    const JsonValue& live = data["state"];

    if (!match.connected || !live.valid()) {
        state.statusMessage = L"En attente de CS2 — lance une partie.";
        state.match = match;
        return true;
    }

    const JsonValue& map = live["map"];
    match.map = Widen(map["name"].str());
    match.mode = Widen(map["mode"].str());
    match.roundNumber = map["round"].integer();
    match.scoreCt = map["team_ct"]["score"].integer();
    match.scoreT = map["team_t"]["score"].integer();
    match.phase = Widen(live["round"]["phase"].str());

    const JsonValue& bomb = live["bomb"];
    if (bomb["state"].str() == "planted") {
        match.bombCountdown = bomb["countdown"].num(-1.0);
    }

    const JsonValue& local = live["player"];
    if (local.valid()) {
        match.hasLocal = true;
        match.localName = Widen(local["name"].str());
        match.localKills = local["match_stats"]["kills"].integer();
        match.localDeaths = local["match_stats"]["deaths"].integer();
        match.localHealth = local["state"]["health"].integer();
        match.localMoney = local["state"]["money"].integer();
        match.localRoundKills = local["state"]["round_kills"].integer();
    }

    // Tableau des scores : renseigne uniquement en spectateur ou GOTV.
    const std::string boardBody = Get(L"/api/live/scoreboard");
    JsonPtr board = JsonParse(boardBody);
    if (board && (*board)["success"].flag()) {
        const JsonValue& rows = (*board)["data"];
        for (size_t i = 0; i < rows.size(); ++i) {
            const JsonValue& row = rows.at(i);
            PlayerRow player;
            player.name = Widen(row["name"].str());
            player.steamid = row["steamid"].str();
            player.team = Widen(row["team"].str());
            player.kills = row["kills"].integer();
            player.deaths = row["deaths"].integer();
            player.assists = row["assists"].integer();
            player.adr = row["adr"].num();
            player.headshotRate = row["headshot_rate"].num();
            player.health = row["health"].integer(100);
            player.alive = player.health > 0;
            match.players.push_back(std::move(player));
        }
    }

    // Analyses deja calculees : on les rapproche des joueurs presents.
    if (!match.players.empty()) {
        const std::string boardAnalyses = Get(L"/api/anticheat/leaderboard/suspicious?limit=100");
        JsonPtr analyses = JsonParse(boardAnalyses);
        if (analyses && (*analyses)["success"].flag()) {
            std::map<std::string, const JsonValue*> byId;
            const JsonValue& entries = (*analyses)["data"];
            for (size_t i = 0; i < entries.size(); ++i) {
                byId[entries.at(i)["steamid64"].str()] = &entries.at(i);
            }
            for (PlayerRow& player : match.players) {
                auto it = byId.find(player.steamid);
                if (it == byId.end()) continue;
                player.analysed = true;
                player.suspicion = (*it->second)["score"].num();
                player.verdict = VerdictFromString((*it->second)["verdict"].str());
            }
        }
    }

    std::stable_sort(match.players.begin(), match.players.end(),
                     [](const PlayerRow& a, const PlayerRow& b) {
                         if (a.team != b.team) return a.team < b.team;
                         return a.kills > b.kills;
                     });

    state.statusMessage.clear();
    state.match = std::move(match);
    return true;
}

}  // namespace cs2t
