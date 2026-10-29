# IR catalog

`catalog.json` contains remote recordings from
[Lucaslhm/Flipper-IRDB](https://github.com/Lucaslhm/Flipper-IRDB), CC0-1.0.
Each profile records its source URL and SHA-256 of the original `.ir` file.
The CC0 legal text is included in `LICENSE-CC0.txt`.

This is a small tested-format catalog, not Xiaomi's proprietary database.
A matching brand alone does not establish compatibility. The owner must test
and confirm a profile before saving. Generic A75C filenames do not establish
compatibility with every Japanese Panasonic unit.

The A75C4187 capture uses a short 128-bit button protocol (two 8-byte
sections): power is a toggle, and temperature keys are relative steps. They
must not be labeled absolute ON, OFF or 26 degrees. Known relative frames are
rejected when learning an absolute power or temperature snapshot. Only its
power response was confirmed on the user's appliance.

Full generated climate controls are enabled for checksum-valid Panasonic
216-bit frames (two sections of 8 and 19 bytes). Model-specific seed bytes are
preserved, captured timer flags are disabled, and checksums are recomputed.
For other protocols, the owner can teach separate absolute ON/OFF frames and
individual temperature snapshots; only the taught temperatures are exposed.
The owner must supply a true absolute snapshot, since unknown raw protocols
cannot establish its meaning. These are requested settings, never measured
appliance states. A relative voice request needs a previously sent absolute
temperature, rather than assuming the AC started at 26 degrees.

The prototype currently has only an IR transmitter. Receiver learning stays
disabled until the owner fits a receiver and explicitly enables it in the
app. Firmware support alone does not mean a receiver is installed.

Protocol-layout reference:
[IRremoteESP8266 Panasonic implementation](https://github.com/crankyoldgit/IRremoteESP8266/blob/master/src/ir_Panasonic.cpp)
and [constants](https://github.com/crankyoldgit/IRremoteESP8266/blob/master/src/ir_Panasonic.h).
The small Python codec expresses the protocol independently; no Arduino
runtime or firmware library is embedded. Hardware uses the
[ESP-IDF RMT driver](https://docs.espressif.com/projects/esp-idf/en/v6.0/esp32s3/api-reference/peripherals/rmt.html).

The VS1838B receiver demodulates its carrier, so learned signals are replayed
at 38 kHz; carrier frequency cannot be inferred from its output. Wire timing
uses 10 us units (at most 5 us rounding error). Unsupported/truncated captures
are rejected rather than stored as successful learning.
