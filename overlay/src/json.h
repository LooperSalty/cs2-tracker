// Analyseur JSON minimal, sans dependance externe.
//
// L'overlay ne consomme que les reponses de l'API locale, dont la forme est
// connue : un analyseur complet serait surdimensionne. Celui-ci couvre la
// norme JSON (objets, tableaux, chaines avec echappements et surrogates,
// nombres, booleens, null) en restant assez court pour etre relu.
#pragma once

#include <map>
#include <memory>
#include <string>
#include <vector>

namespace cs2t {

class JsonValue;
using JsonPtr = std::shared_ptr<JsonValue>;

enum class JsonType { Null, Bool, Number, String, Array, Object };

class JsonValue {
public:
    JsonType type = JsonType::Null;
    bool boolean = false;
    double number = 0.0;
    std::string text;
    std::vector<JsonPtr> items;
    std::map<std::string, JsonPtr> fields;

    // Acces tolerant : une cle absente renvoie une valeur nulle plutot que de
    // lever, ce qui evite de garder l'overlay sous try/catch.
    const JsonValue& operator[](const std::string& key) const {
        static const JsonValue kNull;
        if (type != JsonType::Object) return kNull;
        auto it = fields.find(key);
        return it == fields.end() || !it->second ? kNull : *it->second;
    }

    const JsonValue& at(size_t index) const {
        static const JsonValue kNull;
        if (type != JsonType::Array || index >= items.size() || !items[index]) return kNull;
        return *items[index];
    }

    size_t size() const { return type == JsonType::Array ? items.size() : 0; }
    bool valid() const { return type != JsonType::Null; }

    std::string str(const std::string& fallback = "") const {
        return type == JsonType::String ? text : fallback;
    }
    double num(double fallback = 0.0) const {
        return type == JsonType::Number ? number : fallback;
    }
    int integer(int fallback = 0) const {
        return type == JsonType::Number ? static_cast<int>(number) : fallback;
    }
    bool flag(bool fallback = false) const {
        return type == JsonType::Bool ? boolean : fallback;
    }
};

// Renvoie une valeur nulle si le texte n'est pas du JSON valide.
JsonPtr JsonParse(const std::string& source);

}  // namespace cs2t
