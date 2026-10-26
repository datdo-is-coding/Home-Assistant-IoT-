#pragma once
#include "kws_config.h"
#include <cmath>
#include <string>

// Assembly never actuates: the complete phrase is resolved only at stream end.
class KwsCommand {
public:
    void reset() { action = device = room = -1; invalid = has_room_word = false; }
    void add(int id, float confidence) {
        if (id < 0 || id >= NUM_CLASSES) { invalid = true; return; }
        if (!std::isfinite(confidence) || confidence < 0.75f || confidence > 1.f) return;
        if (id == CLASS_NOISE || id == CLASS_UNKNOWN) return;
        if (id == CLASS_PHONG) { has_room_word = true; return; }
        int* slot = (id == CLASS_BAT || id == CLASS_TAT) ? &action :
                    (id == CLASS_DEN || id == CLASS_QUAT) ? &device : &room;
        if (*slot >= 0 && *slot != id) invalid = true;
        else *slot = id;
    }
    std::string text() const {
        if (invalid) return "__KWS_INVALID__";
        std::string out;
        auto append = [&out](const char* word) { if (!out.empty()) out += ' '; out += word; };
        if (action >= 0) append(KWS_LABELS[action]);
        if (device >= 0) append(KWS_LABELS[device]);
        if (room >= 0) {
            if (room != CLASS_BEP) append("phòng");
            append(KWS_LABELS[room]);
        } else if (has_room_word) append("phòng");
        return out.empty() ? "__KWS_EMPTY__" : out;
    }
private:
    int action = -1, device = -1, room = -1;
    bool invalid = false, has_room_word = false;
};
