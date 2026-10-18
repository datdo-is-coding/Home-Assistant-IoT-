#include "espnow_receiver.h"
#include "audio/audio_transport/audio_packet.h"
#include "esp_log.h"

static const char *TAG = "SUBBOX_KWS";

void subbox_espnow_handle_keyword_event(const uint8_t *data, int len) {
    if (!data || len < (int)sizeof(ActionBoxKeywordEventPacket)) return;
    const auto *pkt = reinterpret_cast<const ActionBoxKeywordEventPacket *>(data);
    ESP_LOGI(TAG, "[SUBBOX KWS RECV] ActionBox keyword event: id=%u, conf=%u%%",
             pkt->keyword_id, pkt->confidence_pct);
}
