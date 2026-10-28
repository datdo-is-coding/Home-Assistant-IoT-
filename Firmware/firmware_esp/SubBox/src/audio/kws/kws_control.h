#pragma once
#include <cstdint>
#include <functional>
#include <map>
#include <string>
#include <vector>
#include "cJSON.h"

std::string kwsString(const cJSON* object, const char* key);
uint32_t kwsUint(const cJSON* object, const char* key);
std::string kwsEncode(const cJSON* object);

struct KwsPeer {
    std::string node_id, subbox_id, hardware_uid;
    uint32_t config_version=0, owner_epoch=0;
};
struct KwsBinding : KwsPeer {
    std::string room, device;
    uint8_t channel=0;
};
struct KwsSource : KwsPeer { std::string room; };
struct KwsPhrase {
    std::string action, device, room;
    bool explicit_room=false;
};
bool kwsParsePhrase(const std::string& phrase,KwsPhrase& command);

// All methods run on the MQTT/command boundary; callbacks provide the device edge.
class KwsControl {
public:
    using Publish=std::function<bool(const std::string&,const std::string&)>;
    using Trusted=std::function<bool(const KwsPeer&)>;
    using Send=std::function<bool(const KwsPeer&,const std::string&,std::string&)>;
    using Save=std::function<bool(const std::string&)>;
    using Clock=std::function<uint64_t()>;
    using Listen=std::function<bool(const KwsPeer&,uint32_t,uint32_t)>;
    using Feedback=std::function<void(const char*,const char*)>;
    using WallClock=std::function<uint64_t()>;
    KwsControl(std::string subbox,uint32_t session,Publish publish,Trusted trusted,Send send,Save save,Clock clock,
        Listen listen={},Feedback feedback={},WallClock wall={});
    bool restore(const std::string& snapshot);
    bool handle(const std::string& topic,const std::string& payload);
    void utterance(const std::string& origin,const std::string& phrase);
    void tick();
private:
    struct Command : KwsPhrase {
        uint32_t request=0, session=0;
        std::string origin;
        bool follow_up=false;
        KwsBinding binding;
    };
    struct Pending { Command command; uint64_t deadline=0; std::string phase; };
    struct Seen { uint64_t deadline=0; std::string ack; };
    bool configure(const std::string& payload,bool persist);
    void resolve(Command command);
    void result(const Command&,const char* status,const char* reason,const std::string& state="");
    std::string execute(const Command&);
    bool remote(const std::string& payload);
    bool ack(const std::string& payload);
    std::string wire(const Command&,const char* kind) const;
    const KwsSource* source(const std::string& node) const;
    const KwsBinding* binding(const std::string& room,const std::string& device) const;
    bool payloadPeer(const cJSON* root,KwsPeer& peer,const char* prefix="") const;
    std::string m_subbox;
    uint32_t m_session,m_request=0,m_revision=0;
    std::string m_snapshot;
    Publish m_publish; Trusted m_trusted; Send m_send; Save m_save; Clock m_clock;
    Listen m_listen; Feedback m_feedback; WallClock m_wall;
    std::vector<KwsSource> m_sources;
    std::vector<KwsBinding> m_bindings;
    std::map<std::string,Pending> m_pending;
    std::map<std::string,Seen> m_seen;
};
