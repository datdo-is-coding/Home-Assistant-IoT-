#pragma once
#include "kws_control.h"
#include <mutex>

class CoreKwsControl {
public:
    using Send=std::function<bool(const uint8_t*,size_t)>;
    using Save=std::function<bool(const std::string&)>;
    using Clock=std::function<uint64_t()>;
    CoreKwsControl(Send send,Save save,Clock clock):m_send(send),m_save(save),m_clock(clock){}
    bool configure(const uint8_t* data,size_t size,bool persist=true);
    bool utterance(const std::string& origin,const std::string& phrase);
private:
    struct Target {uint8_t room,role,channel;uint32_t node,revision,parent;};
    std::mutex m_mutex;
    uint32_t m_revision=0;
    uint8_t m_room=0;
    uint64_t m_request=0;
    std::vector<uint32_t> m_sources;
    std::vector<Target> m_targets;
    std::string m_snapshot;
    Send m_send;Save m_save;Clock m_clock;
};
