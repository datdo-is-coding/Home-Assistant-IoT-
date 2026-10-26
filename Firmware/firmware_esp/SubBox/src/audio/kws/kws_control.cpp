#include "kws_control.h"
#include <algorithm>
#include <cstring>
#include <ctime>
#include <set>
#include <utility>

std::string kwsString(const cJSON* object,const char* key) {
    const auto* value=cJSON_GetObjectItemCaseSensitive(object,key);
    return cJSON_IsString(value)&&value->valuestring?value->valuestring:"";
}
uint32_t kwsUint(const cJSON* object,const char* key) {
    const auto* value=cJSON_GetObjectItemCaseSensitive(object,key);
    if(!cJSON_IsNumber(value)||value->valuedouble<1||value->valuedouble>UINT32_MAX) return 0;
    const auto number=static_cast<uint32_t>(value->valuedouble);
    return value->valuedouble==number?number:0;
}
std::string kwsEncode(const cJSON* object) {
    char* encoded=cJSON_PrintUnformatted(object);
    std::string out=encoded?encoded:""; cJSON_free(encoded); return out;
}
namespace {
constexpr uint64_t PLAYBACK_TIMEOUT_MS=20000;
constexpr uint64_t LISTEN_TIMEOUT_MS=15000;
constexpr uint64_t REMOTE_TIMEOUT_MS=5000;
constexpr uint64_t REMOTE_MAX_AGE_S=REMOTE_TIMEOUT_MS/1000;
constexpr uint64_t TRUSTED_TIME_S=1600000000ULL;

bool validHex(const std::string& value) {
    return value.size()==12 && value.find_first_not_of("0123456789ABCDEF")==std::string::npos;
}
bool validId(const std::string& id,const char* prefix) {
    return id.size()==14 && id.compare(0,2,prefix)==0 && validHex(id.substr(2));
}
bool validRoom(const std::string& room) { return room=="BEDROOM"||room=="LIVING_ROOM"||room=="KITCHEN"; }
bool uniqueKeys(const cJSON* root) {
    std::set<std::string> keys;
    for(const cJSON* child=root?root->child:nullptr;child;child=child->next) {
        if(cJSON_IsObject(root)&&(!child->string||!keys.insert(child->string).second)) return false;
        if(!uniqueKeys(child)) return false;
    }
    return true;
}
cJSON* decode(const std::string& payload) {
    if(payload.empty()||payload.size()>16384||payload.find('\0')!=std::string::npos) return nullptr;
    cJSON* root=cJSON_ParseWithOpts(payload.c_str(),nullptr,true);
    if(!cJSON_IsObject(root)||!uniqueKeys(root)) {cJSON_Delete(root);return nullptr;} return root;
}
bool readPeer(const cJSON* root,KwsPeer& peer) {
    peer.node_id=kwsString(root,"node_id");peer.subbox_id=kwsString(root,"subbox_id");
    peer.hardware_uid=kwsString(root,"hardware_uid");peer.config_version=kwsUint(root,"config_version");
    peer.owner_epoch=kwsUint(root,"owner_epoch");
    return validId(peer.node_id,"AB")&&validId(peer.subbox_id,"SB")&&validHex(peer.hardware_uid)&&
        peer.node_id=="AB"+peer.hardware_uid&&peer.config_version&&peer.owner_epoch;
}
bool samePeer(const KwsPeer& a,const KwsPeer& b) {
    return a.node_id==b.node_id&&a.subbox_id==b.subbox_id&&a.hardware_uid==b.hardware_uid&&
        a.config_version==b.config_version&&a.owner_epoch==b.owner_epoch;
}
void addPeer(cJSON* root,const KwsPeer& peer) {
    cJSON_AddStringToObject(root,"node_id",peer.node_id.c_str());
    cJSON_AddStringToObject(root,"subbox_id",peer.subbox_id.c_str());
    cJSON_AddStringToObject(root,"hardware_uid",peer.hardware_uid.c_str());
    cJSON_AddNumberToObject(root,"config_version",peer.config_version);
    cJSON_AddNumberToObject(root,"owner_epoch",peer.owner_epoch);
}
void addPeer(cJSON* root,const KwsPeer& peer,const char* prefix) {
    const std::string p=prefix;
    cJSON_AddStringToObject(root,(p+"node_id").c_str(),peer.node_id.c_str());
    cJSON_AddStringToObject(root,(p+"subbox_id").c_str(),peer.subbox_id.c_str());
    cJSON_AddStringToObject(root,(p+"hardware_uid").c_str(),peer.hardware_uid.c_str());
    cJSON_AddNumberToObject(root,(p+"config_version").c_str(),peer.config_version);
    cJSON_AddNumberToObject(root,(p+"owner_epoch").c_str(),peer.owner_epoch);
}
}
KwsControl::KwsControl(std::string subbox,uint32_t session,Publish publish,Trusted trusted,Send send,Save save,Clock clock,
    Listen listen,Feedback feedback,WallClock wall)
    :m_subbox(std::move(subbox)),m_session(session?session:1),m_publish(std::move(publish)),m_trusted(std::move(trusted)),
     m_send(std::move(send)),m_save(std::move(save)),m_clock(std::move(clock)),m_listen(std::move(listen)),
     m_feedback(std::move(feedback)),m_wall(std::move(wall)) {
    if(!m_wall) m_wall=[]() {return static_cast<uint64_t>(std::time(nullptr));};
}
bool KwsControl::restore(const std::string& snapshot) {return configure(snapshot,false);}
const KwsSource* KwsControl::source(const std::string& node) const {
    for(const auto& source:m_sources) if(source.node_id==node)return &source;
    return nullptr;
}
const KwsBinding* KwsControl::binding(const std::string& room,const std::string& device) const {
    for(const auto& binding:m_bindings)if(binding.room==room&&binding.device==device)return &binding;
    return nullptr;
}
bool KwsControl::configure(const std::string& payload,bool persist) {
    cJSON* root=decode(payload);
    if(!root)return false;
    const uint32_t revision=kwsUint(root,"revision");
    const auto* sources=cJSON_GetObjectItemCaseSensitive(root,"sources");
    const auto* bindings=cJSON_GetObjectItemCaseSensitive(root,"bindings");
    bool valid=kwsString(root,"cmd")=="KWS_CONFIG"&&revision&&cJSON_IsArray(sources)&&cJSON_IsArray(bindings)&&
        cJSON_GetArraySize(sources)<=32&&cJSON_GetArraySize(bindings)<=6;
    std::vector<KwsSource> next_sources;
    std::vector<KwsBinding> next_bindings;
    std::set<std::string> source_ids,roles,channels;
    const cJSON* entry;
    if(cJSON_IsArray(sources)) cJSON_ArrayForEach(entry,sources) {
        KwsSource s;s.room=kwsString(entry,"room");
        valid=valid&&cJSON_IsObject(entry)&&readPeer(entry,s)&&validRoom(s.room)&&source_ids.insert(s.node_id).second;
        if(valid) next_sources.push_back(s);
    }
    if(cJSON_IsArray(bindings)) cJSON_ArrayForEach(entry,bindings) {
        KwsBinding b;b.room=kwsString(entry,"room");b.device=kwsString(entry,"device");
        const uint32_t channel=kwsUint(entry,"channel");b.channel=static_cast<uint8_t>(channel);
        valid=valid&&cJSON_IsObject(entry)&&readPeer(entry,b)&&validRoom(b.room)&&(b.device=="LIGHT"||b.device=="FAN")&&
            channel>=1&&channel<=3&&roles.insert(b.room+":"+b.device).second&&
            channels.insert(b.node_id+":"+std::to_string(channel)).second;
        if(valid) next_bindings.push_back(b);
    }
    // One physical board cannot acquire conflicting owners/revisions in the same snapshot.
    for(const auto& b:next_bindings) {
        for(const auto& s:next_sources)if(b.node_id==s.node_id&&!samePeer(b,s))valid=false;
        for(const auto& other:next_bindings)if(b.node_id==other.node_id&&!samePeer(b,other))valid=false;
    }
    const std::string normalized=kwsEncode(root);
    if(revision<m_revision||(revision==m_revision&&normalized!=m_snapshot))valid=false;
    if(valid&&persist&&revision!=m_revision)valid=m_save(normalized);
    if(valid) {
        if(revision!=m_revision){m_pending.clear();m_seen.clear();}
        m_revision=revision;m_snapshot=normalized;m_sources=std::move(next_sources);m_bindings=std::move(next_bindings);
    }
    if(persist) {
        cJSON* ack=cJSON_CreateObject();cJSON_AddNumberToObject(ack,"revision",revision);
        cJSON_AddStringToObject(ack,"status",valid?"applied":"error");
        m_publish("kws_config",kwsEncode(ack));cJSON_Delete(ack);
    }
    cJSON_Delete(root);return valid;
}

