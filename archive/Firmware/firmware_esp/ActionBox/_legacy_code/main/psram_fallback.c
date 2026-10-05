/*
 * psram_fallback.c
 * Transparently redirects allocations to MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT
 * when physical PSRAM is absent on ESP32-S3 (PKG: 0).
 */

#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "esp_heap_caps.h"
#include "esp_log.h"

static const char *TAG = "PSRAM_SHIM";

extern void *__real_heap_caps_calloc(size_t n, size_t size, uint32_t caps);
extern void *__real_heap_caps_malloc(size_t size, uint32_t caps);
extern void *__real_heap_caps_realloc(void *ptr, size_t size, uint32_t caps);
extern void *__real_malloc(size_t size);
extern void *__real_calloc(size_t n, size_t size);

void *__wrap_heap_caps_calloc(size_t n, size_t size, uint32_t caps)
{
    void *ptr = __real_heap_caps_calloc(n, size, caps);
    if (!ptr && (caps & MALLOC_CAP_SPIRAM)) {
        ptr = __real_heap_caps_calloc(n, size, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    }
    return ptr;
}

void *__wrap_heap_caps_malloc(size_t size, uint32_t caps)
{
    void *ptr = __real_heap_caps_malloc(size, caps);
    if (!ptr && (caps & MALLOC_CAP_SPIRAM)) {
        ptr = __real_heap_caps_malloc(size, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    }
    return ptr;
}

void *__wrap_heap_caps_realloc(void *ptr, size_t size, uint32_t caps)
{
    void *res = __real_heap_caps_realloc(ptr, size, caps);
    if (!res && (caps & MALLOC_CAP_SPIRAM)) {
        res = __real_heap_caps_realloc(ptr, size, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    }
    return res;
}

void *__wrap_malloc(size_t size)
{
    void *ptr = __real_malloc(size);
    if (!ptr) {
        ptr = __real_heap_caps_malloc(size, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    }
    return ptr;
}

void *__wrap_calloc(size_t n, size_t size)
{
    void *ptr = __real_calloc(n, size);
    if (!ptr) {
        ptr = __real_heap_caps_calloc(n, size, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    }
    return ptr;
}

/* Deep learning library: dl_lib_calloc & dl_lib_calloc_psram implementation */
void *__wrap_dl_lib_calloc(size_t n, size_t size, size_t align)
{
    size_t total_size = n * size + align + 4;
    void *raw = __real_heap_caps_malloc(total_size, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    if (!raw) {
        ESP_LOGE(TAG, "dl_lib_calloc failed to alloc %u bytes (free heap=%u KB)",
                 (unsigned)total_size,
                 (unsigned)(heap_caps_get_free_size(MALLOC_CAP_INTERNAL) / 1024));
        return NULL;
    }
    uintptr_t p = (uintptr_t)raw + 4;
    if (align > 1) {
        p = (p + align - 1) & ~(align - 1);
    }
    *((void **)(p - 4)) = raw;
    memset((void *)p, 0, n * size);
    return (void *)p;
}

void *__wrap_dl_lib_calloc_psram(size_t n, size_t size, size_t align)
{
    return __wrap_dl_lib_calloc(n, size, align);
}
