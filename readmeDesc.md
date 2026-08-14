# Dataset Short Description

This dataset contains raw multi-sensor recordings from a brushed PM DC servo motor (3PI12.12) operated under multiple conditions and speed setpoints (percentages of rated speed; the motor runs unloaded, with no external mechanical load).

It includes four sensor modalities:
- armature current waveforms (BIN)
- vibrometer waveform audio (WAV)
- smartphone audio (M4A)
- vibrometer spot measurements (XLS)

The dataset is organized into four main condition families: normal operation, loose foundation, suboptimal speed-regulator tuning, and suboptimal speed-regulator tuning with RT (current-regulator) coefficient variation. Each family is provided in two variants: without reversal (constant rotation direction) and with reversal (rotation direction reversed every 4 seconds).

The files are organized by condition and sensor, with metadata in metadata.csv, and are intended for condition monitoring research such as fault classification, speed estimation, and phone-vs-instrument benchmarking.
