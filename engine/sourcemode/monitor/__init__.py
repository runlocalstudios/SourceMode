"""Live readout of the GPU box: what the card is doing, for whom, and how long is left.

Three sources, each behind a pure parser so it is unit-testable without hardware:
  gpu.py       nvidia-smi        utilisation, VRAM, temperature, power
  training.py  musubi log + ps   step/epoch progress and ETA of a LoRA run
  comfy.py     ComfyUI /queue    what is rendering and how much is queued
sampler.py folds them into one status dict and keeps an hour of history;
service.py serves that over HTTP for the control panel.
"""
