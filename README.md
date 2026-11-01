# PerceptualEntropyLog

Live viewer: <https://xiaofeng-tan.github.io/PerceptualEntropyLog/> — three settings; each has a Reward and a Diversity card, and every key in `scalars.json` is selectable in the card's dropdown.

Sanitized training logs for the Perc-EC / Perc-VC experiments, one setting per tab (names follow the paper):

| Setting | Directory | Runs |
|---|---|---|
| FLUX.dev · DDPO | `flux_pec_ddpo` | Perc-EC (λ = 0.05), Perc-VC (λ = 0.03, 0.08, 0.10), Native Ent. (λ = 0.05, 0.10) |
| FLUX.dev · Flow-GRPO | `flux_pec_40g` | Perc-EC (λ = 0.05, 0.10), Perc-VC (λ = 0.03, 0.10); still training at export time |
| Wan2.1-T2V-1.3B · Flow-GRPO | `wan21_pec_final` | Flow-GRPO, Perc-EC (λ = 0.04, 0.05), Native Ent. (λ = 0.05) |

Validation samples are per setting: `samples/flux_pec_40g/` (Flow-GRPO) and `samples/val/` (DDPO); none are released for Wan2.1.

## Read the curves

```python
import json
s = json.load(open("flux_pec_ddpo/runs/DDPO-PCVAE-0.08/scalars.json"))
steps  = [p["step"]  for p in s["reward_avg"]]
values = [p["value"] for p in s["reward_avg"]]
```

- `<project>/runs/<run>/scalars.json` — all scalars at full resolution, `{key: [{step, value}]}` (wall-clock timestamps are removed)
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
