# Vietnamese Smart Home NLU Training Dataset
# Bộ Dữ Liệu Huấn Luyện NLU Nhà Thông Minh Tiếng Việt

## Tổng Quan

Bộ dữ liệu JSONL chi tiết cho việc fine-tune model Qwen2.5-3B-Instruct để hiểu lệnh điều khiển nhà thông minh bằng tiếng Việt tự nhiên.

## Thống Kê

| Metric | Base | Augmented |
|--------|------|-----------|
| **Tổng samples** | 266 | **1,534** |
| **Training set** | 239 (90%) | **1,380** (90%) |
| **Validation set** | 27 (10%) | **154** (10%) |
| **File size** | 405 KB | **2,301 KB** |

## Cấu Trúc File

```
training_data/
├── generate_dataset.py              # Script tạo base dataset
├── augment_dataset.py               # Script augmentation (5.8x)
├── smarthome_vi_nlu_full.jsonl      # Base dataset (266 samples)
├── smarthome_vi_nlu_train.jsonl     # Base train split
├── smarthome_vi_nlu_val.jsonl       # Base val split
├── smarthome_vi_nlu_augmented.jsonl          # ★ AUGMENTED (1,534 samples)
├── smarthome_vi_nlu_augmented_train.jsonl    # ★ Augmented train
└── smarthome_vi_nlu_augmented_val.jsonl      # ★ Augmented val
```

## Categories Covered (16 loại)

1. **Basic ON/OFF - Đèn** (36 biến thể bật + 19 biến thể tắt)
2. **Basic ON/OFF - Quạt** (22 biến thể)
3. **Basic ON/OFF - Thiết bị khác** (điều hòa, rèm, bơm, bình nóng lạnh, cửa cuốn, giàn phơi, hút mùi, tivi, nồi cơm)
4. **Temperature / Value** (nhiệt độ số + chữ: 16-30 độ)
5. **Ambiguous** (thiếu phòng, thiếu thiết bị, thiếu cả hai)
6. **ASR Error Resilient** (bạn bè→bật đèn, bất quá→bật quạt, bật điên→bật đèn, ...)
7. **Regional Dialects** (Bắc: giúp tôi / Trung: nờ, nè / Nam: dùm, giùm)
8. **Casual/Slang** (ê, tao, cho tao, ơi, ...)
9. **Natural Context** (trời tối, nóng quá, đi ngủ, về nhà, mưa, ...)
10. **Synonyms** (mở=bật, đóng=tắt, khởi động, ngắt, dừng, on/off)
11. **Inverted Word Order** (đèn phòng khách bật lên, phòng ngủ tắt quạt)
12. **Polite/Formal** (làm ơn, xin vui lòng, phiền bạn)
13. **Edge Cases** (filler words, repeated words, nhé/nha/ạ suffix, question form)
14. **Room×Device Matrix** (9 phòng × 2 thiết bị × 2 hành động = 36 systematic combos)
15. **Vietnamese Number Words** (mười sáu, hai mươi lăm, hai bốn, ...)
16. **Real-world ASR Errors** (phong→phòng, tất→tắt, đen→đèn, words run together)

## Augmentation Methods

- **Prefix augmentation**: ê, nè, ơi, cho tôi, giúp tôi, làm ơn, ...
- **Suffix augmentation**: đi, nhé, nha, dùm, giùm, hộ, ạ, được không, ...
- **Context sentences**: trời tối rồi, nóng quá, đi ngủ thôi, về nhà rồi, ...
- **ASR noise injection**: Random diacritical errors to simulate real misrecognition

## Format (OpenAI Messages / ChatML)

```json
{
  "messages": [
    {"role": "system", "content": "<system prompt>"},
    {"role": "user", "content": "bật đèn phòng khách"},
    {"role": "assistant", "content": "{\"voice_reply\":\"Đã bật đèn ở phòng khách ạ.\",\"command\":{\"action\":\"turn_on\",\"device\":\"light\",\"location\":\"phong_khach\",\"value\":null}}"}
  ]
}
```

## Cách Fine-tune

### Option 1: llama.cpp (trên Pi 4 / máy local)
```bash
# Convert GGUF to training format
python convert_to_lora.py smarthome_vi_nlu_augmented_train.jsonl

# Fine-tune with LoRA
./llama-finetune \
  --model-base qwen2.5-3b-instruct-q4_k_m.gguf \
  --train-data smarthome_vi_nlu_augmented_train.jsonl \
  --lora-out smarthome-vi-lora.gguf \
  --epochs 3 \
  --batch-size 4 \
  --learning-rate 1e-4
```

### Option 2: Hugging Face + Unsloth (trên Google Colab / GPU)
```python
from unsloth import FastLanguageModel
from trl import SFTTrainer

model, tokenizer = FastLanguageModel.from_pretrained(
    "Qwen/Qwen2.5-3B-Instruct", max_seq_length=512, load_in_4bit=True
)
model = FastLanguageModel.get_peft_model(model, r=16, lora_alpha=16)

trainer = SFTTrainer(
    model=model,
    train_dataset=train_dataset,
    eval_dataset=val_dataset,
    max_seq_length=512,
    num_train_epochs=3,
    per_device_train_batch_size=4,
    learning_rate=2e-4,
)
trainer.train()
model.save_pretrained_gguf("smarthome-vi-qwen3b", tokenizer, quantization_method="q4_k_m")
```

## Device Coverage

| Device ID | Tên Việt | Samples |
|-----------|----------|---------|
| light | đèn | 644 |
| fan | quạt | 378 |
| air_conditioner | điều hòa | 241 |
| curtain | rèm | 38 |
| pump | máy bơm | 36 |
| cua_cuon | cửa cuốn | 22 |
| quat_tran | quạt trần | 20 |
| binh_nong_lanh | bình nóng lạnh | 18 |
| may_hut_mui | máy hút mùi | 18 |
| gian_phoi | giàn phơi | 17 |

## Room Coverage

| Room ID | Tên Việt | Samples |
|---------|----------|---------|
| phong_khach | phòng khách | 25.9% |
| phong_ngu | phòng ngủ | 19.9% |
| phong_bep | phòng bếp | 8.6% |
| san_vuon | sân vườn | 4.9% |
| gara | gara | 3.8% |
| phong_tam | phòng tắm | 3.4% |
| ban_cong | ban công | 3.0% |
| phong_lam_viec | phòng làm việc | 3.0% |
| hanh_lang | hành lang | 2.3% |
| null (ambiguous) | không nêu rõ | 21.8% |
