---
name: sequence-check
description: Inspect explicit local rendered image sequences for missing frames, corrupt images, EXR channel differences, nonfinite values, and suspected black or repeated frames.
---

1. Resolve the user's exact absolute directory and sequence filename glob. Call sequence_discover if multiple sequences may be present; show groups and let the user identify ambiguous targets.
2. Obtain expected start/end from the user's request or known project settings. Without both endpoints, only gaps within the observed span are detectable. Say so rather than claiming the sequence is complete.
3. Call sequence_inspect with the narrow selection. It decodes PNG/JPEG/TIFF/BMP and flat multipart EXR. Grouping uses the last digit run before the extension; different padding may reveal duplicate frame numbers. Negative frame naming is not interpreted as signed numbers.
4. Report missing/duplicate frames, decode errors and changed layout separately from suspected black/identical pixels. Static shots and intentional fades may be valid. Nonfinite AOV data may need interpretation. No colour transform, artistic judgment or render-engine validation is performed.
5. Explicitly report unverified files and coverage limits: 1000 selected files, 10000 directory entries, 16,777,216 pixels per image/EXR part, 256 MiB estimated decoded channel data, 512 MiB input file. Deep EXR, additional tiled EXR mip/rip levels, and animated/multi-page raster are not fully checked. Split large workloads with explicit patterns. Never call no matches a pass.

Tools never change the source or create videos/reports. Summarize the returned data in chat. Ask for explicit separate output instructions before using other tools to write a report. Do not silently delete, overwrite or re-render flagged frames.