bool KwsControl::parse(const std::string& phrase,Command& command) {
    std::string remaining=phrase;
    struct Token { const char* text; const char* value; unsigned kind; };
    static const Token tokens[]={{"phòng khách","LIVING_ROOM",2},{"phòng ngủ","BEDROOM",2},{"phòng bếp","KITCHEN",2},
        {"bật","TURN_ON",0},{"tắt","TURN_OFF",0},{"đèn","LIGHT",1},{"quạt","FAN",1},{"phòng","",3},
        {"khách","LIVING_ROOM",2},{"ngủ","BEDROOM",2},{"bếp","KITCHEN",2}};
    unsigned count=0;
    while(!remaining.empty()) {
        bool found=false;
        for(const auto& token:tokens) {
            const size_t length=strlen(token.text);
            if(remaining.compare(0,length,token.text)!=0||(remaining.size()>length&&remaining[length]!=' '))continue;
            if(token.kind==3) { if(command.explicit_room)return false;command.explicit_room=true; }
            else {
                std::string& field=token.kind==0?command.action:token.kind==1?command.device:command.room;
                if(!field.empty())return false;
                field=token.value;if(token.kind==2)command.explicit_room=true;
            }
            remaining.erase(0,length);if(!remaining.empty())remaining.erase(0,1);
            found=true;++count;break;
        }
        if(!found||count>4)return false;
    }
    return count>0;
}
void KwsControl::result(const Command& command,const char* status,const char* reason,const std::string& state) {
    cJSON* root=cJSON_CreateObject();
    cJSON_AddNumberToObject(root,"issued_at",m_wall());
    cJSON_AddNumberToObject(root,"schema_version",1);cJSON_AddNumberToObject(root,"session_id",command.session);
    cJSON_AddNumberToObject(root,"request_id",command.request);cJSON_AddStringToObject(root,"origin_node",command.origin.c_str());
    if(!command.binding.node_id.empty()) {
        cJSON_AddStringToObject(root,"target_node",command.binding.node_id.c_str());
        cJSON_AddStringToObject(root,"target_subbox",command.binding.subbox_id.c_str());
        cJSON_AddNumberToObject(root,"channel",command.binding.channel);
    }
    if(!command.action.empty())cJSON_AddStringToObject(root,"action",command.action.c_str());
    cJSON_AddStringToObject(root,"status",status);cJSON_AddStringToObject(root,"reason",reason);
    // Gateway offers a spoken question only for the first incomplete turn.
    cJSON_AddBoolToObject(root,"follow_up",strcmp(status,"incomplete")==0);
    if(!state.empty())cJSON_AddStringToObject(root,"state",state.c_str());
    m_publish("kws_result",kwsEncode(root));cJSON_Delete(root);
    if(m_feedback)m_feedback(status,reason);
}
void KwsControl::utterance(const std::string& origin,const std::string& phrase) {
    tick();
    Command command;command.origin=origin;command.session=m_session;command.request=++m_request;
    if(!command.request)command.request=++m_request;
    const auto* s=source(origin);
    if(!s||s->subbox_id!=m_subbox||!m_trusted(*s)) {result(command,"error","unknown_source");return;}
    auto pending=m_pending.find(origin);
    if(pending!=m_pending.end()) {
        if(pending->second.phase!="listening") {result(command,"error","busy");return;}
        command=pending->second.command;command.follow_up=true;m_pending.erase(pending);
    }
    if(phrase=="__KWS_EMPTY__") {result(command,"error","no_command");return;}
    if(phrase=="__KWS_AUDIO_ERROR__") {result(command,"error","audio_error");return;}
    if(!parse(phrase,command)) {result(command,"error","invalid_command");return;}
    if(command.room.empty()&&!command.explicit_room)command.room=s->room;
    resolve(command);
}
void KwsControl::resolve(Command command) {
    const char* missing=command.action.empty()?"missing_action":command.device.empty()?"missing_device":command.room.empty()?"missing_room":nullptr;
    if(missing) {
        if(command.follow_up){result(command,"error","incomplete_command");return;}
        m_pending[command.origin]={command,m_clock()+PLAYBACK_TIMEOUT_MS,"playback"};
        result(command,"incomplete",missing);return;
    }
    const auto* target=binding(command.room,command.device);
    if(!target){result(command,"error","missing_binding");return;}
    command.binding=*target;
    if(target->subbox_id!=m_subbox) {
        if(m_pending.size()>=8){result(command,"error","busy");return;}
        m_pending[command.origin]={command,m_clock()+REMOTE_TIMEOUT_MS,"remote"};
        if(!m_publish("kws_command/"+target->subbox_id,wire(command,"KWS_REMOTE"))) {
            m_pending.erase(command.origin);result(command,"error","remote_unavailable");
        }
        return;
    }
    const std::string outcome=execute(command);
    result(command,outcome=="ON"||outcome=="OFF"?"success":"error",outcome=="ON"||outcome=="OFF"?"ok":outcome.c_str(),outcome=="ON"||outcome=="OFF"?outcome:"");
}
std::string KwsControl::execute(const Command& command) {
    if(command.binding.subbox_id!=m_subbox||!m_trusted(command.binding))return "stale_target";
    cJSON* root=cJSON_CreateObject();addPeer(root,command.binding);
    cJSON_AddNumberToObject(root,"protocol_version",3);cJSON_AddNumberToObject(root,"session_id",command.session);
    cJSON_AddNumberToObject(root,"request_id",command.request);cJSON_AddNumberToObject(root,"channel",command.binding.channel);
    cJSON_AddStringToObject(root,"cmd",command.action.c_str());
    std::string ack;const bool sent=m_send(command.binding,kwsEncode(root),ack);cJSON_Delete(root);
    if(!sent)return "device_unreachable";
    root=decode(ack);
    if(!root)return "invalid_ack";
    const std::string state=kwsString(root,"state");
    const bool valid=kwsUint(root,"protocol_version")==3&&kwsUint(root,"session_id")==command.session&&
        kwsUint(root,"request_id")==command.request&&kwsString(root,"node_id")==command.binding.node_id&&
        kwsString(root,"hardware_uid")==command.binding.hardware_uid&&kwsUint(root,"config_version")==command.binding.config_version&&
        kwsUint(root,"owner_epoch")==command.binding.owner_epoch&&kwsUint(root,"channel")==command.binding.channel&&kwsString(root,"status")=="OK";
    cJSON_Delete(root);
    if(!valid)return "invalid_ack";
    if((command.action=="TURN_ON"&&state!="ON")||(command.action=="TURN_OFF"&&state!="OFF"))return "state_mismatch";
    return state;
}
std::string KwsControl::wire(const Command& command,const char* kind) const {
    cJSON* root=cJSON_CreateObject();addPeer(root,command.binding);
    cJSON_AddStringToObject(root,"cmd",kind);cJSON_AddNumberToObject(root,"revision",m_revision);
    cJSON_AddNumberToObject(root,"session_id",command.session);cJSON_AddNumberToObject(root,"request_id",command.request);
    cJSON_AddStringToObject(root,"origin_node",command.origin.c_str());cJSON_AddStringToObject(root,"action",command.action.c_str());
    cJSON_AddStringToObject(root,"room",command.room.c_str());cJSON_AddStringToObject(root,"device",command.device.c_str());
    cJSON_AddNumberToObject(root,"channel",command.binding.channel);
    if(const auto* s=source(command.origin)) {
        addPeer(root,*s,"origin_");cJSON_AddStringToObject(root,"origin_subbox",s->subbox_id.c_str());
    }
    cJSON_AddNumberToObject(root,"issued_at",m_wall());
    std::string out=kwsEncode(root);cJSON_Delete(root);return out;
}
bool KwsControl::payloadPeer(const cJSON* root,KwsPeer& peer,const char* prefix) const {
    const std::string p=prefix;
    peer.node_id=kwsString(root,(p+"node_id").c_str());
    peer.subbox_id=kwsString(root,(p+"subbox_id").c_str());
    peer.hardware_uid=kwsString(root,(p+"hardware_uid").c_str());
    peer.config_version=kwsUint(root,(p+"config_version").c_str());
    peer.owner_epoch=kwsUint(root,(p+"owner_epoch").c_str());
    return validId(peer.node_id,"AB")&&validId(peer.subbox_id,"SB")&&validHex(peer.hardware_uid)&&
        peer.node_id=="AB"+peer.hardware_uid&&peer.config_version&&peer.owner_epoch;
}
bool KwsControl::remote(const std::string& payload) {
    cJSON* root=decode(payload);
    if(!root)return false;
    bool valid=kwsString(root,"cmd")=="KWS_REMOTE"&&kwsUint(root,"revision")==m_revision;
    const uint32_t session=kwsUint(root,"session_id"),request=kwsUint(root,"request_id");
    const auto* targetBinding=binding(kwsString(root,"room"),kwsString(root,"device"));
    KwsBinding target;KwsPeer origin;
    valid=valid&&session&&request&&targetBinding&&payloadPeer(root,target)&&payloadPeer(root,origin,"origin_");
    if(valid) {
        valid=samePeer(target,*targetBinding)&&target.subbox_id==m_subbox&&
            kwsUint(root,"channel")==targetBinding->channel&&
            (kwsString(root,"action")=="TURN_ON"||kwsString(root,"action")=="TURN_OFF")&&
            kwsString(root,"origin_subbox")==origin.subbox_id&&origin.subbox_id!=m_subbox;
    }
    const auto* originSource=source(origin.node_id);
    valid=valid&&originSource&&samePeer(*originSource,origin)&&originSource->subbox_id==origin.subbox_id;
    if(!valid){cJSON_Delete(root);return false;}
    Command command;command.origin=origin.node_id;command.session=session;command.request=request;
    command.action=kwsString(root,"action");command.room=targetBinding->room;command.device=targetBinding->device;
    command.binding=*targetBinding;
    const std::string key=origin.subbox_id+":"+origin.node_id+":"+std::to_string(session)+":"+std::to_string(request);
    auto seen=m_seen.find(key);
    if(seen!=m_seen.end()&&seen->second.deadline>=m_clock()) {
        m_publish("kws_ack/"+origin.subbox_id,seen->second.ack);cJSON_Delete(root);return true;
    }
    // Keep unexpired dedup evidence; overload must never turn a retry into a new actuation.
    if(m_seen.size()>=64){cJSON_Delete(root);return false;}
    const uint64_t now=m_wall(),issued=kwsUint(root,"issued_at");
    const char* failure=nullptr;
    if(now<TRUSTED_TIME_S)failure="clock_untrusted";
    else if(!issued||issued+REMOTE_MAX_AGE_S<=now||issued>now+1)failure="expired_request";
    std::string outcome;
    if(!failure) {
        outcome=execute(command);
        if(outcome=="stale_target")failure="stale_target";
        else if(outcome=="device_unreachable")failure="device_unreachable";
        else if(outcome=="invalid_ack")failure="invalid_ack";
        else if(outcome=="state_mismatch")failure="state_mismatch";
    }
    cJSON* ackRoot=cJSON_CreateObject();
    cJSON_AddStringToObject(ackRoot,"cmd","KWS_ACK");cJSON_AddNumberToObject(ackRoot,"schema_version",1);
    cJSON_AddNumberToObject(ackRoot,"session_id",session);cJSON_AddNumberToObject(ackRoot,"request_id",request);
    cJSON_AddStringToObject(ackRoot,"origin_node",origin.node_id.c_str());
    addPeer(ackRoot,target);
    cJSON_AddNumberToObject(ackRoot,"channel",targetBinding->channel);
    cJSON_AddStringToObject(ackRoot,"action",command.action.c_str());
    const bool success=!failure&&(outcome=="ON"||outcome=="OFF");
    cJSON_AddStringToObject(ackRoot,"status",success?"success":"error");
    cJSON_AddStringToObject(ackRoot,"reason",failure?failure:"ok");
    if(!outcome.empty())cJSON_AddStringToObject(ackRoot,"state",outcome.c_str());
    const std::string encoded=kwsEncode(ackRoot);cJSON_Delete(ackRoot);
    m_seen[key]={m_clock()+120000,encoded};
    m_publish("kws_ack/"+origin.subbox_id,encoded);
    cJSON_Delete(root);return true;
}
bool KwsControl::ack(const std::string& payload) {
    cJSON* root=decode(payload);
    if(!root)return false;
    const std::string origin=kwsString(root,"origin_node");
    auto pending=m_pending.find(origin);
    KwsBinding target;
    const bool valid=kwsString(root,"cmd")=="KWS_ACK"&&pending!=m_pending.end()&&pending->second.phase=="remote"&&
        kwsUint(root,"session_id")==pending->second.command.session&&kwsUint(root,"request_id")==pending->second.command.request&&
        payloadPeer(root,target)&&samePeer(target,pending->second.command.binding)&&
        kwsUint(root,"channel")==pending->second.command.binding.channel&&kwsString(root,"action")==pending->second.command.action;
    if(!valid){cJSON_Delete(root);return false;}
    std::string reason=kwsString(root,"reason");
    if(reason.empty()||reason.size()>48)reason="remote_error";
    const std::string state=kwsString(root,"state");
    const bool success=kwsString(root,"status")=="success"&&
        ((pending->second.command.action=="TURN_ON"&&state=="ON")||(pending->second.command.action=="TURN_OFF"&&state=="OFF"));
    Command command=pending->second.command;
    m_pending.erase(pending);
    result(command,success?"success":"error",success?"ok":reason.c_str(),success?state:"");
    cJSON_Delete(root);return true;
}
bool KwsControl::handle(const std::string& topic,const std::string& payload) {
    tick();
    if(payload.empty())return false;
    const std::string commandTopic="home/subbox/"+m_subbox+"/command";
    cJSON* root=decode(payload);
    if(!root)return false;
    const std::string publisher=kwsString(root,"origin_subbox");
    const std::string responder=kwsString(root,"subbox_id");
    const std::string remoteTopic="home/kws/"+publisher+"/"+m_subbox+"/command";
    const std::string ackTopic="home/kws/"+responder+"/"+m_subbox+"/ack";
    const std::string cmd=kwsString(root,"cmd");
    bool handled=false;
    if(cmd=="KWS_CONFIG") {
        handled=topic==commandTopic;
        if(handled)handled=configure(payload,true);
    } else if(kwsString(root,"type")=="kws_playback_done"&&topic.empty()) {
        const uint32_t session=kwsUint(root,"session_id"),request=kwsUint(root,"request_id");
        const std::string origin=kwsString(root,"origin_node");
        auto pending=m_pending.find(origin);
        if(pending!=m_pending.end()&&pending->second.phase=="playback"&&session==m_session&&
            request==pending->second.command.request&&session==pending->second.command.session) {
            // LISTEN_FOLLOWUP and the eventual action each need a fresh request ID:
            // ActionBox caches responses by (session, request), and Gateway dedups
            // results by request. Reusing the incomplete request would collide.
            uint32_t listen_request=++m_request;
            if(!listen_request)listen_request=++m_request;
            Command command=pending->second.command;
            command.request=++m_request;
            if(!command.request)command.request=++m_request;
            pending->second.command=command;
            pending->second.phase="listening";
            pending->second.deadline=m_clock()+LISTEN_TIMEOUT_MS;
            const auto* s=source(origin);
            if(m_listen&&(!s||!m_listen(*s,session,listen_request))) {
                m_pending.erase(pending);
                result(command,"error","listen_unavailable");
            }
            handled=true;
        }
    } else if(cmd=="KWS_REMOTE"&&validId(publisher,"SB")&&topic==remoteTopic) {
        handled=remote(payload);
    } else if(cmd=="KWS_ACK"&&validId(responder,"SB")&&topic==ackTopic) {
        handled=ack(payload);
    }
    cJSON_Delete(root);
    return handled;
}
void KwsControl::tick() {
    const uint64_t now=m_clock();
    for(auto it=m_pending.begin();it!=m_pending.end();) {
        if(it->second.deadline>=now) {++it;continue;}
        const Command command=it->second.command;
        it=m_pending.erase(it);
        result(command,"error","timeout");
    }
    for(auto it=m_seen.begin();it!=m_seen.end();) {
        if(it->second.deadline<now)it=m_seen.erase(it);else ++it;
    }
}
