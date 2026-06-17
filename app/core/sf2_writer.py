"""Pure-Python SoundFont 2.01 (RIFF/sfbk) writer.

Builds valid .sf2 files from WAV samples with key-range mapping,
loop points, and ADSR envelope generators. No external dependencies
beyond numpy (already in requirements).

SF2 spec reference: SoundFont Technical Specification 2.01 (Creative/E-mu).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf


class SF2WriteError(Exception):
    pass


# SF2 generator opcodes (subset used for key range, vel range, ADSR, sample)
GEN_KEY_RANGE = 43
GEN_VEL_RANGE = 44
GEN_ATTACK_VOL_ENV = 34
GEN_DECAY_VOL_ENV = 36
GEN_SUSTAIN_VOL_ENV = 37
GEN_RELEASE_VOL_ENV = 38
GEN_SAMPLE_ID = 53
GEN_SAMPLE_MODES = 54
GEN_OVERRIDING_ROOT_KEY = 58
GEN_INSTRUMENT = 41

SAMPLE_LINK_MONO = 1
SAMPLE_LOOP_CONTINUOUSLY = 1
SAMPLE_NO_LOOP = 0

# 46 zero samples appended after each sample (SF2 spec requirement)
SAMPLE_PAD = 46

MAX_SAMPLE_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB per sample


@dataclass
class SF2Sample:
    name: str
    data: np.ndarray  # mono int16
    sample_rate: int = 44100
    original_pitch: int = 60  # MIDI note the sample was recorded at
    pitch_correction: int = 0  # cents
    loop_start: int = 0
    loop_end: int = 0  # 0 = no loop (set to len-1 for full-sample loop)
    loop_enabled: bool = False

    def __post_init__(self) -> None:
        if self.data.ndim != 1:
            raise SF2WriteError(f"Sample '{self.name}' must be mono (1D array)")
        if self.data.dtype != np.int16:
            self.data = (np.clip(self.data.astype(np.float64), -1.0, 1.0) * 32767).astype(np.int16)
        sample_bytes = self.data.nbytes
        if sample_bytes > MAX_SAMPLE_SIZE_BYTES:
            raise SF2WriteError(
                f"Sample '{self.name}' is too large ({sample_bytes / (1024 * 1024):.0f} MB). "
                f"Maximum is {MAX_SAMPLE_SIZE_BYTES / (1024 * 1024):.0f} MB."
            )
        if self.loop_end == 0 and self.loop_enabled:
            self.loop_end = len(self.data) - 1


@dataclass
class SF2Zone:
    sample_index: int
    key_lo: int = 0
    key_hi: int = 127
    vel_lo: int = 0
    vel_hi: int = 127
    root_key: int = -1  # -1 = use sample's original_pitch
    attack_ms: float = 0.0
    decay_ms: float = 0.0
    sustain_pct: float = 100.0  # 0-100, where 0 = full sustain, 100 = silent
    release_ms: float = 0.0
    loop_mode: int = -1  # -1 = auto from sample


@dataclass
class SF2Preset:
    name: str
    preset_number: int = 0
    bank: int = 0
    zones: list[SF2Zone] = field(default_factory=list)


@dataclass
class SF2Bank:
    name: str = "Tunerize SoundFont"
    samples: list[SF2Sample] = field(default_factory=list)
    presets: list[SF2Preset] = field(default_factory=list)

    def add_sample(self, sample: SF2Sample) -> int:
        idx = len(self.samples)
        self.samples.append(sample)
        return idx

    def add_preset(self, preset: SF2Preset) -> None:
        self.presets.append(preset)


def load_wav_as_sample(
    wav_path: Path,
    name: str | None = None,
    original_pitch: int = 60,
    loop_start: int = 0,
    loop_end: int = 0,
    loop_enabled: bool = False,
) -> SF2Sample:
    """Load a WAV file and return an SF2Sample."""
    data, sr = sf.read(str(wav_path), dtype="int16", always_2d=False)
    if data.ndim == 2:
        data = data.mean(axis=1).astype(np.int16)
    return SF2Sample(
        name=name or wav_path.stem[:20],
        data=data,
        sample_rate=sr,
        original_pitch=original_pitch,
        loop_start=loop_start,
        loop_end=loop_end,
        loop_enabled=loop_enabled,
    )


def _timecents(ms: float) -> int:
    """Convert milliseconds to SF2 timecents (1200 * log2(seconds))."""
    if ms <= 0:
        return -32768  # instant
    seconds = ms / 1000.0
    import math
    tc = int(round(1200.0 * math.log2(seconds)))
    return max(-32768, min(32767, tc))


def _sustain_cb(pct: float) -> int:
    """Convert sustain percentage (0=full, 100=silent) to centibels."""
    return max(0, min(1440, int(round(pct * 10))))


def write_sf2(bank: SF2Bank, output_path: Path) -> Path:
    """Write an SF2Bank to a .sf2 file. Returns the output path."""
    if not bank.samples:
        raise SF2WriteError("Cannot write an SF2 with no samples.")
    if not bank.presets:
        raise SF2WriteError("Cannot write an SF2 with no presets.")

    info_chunk = _build_info(bank.name)
    sdta_chunk = _build_sdta(bank.samples)
    pdta_chunk = _build_pdta(bank)

    sfbk_body = info_chunk + sdta_chunk + pdta_chunk
    riff = b"RIFF" + struct.pack("<I", len(sfbk_body) + 4) + b"sfbk" + sfbk_body

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(riff)
    return output_path


def _chunk(chunk_id: bytes, data: bytes) -> bytes:
    padded = data + (b"\x00" if len(data) % 2 else b"")
    return chunk_id + struct.pack("<I", len(data)) + padded


def _list_chunk(list_type: bytes, *sub_chunks: bytes) -> bytes:
    body = list_type + b"".join(sub_chunks)
    return b"LIST" + struct.pack("<I", len(body)) + body


def _build_info(name: str) -> bytes:
    ifil = _chunk(b"ifil", struct.pack("<HH", 2, 1))  # SF2 version 2.01
    isng = _chunk(b"isng", b"EMU8000\x00")
    inam = _chunk(b"INAM", name.encode("latin-1", errors="replace")[:255] + b"\x00")
    isft = _chunk(b"ISFT", b"Tunerize\x00")
    return _list_chunk(b"INFO", ifil, isng, inam, isft)


def _build_sdta(samples: list[SF2Sample]) -> bytes:
    pcm_parts: list[bytes] = []
    for sample in samples:
        pcm_parts.append(sample.data.tobytes())
        pcm_parts.append(b"\x00\x00" * SAMPLE_PAD)
    smpl = _chunk(b"smpl", b"".join(pcm_parts))
    return _list_chunk(b"sdta", smpl)


def _build_pdta(bank: SF2Bank) -> bytes:
    # We create one instrument per preset for simplicity:
    # preset -> preset_bag -> preset_gen(instrument) -> instrument -> inst_bag -> inst_gen(sample, key range, etc.)

    # --- shdr: sample headers ---
    shdr_records: list[bytes] = []
    sample_offset = 0
    for sample in bank.samples:
        n = len(sample.data)
        padded_name = sample.name.encode("latin-1", errors="replace")[:20].ljust(20, b"\x00")

        loop_start = sample_offset + sample.loop_start
        loop_end = sample_offset + (sample.loop_end if sample.loop_end > 0 else n - 1)

        shdr_records.append(struct.pack(
            "<20sIIIIIBbHH",
            padded_name,
            sample_offset,           # start
            sample_offset + n,       # end
            loop_start,              # loop start
            loop_end,                # loop end
            sample.sample_rate,
            sample.original_pitch,
            sample.pitch_correction,
            0,                       # sample link
            SAMPLE_LINK_MONO,
        ))
        sample_offset += n + SAMPLE_PAD

    # EOS sentinel
    shdr_records.append(struct.pack(
        "<20sIIIIIBbHH",
        b"EOS\x00" + b"\x00" * 16,
        0, 0, 0, 0, 0, 0, 0, 0, 0,
    ))
    shdr = _chunk(b"shdr", b"".join(shdr_records))

    # --- inst + ibag + igen: one instrument per preset ---
    inst_records: list[bytes] = []
    ibag_records: list[bytes] = []
    igen_records: list[bytes] = []

    ibag_idx = 0
    igen_idx = 0

    for preset in bank.presets:
        inst_name = preset.name.encode("latin-1", errors="replace")[:20].ljust(20, b"\x00")
        inst_records.append(struct.pack("<20sH", inst_name, ibag_idx))

        for zone in preset.zones:
            ibag_records.append(struct.pack("<HH", igen_idx, 0))

            # key range
            igen_records.append(struct.pack("<HBB", GEN_KEY_RANGE, zone.key_lo, zone.key_hi))
            igen_idx += 1

            # velocity range
            if zone.vel_lo != 0 or zone.vel_hi != 127:
                igen_records.append(struct.pack("<HBB", GEN_VEL_RANGE, zone.vel_lo, zone.vel_hi))
                igen_idx += 1

            # root key override
            root = zone.root_key if zone.root_key >= 0 else bank.samples[zone.sample_index].original_pitch
            igen_records.append(struct.pack("<Hh", GEN_OVERRIDING_ROOT_KEY, root))
            igen_idx += 1

            # ADSR
            if zone.attack_ms > 0:
                igen_records.append(struct.pack("<Hh", GEN_ATTACK_VOL_ENV, _timecents(zone.attack_ms)))
                igen_idx += 1
            if zone.decay_ms > 0:
                igen_records.append(struct.pack("<Hh", GEN_DECAY_VOL_ENV, _timecents(zone.decay_ms)))
                igen_idx += 1
            if zone.sustain_pct < 100.0:
                igen_records.append(struct.pack("<Hh", GEN_SUSTAIN_VOL_ENV, _sustain_cb(zone.sustain_pct)))
                igen_idx += 1
            if zone.release_ms > 0:
                igen_records.append(struct.pack("<Hh", GEN_RELEASE_VOL_ENV, _timecents(zone.release_ms)))
                igen_idx += 1

            # loop mode
            loop_mode = zone.loop_mode
            if loop_mode < 0:
                loop_mode = SAMPLE_LOOP_CONTINUOUSLY if bank.samples[zone.sample_index].loop_enabled else SAMPLE_NO_LOOP
            if loop_mode != SAMPLE_NO_LOOP:
                igen_records.append(struct.pack("<Hh", GEN_SAMPLE_MODES, loop_mode))
                igen_idx += 1

            # sampleID — must be the last generator in the zone
            igen_records.append(struct.pack("<HH", GEN_SAMPLE_ID, zone.sample_index))
            igen_idx += 1

            ibag_idx += 1

    # Instrument EOS
    inst_records.append(struct.pack("<20sH", b"EOI\x00" + b"\x00" * 16, ibag_idx))
    ibag_records.append(struct.pack("<HH", igen_idx, 0))
    igen_records.append(struct.pack("<Hh", 0, 0))

    inst = _chunk(b"inst", b"".join(inst_records))
    ibag = _chunk(b"ibag", b"".join(ibag_records))
    imod = _chunk(b"imod", struct.pack("<HHhHH", 0, 0, 0, 0, 0))
    igen = _chunk(b"igen", b"".join(igen_records))

    # --- phdr + pbag + pgen: preset headers ---
    phdr_records: list[bytes] = []
    pbag_records: list[bytes] = []
    pgen_records: list[bytes] = []

    pbag_idx = 0
    pgen_idx = 0

    for inst_idx, preset in enumerate(bank.presets):
        preset_name = preset.name.encode("latin-1", errors="replace")[:20].ljust(20, b"\x00")
        phdr_records.append(struct.pack(
            "<20sHHHIII",
            preset_name,
            preset.preset_number,
            preset.bank,
            pbag_idx,
            0, 0, 0,  # library, genre, morphology
        ))

        # One preset zone pointing to the instrument
        pbag_records.append(struct.pack("<HH", pgen_idx, 0))
        pgen_records.append(struct.pack("<HH", GEN_INSTRUMENT, inst_idx))
        pgen_idx += 1
        pbag_idx += 1

    # Preset EOS
    phdr_records.append(struct.pack(
        "<20sHHHIII",
        b"EOP\x00" + b"\x00" * 16,
        0, 0, pbag_idx, 0, 0, 0,
    ))
    pbag_records.append(struct.pack("<HH", pgen_idx, 0))
    pgen_records.append(struct.pack("<Hh", 0, 0))

    phdr = _chunk(b"phdr", b"".join(phdr_records))
    pbag = _chunk(b"pbag", b"".join(pbag_records))
    pmod = _chunk(b"pmod", struct.pack("<HHhHH", 0, 0, 0, 0, 0))
    pgen = _chunk(b"pgen", b"".join(pgen_records))

    return _list_chunk(b"pdta", phdr, pbag, pmod, pgen, inst, ibag, imod, igen, shdr)
