# PerceptualEntropyLog

Live viewer: <https://xiaofeng-tan.github.io/PerceptualEntropyLog/> — two settings; each has a Reward and a Diversity card, and every key in `scalars.json` is selectable in the card's dropdown.

Sanitized training logs for the Perc-EC / Perc-VC experiments: 6 FLUX+DDPO runs and 4 Wan2.1+GRPO runs.

## Read the curves

```python
import json
s = json.load(open("flux_pec_ddpo/runs/DDPO-PCVAE-0.08/scalars.json"))
steps  = [p["step"]  for p in s["reward_avg"]]
values = [p["value"] for p in s["reward_avg"]]
```

- `<project>/runs/<run>/scalars.json` — all scalars at full resolution, `{key: [{step, value, timestamp}]}` (Unix ms)
- `<project>/runs/<run>/config.json` — training hyperparameters
- `wan21_pec_final/runs/Native Entropy-0.05/scalars_aligned.json` — same run on the baseline's step axis; use this one when comparing against `baseline-GRPO`

## Dashboard

`swanlog/` is not committed, so regenerate it first:

```bash
pip install "swanlab[dashboard]==0.10.2"
python tools/rebuild.py flux_pec_ddpo/runs /tmp/swanlog flux_pec_ddpo
mv /tmp/swanlog flux_pec_ddpo/swanlog
swanlab watch flux_pec_ddpo/swanlog -p 5092      # http://127.0.0.1:5092
```

## Add new logs

Copy each run's `scalars.json` and `config.json` into `<project>/runs/<run>/`, then:

```bash
git add -A && git commit -m "..." && git push
```

`console.log`, `system.json` and `swanlog/` are gitignored and stay out of the repo.
