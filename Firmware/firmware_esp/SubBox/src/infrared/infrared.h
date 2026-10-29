#pragma once
#include <stdint.h>
#include <stddef.h>
#include "cJSON.h"

using IrReply = bool (*)(void*, const char*, size_t);
bool infrared_bind(void* owner, IrReply reply);
void infrared_session(void* owner, uint32_t generation);
void infrared_unbind(void* owner);
void infrared_submit(void* owner, uint32_t generation, const cJSON* message);
