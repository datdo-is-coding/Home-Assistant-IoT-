#pragma once

#include <stdint.h>
#include <stddef.h>

class VADInterface {
public:
    virtual ~VADInterface() = default;

    virtual bool process(const int16_t* pcm, size_t count) = 0;

    virtual bool speechStarted() const = 0;

    virtual bool speechEnded() const = 0;

    virtual bool isSpeaking() const = 0;

    virtual int64_t getEnergy() const = 0;

    virtual void reset() = 0;
};
