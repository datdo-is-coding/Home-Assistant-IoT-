#include "core_kws_control.h"
#include <algorithm>
#include <cstring>
#include <set>

namespace {
uint32_t read32(const uint8_t* p) {return uint32_t(p[0])|(uint32_t(p[1])<<8)|(uint32_t(p[2])<<16)|(uint32_t(p[3])<<24);}
void write32(uint8_t* p,uint32_t v) {for(unsigned i=0;i<4;++i)p[i]=v>>(8*i);}
void write64(uint8_t* p,uint64_t v) {for(unsigned i=0;i<8;++i)p[i]=v>>(8*i);}
constexpr const char* rooms[]={"BEDROOM","LIVING_ROOM","KITCHEN"};
}
bool CoreKwsControl::configure(const uint8_t* data,size_t size,bool persist) {
    if(!data||size<8||data[0]!=1||!read32(data+1)||data[5]>2||data[6]>4||data[7]>6||size!=8u+4u*data[6]+15u*data[7])return false;
    std::vector<uint32_t> sources;std::vector<Target> targets;
    std::set<uint32_t> ids;std::set<unsigned> pairs;std::set<uint64_t> channels;
    for(unsigned i=0;i<data[6];++i) {
        const auto id=read32(data+8+4*i);if(!id||!ids.insert(id).second)return false;sources.push_back(id);
    }
    const uint8_t* at=data+8+4*data[6];
    for(unsigned i=0;i<data[7];++i,at+=15) {
        Target target{at[0],at[1],at[2],read32(at+3),read32(at+7),read32(at+11)};
        if(target.room>2||target.role>1||target.channel<1||target.channel>3||!target.node||!target.revision||!target.parent||
           !pairs.insert(target.room*2+target.role).second||!channels.insert(uint64_t(target.node)*4+target.channel).second)return false;
        targets.push_back(target);
    }
    std::lock_guard<std::mutex> lock(m_mutex);
    if(read32(data+1)<m_revision)return false;
    const std::string snapshot(reinterpret_cast<const char*>(data),size);
    if(persist&&snapshot!=m_snapshot&&m_save&&!m_save(snapshot))return false;
    m_revision=read32(data+1);m_room=data[5];m_sources=std::move(sources);m_targets=std::move(targets);m_snapshot=snapshot;
    return true;
}
bool CoreKwsControl::utterance(const std::string& origin,const std::string& phrase) {
    std::lock_guard<std::mutex> lock(m_mutex);
    uint32_t source=0;
    if(origin.empty())return false;
    for(char c:origin) {
        if(c<'0'||c>'9'||source>(UINT32_MAX-unsigned(c-'0'))/10)return false;
        source=source*10+unsigned(c-'0');
    }
    if(std::find(m_sources.begin(),m_sources.end(),source)==m_sources.end())return false;
    const uint64_t now=m_clock();if(now<1600000000000ULL||m_request==UINT64_MAX)return false;
    const uint64_t request=++m_request;
    uint8_t reason=0;KwsPhrase command;
    if(!m_revision)reason=4;
    else if(!kwsParsePhrase(phrase,command))reason=1;
    else if(command.action.empty()||command.device.empty()||(command.explicit_room&&command.room.empty()))reason=2;
    if(command.room.empty()&&!command.explicit_room)command.room=rooms[m_room];
    const Target* target=nullptr;
    for(const auto& candidate:m_targets) {
        if(command.room==rooms[candidate.room]&&command.device==(candidate.role==0?"LIGHT":"FAN"))target=&candidate;
    }
    if(!reason&&!target)reason=3;
    if(reason) {
        uint8_t data[22]={3};write64(data+1,request);write32(data+9,source);data[13]=reason;write64(data+14,now+4000);
        return m_send(data,sizeof(data));
    }
    uint8_t data[37]={1};write64(data+1,request);write32(data+9,source);write32(data+13,target->node);
    write32(data+17,target->revision);write32(data+21,m_revision);
    data[25]=target->room;data[26]=target->role;data[27]=target->channel;data[28]=command.action=="TURN_ON";
    write64(data+29,now+4000);return m_send(data,sizeof(data));
}
