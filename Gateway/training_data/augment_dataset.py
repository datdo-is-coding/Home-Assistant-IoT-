# -*- coding: utf-8 -*-
"""
Vietnamese Smart Home NLU Data Augmentation
=============================================
Takes the base dataset (266 samples) and augments it to ~1500+ samples through:
1. Prefix augmentation (thêm các từ mở đầu tự nhiên)
2. Suffix augmentation (thêm các từ kết thúc tự nhiên)
3. Noise injection (mô phỏng lỗi ASR thực tế)
4. Paraphrase templates
5. Context sentences (thêm ngữ cảnh tự nhiên)
"""

import json
import os
import random
import sys
import re
import copy

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ─── Augmentation Templates ────────────────────────────────────────

PREFIXES = [
    "", "ê ", "nè ", "ơi ", "này ", "ok ",
    "hey ", "hi ", "oi ", "à ", "ừm ",
    "cho tôi ", "giúp tôi ", "giùm tui ",
    "làm ơn ", "xin ", "vui lòng ",
    "nhờ bạn ", "phiền bạn ",
]

SUFFIXES = [
    "", " đi", " giúp tôi", " với", " nhé", " nha",
    " cái", " giùm", " hộ", " luôn đi", " ngay đi",
    " cho tao", " cho tui", " dùm", " ạ",
    " được không", " được chứ",
]

CONTEXT_PREFIXES = [
    "",
    "trời tối rồi ",
    "nóng quá ",
    "lạnh quá ",
    "sáng rồi ",
    "đi ngủ thôi ",
    "dậy rồi ",
    "về nhà rồi ",
    "đi làm ",
    "mưa rồi ",
    "trời nắng quá ",
    "buồn ngủ quá ",
    "tối thui rồi ",
    "chẳng thấy gì ",
    "khách sắp tới ",
    "chuẩn bị ăn cơm ",
    "sắp tắm ",
    "sắp đi ",
    "ngồi xem tivi ",
]

# Common ASR noise patterns to inject
ASR_NOISE_PATTERNS = [
    # Vietnamese diacritical errors (random missing/wrong diacritics)
    ("ắ", "a"), ("ật", "at"), ("ạt", "at"),
    ("è", "e"), ("ền", "en"), ("ẹn", "en"),
    ("ủ", "u"), ("ộ", "o"),
    ("ò", "o"), ("ấ", "a"),
]


def augment_prefix_suffix(sample, prefixes=PREFIXES, suffixes=SUFFIXES):
    """Generate new samples with different prefixes and suffixes."""
    augmented = []
    original_text = sample["messages"][1]["content"]
    output = sample["messages"][2]["content"]

    for prefix in random.sample(prefixes, min(3, len(prefixes))):
        for suffix in random.sample(suffixes, min(2, len(suffixes))):
            new_text = f"{prefix}{original_text}{suffix}".strip()
            if new_text != original_text:
                new_sample = copy.deepcopy(sample)
                new_sample["messages"][1]["content"] = new_text
                augmented.append(new_sample)

    return augmented


def augment_context(sample, contexts=CONTEXT_PREFIXES):
    """Add natural context sentences before the command."""
    augmented = []
    original_text = sample["messages"][1]["content"]
    output = sample["messages"][2]["content"]

    for ctx in random.sample(contexts, min(3, len(contexts))):
        if ctx:
            new_text = f"{ctx}{original_text}"
            new_sample = copy.deepcopy(sample)
            new_sample["messages"][1]["content"] = new_text
            augmented.append(new_sample)

    return augmented


def augment_asr_noise(sample, noise_rate=0.15):
    """Inject random ASR-like noise into the user text."""
    original_text = sample["messages"][1]["content"]

    # Only augment some characters
    new_text = original_text
    for correct, noisy in random.sample(ASR_NOISE_PATTERNS, min(2, len(ASR_NOISE_PATTERNS))):
        if correct in new_text and random.random() < noise_rate:
            new_text = new_text.replace(correct, noisy, 1)

    if new_text != original_text:
        new_sample = copy.deepcopy(sample)
        new_sample["messages"][1]["content"] = new_text
        return [new_sample]
    return []


