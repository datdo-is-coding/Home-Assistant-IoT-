#include "audio/kws/kws_control.h"
#include <cassert>
#include <functional>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

namespace {
bool contains(const std::string& text, const char* needle) {
    return text.find(needle) != std::string::npos;
}

std::string editJson(const std::string& json, const char* key, int value) {
    cJSON* root = cJSON_Parse(json.c_str());
    assert(root);
    cJSON_DeleteItemFromObjectCaseSensitive(root, key);
    cJSON_AddNumberToObject(root, key, value);
    const std::string out = kwsEncode(root);
    cJSON_Delete(root);
    return out;
}

std::string replaceText(std::string text, const std::string& from, const std::string& to) {
    const size_t position = text.find(from);
    assert(position != std::string::npos);
    text.replace(position, from.size(), to);
    return text;
}
}

int main() {
    std::vector<std::string> events;
    std::vector<std::string> config_acks;
    std::vector<std::string> sent_commands;
    std::vector<std::string> remote_payloads;
    std::vector<std::string> remote_acks;
    unsigned calls = 0;
    unsigned remote_calls = 0;
    std::string saved;
    uint64_t now = 100;
    uint64_t wall = 1700000000;
    bool route_remote = true;
    bool remote_trusted = true;
    std::unique_ptr<KwsControl> remote_control;

    std::function<bool(const KwsPeer&, const std::string&, std::string&)> send =
        [&](const KwsPeer&, const std::string& command, std::string& ack) {
            ++calls;
            sent_commands.push_back(command);
            cJSON* root = cJSON_Parse(command.c_str());
            assert(root);
            cJSON_AddStringToObject(root, "status", "OK");
            cJSON_AddStringToObject(root, "state", kwsString(root, "cmd") == "TURN_ON" ? "ON" : "OFF");
            ack = kwsEncode(root);
            cJSON_Delete(root);
            return true;
        };
    std::function<bool(const KwsPeer&, uint32_t, uint32_t)> listen =
        [&](const KwsPeer& peer, uint32_t session, uint32_t request) {
            cJSON* root = cJSON_CreateObject();
            cJSON_AddStringToObject(root, "node_id", peer.node_id.c_str());
            cJSON_AddStringToObject(root, "subbox_id", peer.subbox_id.c_str());
            cJSON_AddStringToObject(root, "hardware_uid", peer.hardware_uid.c_str());
            cJSON_AddNumberToObject(root, "config_version", peer.config_version);
            cJSON_AddNumberToObject(root, "owner_epoch", peer.owner_epoch);
            cJSON_AddNumberToObject(root, "protocol_version", 3);
            cJSON_AddNumberToObject(root, "session_id", session);
            cJSON_AddNumberToObject(root, "request_id", request);
            cJSON_AddStringToObject(root, "cmd", "LISTEN_FOLLOWUP");
            const std::string command = kwsEncode(root);
            cJSON_Delete(root);
            std::string ack;
            return send(peer, command, ack);
        };

    const auto publish = [&](const std::string& kind, const std::string& data) {
        if (kind == "kws_result") {
            events.push_back(kind + ":" + data);
            return true;
        }
        if (kind == "kws_config") {
            config_acks.push_back(data);
            return true;
        }
        const std::string command_prefix = "kws_command/";
        if (kind.rfind(command_prefix, 0) == 0) {
            remote_payloads.push_back(data);
            if (route_remote && remote_control) {
                return remote_control->handle("home/kws/SB111111111111/SB333333333333/command", data);
            }
            return true;
        }
        return false;
    };

    KwsControl control("SB111111111111", 71, publish,
        [&](const KwsPeer& peer) {
            return peer.node_id == "AB222222222222" && peer.subbox_id == "SB111111111111";
        },
        send,
        [&](const std::string& json) { saved = json; return true; },
        [&] { return now; },
        listen,
        {},
        [&] { return wall; });

    const std::string config = R"({"cmd":"KWS_CONFIG","revision":1,"sources":[{"node_id":"AB222222222222","subbox_id":"SB111111111111","room":"BEDROOM","hardware_uid":"222222222222","config_version":4,"owner_epoch":1}],"bindings":[{"room":"BEDROOM","device":"LIGHT","node_id":"AB222222222222","subbox_id":"SB111111111111","channel":3,"hardware_uid":"222222222222","config_version":4,"owner_epoch":1}]})";
    assert(control.handle("home/subbox/SB111111111111/command", config));
    assert(!saved.empty());
    assert(config_acks.size() == 1 && contains(config_acks.back(), "\"status\":\"applied\""));
    const std::string saved_v1 = saved;

    control.utterance("AB222222222222", "bật đèn");
    assert(calls == 1 && contains(events.back(), "\"status\":\"success\""));
    assert(contains(events.back(), "\"channel\":3"));
    control.utterance("AB333333333333", "bật đèn");
    assert(calls == 1);
    control.utterance("AB222222222222", "bật quạt");
    assert(calls == 1);
    control.utterance("AB222222222222", "bật đèn phòng");
    assert(calls == 1);
    assert(contains(events.back(), "missing_room"));
    now += 30001;
    control.tick();
    assert(contains(events.back(), "timeout"));
    control.utterance("AB222222222222", "bật tắt đèn");
    assert(calls == 1);
    assert(contains(events.back(), "invalid_command"));
    control.utterance("AB222222222222", "bật");
    assert(contains(events.back(), "\"follow_up\":true"));
    cJSON* result = cJSON_Parse(events.back().substr(events.back().find(':') + 1).c_str());
    const unsigned request = kwsUint(result, "request_id");
    cJSON_Delete(result);
    assert(control.handle("", std::string("{\"type\":\"kws_playback_done\",\"session_id\":71,\"request_id\":") +
        std::to_string(request) + ",\"origin_node\":\"AB222222222222\"}"));
    assert(calls == 2);
    cJSON* listen_command = cJSON_Parse(sent_commands.back().c_str());
    assert(listen_command);
    assert(kwsString(listen_command, "cmd") == "LISTEN_FOLLOWUP");
    const unsigned listen_request = kwsUint(listen_command, "request_id");
    cJSON_Delete(listen_command);
    assert(listen_request != 0 && listen_request != request);
    control.utterance("AB222222222222", "đèn");
    assert(calls == 3);
    assert(contains(events.back(), "\"follow_up\":false"));
    assert(contains(events.back(), "\"status\":\"success\""));
    cJSON* final_result = cJSON_Parse(events.back().substr(events.back().find(':') + 1).c_str());
    assert(final_result);
    const unsigned final_request = kwsUint(final_result, "request_id");
    cJSON_Delete(final_result);
    assert(final_request != 0 && final_request != request && final_request != listen_request);

    // Replaying the active revision is idempotent; stale or changed snapshots are rejected.
    assert(control.handle("home/subbox/SB111111111111/command", config));
    assert(saved == saved_v1);
    assert(!control.handle("home/subbox/SB111111111111/command",
        replaceText(config, "\"channel\":3", "\"channel\":2")));
    assert(!control.handle("home/subbox/SB111111111111/command",
        replaceText(config, "\"revision\":1", "\"revision\":0")));
    assert(saved == saved_v1);

    const std::string config_v2 = R"({"cmd":"KWS_CONFIG","revision":2,"sources":[{"node_id":"AB222222222222","subbox_id":"SB111111111111","room":"BEDROOM","hardware_uid":"222222222222","config_version":4,"owner_epoch":1},{"node_id":"AB444444444444","subbox_id":"SB333333333333","room":"KITCHEN","hardware_uid":"444444444444","config_version":7,"owner_epoch":2}],"bindings":[{"room":"BEDROOM","device":"LIGHT","node_id":"AB222222222222","subbox_id":"SB111111111111","channel":3,"hardware_uid":"222222222222","config_version":4,"owner_epoch":1},{"room":"KITCHEN","device":"FAN","node_id":"AB444444444444","subbox_id":"SB333333333333","channel":2,"hardware_uid":"444444444444","config_version":7,"owner_epoch":2}]})";

    remote_control = std::make_unique<KwsControl>("SB333333333333", 72,
        [&](const std::string& kind, const std::string& data) {
            if (kind.rfind("kws_ack/SB111111111111", 0) == 0) remote_acks.push_back(data);
            return true;
        },
        [&](const KwsPeer& peer) {
            return remote_trusted && peer.node_id == "AB444444444444" &&
                peer.subbox_id == "SB333333333333";
        },
        [&](const KwsPeer& peer, const std::string& command, std::string& ack) {
            ++remote_calls;
            cJSON* root = cJSON_Parse(command.c_str());
            assert(root);
            cJSON_AddStringToObject(root, "status", "OK");
            cJSON_AddStringToObject(root, "state", kwsString(root, "cmd") == "TURN_ON" ? "ON" : "OFF");
            ack = kwsEncode(root);
            cJSON_Delete(root);
            assert(peer.node_id == "AB444444444444");
            return true;
        },
        [](const std::string&) { return true; },
        [&] { return now; },
        KwsControl::Listen{}, KwsControl::Feedback{},
        [&] { return wall; });

    assert(control.handle("home/subbox/SB111111111111/command", config_v2));
    assert(saved != saved_v1);
    assert(remote_control->handle("home/subbox/SB333333333333/command", config_v2));

    // A command owned by another SubBox is published and its success is only reported after a matching ACK.
    control.utterance("AB222222222222", "bật quạt bếp");
    assert(calls == 3);
    assert(remote_payloads.size() == 1);
    assert(remote_calls == 1 && remote_acks.size() == 1);
    assert(contains(remote_acks.back(), "\"status\":\"success\""));
    assert(contains(remote_acks.back(), "\"channel\":2"));
    assert(control.handle("home/kws/SB333333333333/SB111111111111/ack", remote_acks.back()));
    assert(contains(events.back(), "\"status\":\"success\""));
    assert(contains(events.back(), "\"target_node\":\"AB444444444444\""));
    assert(contains(events.back(), "\"target_subbox\":\"SB333333333333\""));
    assert(contains(events.back(), "\"channel\":2"));
    const std::string first_remote = remote_payloads.back();
    const std::string first_remote_ack = remote_acks.back();

    // Publisher identity comes from the ACL-bound topic, never from JSON alone.
    assert(!remote_control->handle("home/kws/SB555555555555/SB333333333333/command", first_remote));
    assert(!remote_control->handle("home/subbox/SB333333333333/kws/command", first_remote));
    assert(remote_calls == 1);

    // A replay inside the dedup window returns the cached ACK without touching the relay again.
    assert(remote_control->handle("home/kws/SB111111111111/SB333333333333/command", first_remote));
    assert(remote_calls == 1);
    assert(remote_acks.size() == 2 && remote_acks.back() == first_remote_ack);
    assert(!control.handle("home/kws/SB333333333333/SB111111111111/ack", remote_acks.back()));

    // A remote target cannot execute a payload addressed at the wrong SubBox.
    assert(!control.handle("home/kws/SB111111111111/SB333333333333/command", first_remote));
    assert(remote_calls == 1);
    assert(!remote_control->handle("home/kws/SB333333333333/SB111111111111/command", first_remote));

    // Wrong/stale ACKs cannot clear the pending request; the correct one still can.
    control.utterance("AB222222222222", "tắt quạt bếp");
    assert(remote_calls == 2 && remote_acks.size() == 3);
    const std::string valid_ack = remote_acks.back();
    cJSON* valid_json = cJSON_Parse(valid_ack.c_str());
    assert(valid_json);
    const int valid_request = static_cast<int>(kwsUint(valid_json, "request_id"));
    cJSON_Delete(valid_json);
    const std::string wrong_ack = editJson(valid_ack, "request_id", valid_request + 1);
    assert(!control.handle("home/kws/SB333333333333/SB111111111111/ack", wrong_ack));
    assert(!control.handle("home/kws/SB333333333333/SB111111111111/ack", editJson(valid_ack, "channel", 1)));
    assert(!control.handle("home/kws/SB555555555555/SB111111111111/ack", valid_ack));
    assert(!control.handle("home/subbox/SB111111111111/kws/ack", valid_ack));
    assert(control.handle("home/kws/SB333333333333/SB111111111111/ack", valid_ack));
    assert(contains(events.back(), "\"status\":\"success\"") &&
        contains(events.back(), "\"state\":\"OFF\""));

    // An expired request is rejected by the destination with a structured error ACK.
    remote_acks.clear();
    route_remote = false;
    const uint64_t issued_wall = wall;
    control.utterance("AB222222222222", "bật quạt bếp");
    assert(remote_payloads.size() == 3);
    route_remote = true;
    wall = issued_wall + 6;
    assert(remote_control->handle("home/kws/SB111111111111/SB333333333333/command", remote_payloads.back()));
    assert(remote_calls == 2);
    assert(remote_acks.size() == 1 && contains(remote_acks.back(), "expired_request"));
    assert(control.handle("home/kws/SB333333333333/SB111111111111/ack", remote_acks.back()));
    assert(contains(events.back(), "\"status\":\"error\"") &&
        contains(events.back(), "expired_request"));
    wall = issued_wall;

    // A remote request that never gets an ACK fails closed after the short timeout.
    route_remote = false;
    control.utterance("AB222222222222", "bật quạt bếp");
    now += 5001;
    control.tick();
    assert(contains(events.back(), "timeout"));
    route_remote = true;

    // Untrusted origin/target identity cannot execute even with a valid revision.
    const std::string untrusted = replaceText(remote_payloads.back(),
        "\"origin_node_id\":\"AB222222222222\"", "\"origin_node_id\":\"AB555555555555\"");
    assert(!remote_control->handle("home/kws/SB111111111111/SB333333333333/command", untrusted));
    assert(remote_calls == 2);

    // Deadlines apply at the message boundary even before the worker's next tick.
    route_remote = true;
    control.utterance("AB222222222222", "bật quạt bếp");
    const std::string late_ack = remote_acks.back();
    now += 5001;
    assert(!control.handle("home/kws/SB333333333333/SB111111111111/ack", late_ack));
    assert(contains(events.back(), "timeout"));
    control.utterance("AB222222222222", "bật");
    cJSON* question = cJSON_Parse(events.back().substr(events.back().find(':') + 1).c_str());
    const unsigned question_request = kwsUint(question, "request_id");
    cJSON_Delete(question);
    const unsigned before_listen = calls;
    now += 20001;
    assert(!control.handle("", std::string("{\"type\":\"kws_playback_done\",\"session_id\":71,\"request_id\":") +
        std::to_string(question_request) + ",\"origin_node\":\"AB222222222222\"}"));
    assert(calls == before_listen);

    // A fresh controller restores its persisted binding with the broker absent.
    KwsControl rebooted("SB111111111111", 99,
        [](const std::string&, const std::string&) { return false; },
        [](const KwsPeer& peer) { return peer.node_id == "AB222222222222" && peer.owner_epoch == 1; },
        send, [](const std::string&) { return false; }, [&] { return now; });
    assert(rebooted.restore(saved_v1));
    const unsigned before_offline = calls;
    rebooted.utterance("AB222222222222", "bật đèn");
    assert(calls == before_offline + 1 && contains(sent_commands.back(), "\"channel\":3"));

    // Cache pressure must not evict a still-valid request and actuate its replay.
    const unsigned before_pressure = remote_calls;
    for (int id=1000; id<1070; ++id)
        remote_control->handle("home/kws/SB111111111111/SB333333333333/command", editJson(first_remote, "request_id", id));
    assert(remote_calls - before_pressure <= 64);
    const unsigned after_pressure = remote_calls;
    remote_control->handle("home/kws/SB111111111111/SB333333333333/command", first_remote);
    assert(remote_calls == after_pressure);

    std::cout << "kws control checks passed\n";
}
