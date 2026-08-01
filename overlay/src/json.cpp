#include "json.h"

#include <cstdlib>

namespace cs2t {
namespace {

class Parser {
public:
    explicit Parser(const std::string& source) : src_(source) {}

    JsonPtr Parse() {
        SkipSpace();
        JsonPtr value = ParseValue(0);
        if (!value) return nullptr;
        SkipSpace();
        return pos_ == src_.size() ? value : nullptr;
    }

private:
    // Garde-fou contre un document volontairement trop imbrique.
    static constexpr int kMaxDepth = 64;

    const std::string& src_;
    size_t pos_ = 0;

    bool Eof() const { return pos_ >= src_.size(); }
    char Peek() const { return Eof() ? '\0' : src_[pos_]; }

    void SkipSpace() {
        while (!Eof()) {
            const char c = src_[pos_];
            if (c == ' ' || c == '\t' || c == '\n' || c == '\r') ++pos_;
            else break;
        }
    }

    bool Literal(const char* text) {
        const size_t len = std::char_traits<char>::length(text);
        if (src_.compare(pos_, len, text) != 0) return false;
        pos_ += len;
        return true;
    }

    JsonPtr ParseValue(int depth) {
        if (depth > kMaxDepth || Eof()) return nullptr;
        switch (Peek()) {
            case '{': return ParseObject(depth);
            case '[': return ParseArray(depth);
            case '"': return ParseString();
            case 't': case 'f': return ParseBool();
            case 'n': return ParseNull();
            default: return ParseNumber();
        }
    }

    JsonPtr ParseObject(int depth) {
        auto node = std::make_shared<JsonValue>();
        node->type = JsonType::Object;
        ++pos_;  // '{'
        SkipSpace();
        if (Peek() == '}') { ++pos_; return node; }

        while (true) {
            SkipSpace();
            if (Peek() != '"') return nullptr;
            JsonPtr key = ParseString();
            if (!key) return nullptr;
            SkipSpace();
            if (Peek() != ':') return nullptr;
            ++pos_;
            SkipSpace();
            JsonPtr value = ParseValue(depth + 1);
            if (!value) return nullptr;
            node->fields[key->text] = value;

            SkipSpace();
            if (Peek() == ',') { ++pos_; continue; }
            if (Peek() == '}') { ++pos_; return node; }
            return nullptr;
        }
    }

    JsonPtr ParseArray(int depth) {
        auto node = std::make_shared<JsonValue>();
        node->type = JsonType::Array;
        ++pos_;  // '['
        SkipSpace();
        if (Peek() == ']') { ++pos_; return node; }

        while (true) {
            SkipSpace();
            JsonPtr value = ParseValue(depth + 1);
            if (!value) return nullptr;
            node->items.push_back(value);

            SkipSpace();
            if (Peek() == ',') { ++pos_; continue; }
            if (Peek() == ']') { ++pos_; return node; }
            return nullptr;
        }
    }

    // Encode un point de code en UTF-8 : l'API renvoie du texte accentue.
    static void AppendUtf8(std::string& out, unsigned int code) {
        if (code < 0x80) {
            out += static_cast<char>(code);
        } else if (code < 0x800) {
            out += static_cast<char>(0xC0 | (code >> 6));
            out += static_cast<char>(0x80 | (code & 0x3F));
        } else if (code < 0x10000) {
            out += static_cast<char>(0xE0 | (code >> 12));
            out += static_cast<char>(0x80 | ((code >> 6) & 0x3F));
            out += static_cast<char>(0x80 | (code & 0x3F));
        } else {
            out += static_cast<char>(0xF0 | (code >> 18));
            out += static_cast<char>(0x80 | ((code >> 12) & 0x3F));
            out += static_cast<char>(0x80 | ((code >> 6) & 0x3F));
            out += static_cast<char>(0x80 | (code & 0x3F));
        }
    }

    bool ReadHex4(unsigned int& out) {
        if (pos_ + 4 > src_.size()) return false;
        out = 0;
        for (int i = 0; i < 4; ++i) {
            const char c = src_[pos_ + i];
            out <<= 4;
            if (c >= '0' && c <= '9') out |= static_cast<unsigned>(c - '0');
            else if (c >= 'a' && c <= 'f') out |= static_cast<unsigned>(c - 'a' + 10);
            else if (c >= 'A' && c <= 'F') out |= static_cast<unsigned>(c - 'A' + 10);
            else return false;
        }
        pos_ += 4;
        return true;
    }

    JsonPtr ParseString() {
        auto node = std::make_shared<JsonValue>();
        node->type = JsonType::String;
        ++pos_;  // '"'

        while (!Eof()) {
            const char c = src_[pos_++];
            if (c == '"') return node;
            if (c != '\\') { node->text += c; continue; }
            if (Eof()) return nullptr;

            const char esc = src_[pos_++];
            switch (esc) {
                case '"': node->text += '"'; break;
                case '\\': node->text += '\\'; break;
                case '/': node->text += '/'; break;
                case 'b': node->text += '\b'; break;
                case 'f': node->text += '\f'; break;
                case 'n': node->text += '\n'; break;
                case 'r': node->text += '\r'; break;
                case 't': node->text += '\t'; break;
                case 'u': {
                    unsigned int code = 0;
                    if (!ReadHex4(code)) return nullptr;
                    // Paire de substitution : recompose le point de code reel.
                    if (code >= 0xD800 && code <= 0xDBFF && pos_ + 1 < src_.size()
                        && src_[pos_] == '\\' && src_[pos_ + 1] == 'u') {
                        pos_ += 2;
                        unsigned int low = 0;
                        if (!ReadHex4(low)) return nullptr;
                        if (low >= 0xDC00 && low <= 0xDFFF) {
                            code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00);
                        }
                    }
                    AppendUtf8(node->text, code);
                    break;
                }
                default: return nullptr;
            }
        }
        return nullptr;
    }

    JsonPtr ParseNumber() {
        const size_t start = pos_;
        if (Peek() == '-' || Peek() == '+') ++pos_;
        while (!Eof()) {
            const char c = src_[pos_];
            if ((c >= '0' && c <= '9') || c == '.' || c == 'e' || c == 'E'
                || c == '+' || c == '-') {
                ++pos_;
            } else {
                break;
            }
        }
        if (pos_ == start) return nullptr;

        auto node = std::make_shared<JsonValue>();
        node->type = JsonType::Number;
        node->number = std::strtod(src_.substr(start, pos_ - start).c_str(), nullptr);
        return node;
    }

    JsonPtr ParseBool() {
        auto node = std::make_shared<JsonValue>();
        node->type = JsonType::Bool;
        if (Literal("true")) { node->boolean = true; return node; }
        if (Literal("false")) { node->boolean = false; return node; }
        return nullptr;
    }

    JsonPtr ParseNull() {
        if (!Literal("null")) return nullptr;
        return std::make_shared<JsonValue>();
    }
};

}  // namespace

JsonPtr JsonParse(const std::string& source) {
    return Parser(source).Parse();
}

}  // namespace cs2t
