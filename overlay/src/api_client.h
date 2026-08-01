// Client HTTP de l'API locale, base sur WinHTTP (aucune dependance externe).
#pragma once

#include <string>

#include "model.h"

namespace cs2t {

class ApiClient {
public:
    ApiClient(std::wstring host, int port);
    ~ApiClient();

    ApiClient(const ApiClient&) = delete;
    ApiClient& operator=(const ApiClient&) = delete;

    // Interroge l'API et remplit `state`. Renvoie false si l'API est
    // injoignable ; `state` conserve alors sa derniere valeur connue afin que
    // l'affichage ne clignote pas a la moindre requete perdue.
    bool Refresh(OverlayState& state);

private:
    // Renvoie une chaine vide en cas d'echec.
    std::string Get(const wchar_t* path);

    std::wstring host_;
    int port_;
    void* session_ = nullptr;  // HINTERNET
};

}  // namespace cs2t