def main():
    base_dir = os.path.dirname(__file__)
    input_path = os.path.join(base_dir, "smarthome_vi_nlu_full.jsonl")
    output_path = os.path.join(base_dir, "smarthome_vi_nlu_augmented.jsonl")

    # Load base dataset
    base_samples = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                base_samples.append(json.loads(line))

    print(f"Base dataset: {len(base_samples)} samples")

    # Augment
    all_samples = list(base_samples)  # Keep originals
    seen_texts = set(s["messages"][1]["content"] for s in base_samples)

    random.seed(42)

    for sample in base_samples:
        # 1. Prefix/Suffix augmentation (selective, not every sample)
        if random.random() < 0.6:
            for aug in augment_prefix_suffix(sample):
                text = aug["messages"][1]["content"]
                if text not in seen_texts:
                    all_samples.append(aug)
                    seen_texts.add(text)

        # 2. Context augmentation (selective)
        if random.random() < 0.4:
            for aug in augment_context(sample):
                text = aug["messages"][1]["content"]
                if text not in seen_texts:
                    all_samples.append(aug)
                    seen_texts.add(text)

        # 3. ASR noise injection (selective)
        if random.random() < 0.3:
            for aug in augment_asr_noise(sample):
                text = aug["messages"][1]["content"]
                if text not in seen_texts:
                    all_samples.append(aug)
                    seen_texts.add(text)

    # Shuffle
    random.shuffle(all_samples)

    # Write augmented dataset
    with open(output_path, "w", encoding="utf-8") as f:
        for s in all_samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    # Split: 90% train, 10% val
    split_idx = int(len(all_samples) * 0.9)
    train = all_samples[:split_idx]
    val = all_samples[split_idx:]

    train_path = os.path.join(base_dir, "smarthome_vi_nlu_augmented_train.jsonl")
    with open(train_path, "w", encoding="utf-8") as f:
        for s in train:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    val_path = os.path.join(base_dir, "smarthome_vi_nlu_augmented_val.jsonl")
    with open(val_path, "w", encoding="utf-8") as f:
        for s in val:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    # Stats
    print("=" * 70)
    print("  AUGMENTED VIETNAMESE SMART HOME NLU DATASET")
    print("=" * 70)
    print(f"  Base samples:       {len(base_samples)}")
    print(f"  Augmented total:    {len(all_samples)} ({len(all_samples)/len(base_samples):.1f}x)")
    print(f"  Training set:       {len(train)} (90%)")
    print(f"  Validation set:     {len(val)} (10%)")
    print(f"\n  Augmented dataset:  {os.path.abspath(output_path)}")
    print(f"  Training split:     {os.path.abspath(train_path)}")
    print(f"  Validation split:   {os.path.abspath(val_path)}")
    print(f"  File size:          {os.path.getsize(output_path)/1024:.0f} KB")

    # Distribution
    actions = {}
    devices = {}
    for s in all_samples:
        msg = json.loads(s["messages"][2]["content"])
        cmd = msg.get("command", {})
        a = cmd.get("action", "?")
        d = cmd.get("device") or "null"
        actions[a] = actions.get(a, 0) + 1
        devices[d] = devices.get(d, 0) + 1

    print("\n  -- Action Distribution --")
    for k, v in sorted(actions.items(), key=lambda x: -x[1]):
        print(f"    {k:20s} {v:4d} ({v/len(all_samples)*100:5.1f}%)")

    print("\n  -- Top Devices --")
    for k, v in sorted(devices.items(), key=lambda x: -x[1])[:10]:
        print(f"    {k:20s} {v:4d} ({v/len(all_samples)*100:5.1f}%)")

    print("\n  -- Sample Augmented Examples --")
    for i in range(min(8, len(all_samples))):
        user_msg = all_samples[i]["messages"][1]["content"]
        print(f"    [{i+1}] {user_msg}")

    print("\n" + "=" * 70)
    print("  AUGMENTATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
