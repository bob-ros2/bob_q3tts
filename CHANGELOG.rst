^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Changelog for package bob_q3tts
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Unreleased
----------
* Add `max_new_tokens` (env `Q3TTS_MAX_NEW_TOKENS`, default 1024 ≈ 85 s at the 12 Hz code rate) forwarded to both generation paths; without it the checkpoint default 8192 (~11 min) lets a runaway generation babble until EOS
* Show the cap in the GUI Generation group and document it in the parameter table
* Default to sampling (`do_sample: true`) instead of greedy decoding
* Contributors: Bob Ros

1.1.0 (2026-04-01)
------------------
* Upgrade sentence splitting to support multi-character delimiters (e.g. '. ')
* Add 'substitute' parameter for regex-based text cleaning (removes HTML, emojis, etc.)
* Fix ALSA buffer underrun issues by enabling 'aplay' fallback
* Contributors: Bob Ros, Antigravity

1.0.0 (2026-01-28)
------------------
* Initial release of bob_q3tts
* Contributors: Bob Ros
