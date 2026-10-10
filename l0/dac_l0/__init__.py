"""Detect A Clip — desktop synthetic L0 track (reference / research harness).

This package is the Python reference implementation of the on-device recognition
pipeline described in roadmap v4.2.1 (F03–F05). It runs on a desktop against
self-created synthetic assets only. It is not the shipped mobile engine; the product
remains native Kotlin/Swift. Everything here is LAB-purpose evidence.
"""

__version__ = "0.1.0"

# Identifiers that bind the recognition tuple (F04). Bumping any of these invalidates
# previously built packs; the pack loader checks compatibility against them.
GENERATOR_VERSION = "synth-gen-3"
PREPROCESSING_VERSION = "prep-640x360-gray-uniformcrop-3"
INDEX_FORMAT_VERSION = "idx-flat-4"  # writer; readers also accept idx-flat-3 (migration)
# Preprocessing identifier of the integer-exact device path (ED-17).
EXACT_PREPROCESSING_VERSION = "dac-crop-v1+dac-qual-v1+dac-dhash-v1"
CALIBRATION_STATUS_DEFAULT = "UNCALIBRATED"  # until P04-T05 freezes thresholds
