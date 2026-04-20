# Stage 3 — Sentiment Simulation Blueprint

Miroshark-style multi-persona simulation — pre-event narrative stress test.

## What problem it solves

Equity allocator's hardest call: **"how will the market NARRATIVE react to X?"**
- Pre-earnings: beat/miss/guide surprise impact on price path
- Corporate action: rights issue, buyback, M&A announcement
- Regulation: BI rate decision, sectoral policy

Fundamental models don't capture reflexivity. Simulation does.

## Architecture (simplified from MiroShark)

```
Input: event description + target ticker + context docs
      │
      ▼
┌──────────────────────────────────────────────┐
│  Persona generator                            │
│  Spawn N personas dengan distinct biases      │
└─┬──────────────┬──────────────┬──────────────┘
  │              │              │
  ▼              ▼              ▼
Retail Bull   Retail Bear   Institutional   Foreign    Media    Reg body
 (WSB-like)   (permabear)   (sell-side)     (macro)   (pundit)  (OJK/BI view)
  │              │              │              │         │          │
  └──────────────┴──────────────┴──────────────┴─────────┴──────────┘
                                 │
                                 ▼
                    Round-based interaction
                    (each persona posts, reacts to others,
                     evolves opinion over simulated hours)
                                 │
                                 ▼
                    Aggregated narrative metrics:
                    - Sentiment trajectory
                    - Virality score
                    - Polarization index
                    - Price impact estimate
```

## Persona template example

```python
PERSONAS = {
    'retail_bull': {
        'name': 'Pak Budi (WSB-ID equivalent)',
        'bias': 'momentum chaser, FOMO prone',
        'reaction_speed': 'fast (minutes)',
        'influence': 'medium (viral amplifier)',
        'system_prompt': '''Kamu retail Indonesia yg aktif di grup Telegram saham. 
        Cenderung bullish narratives yang lagi trend. Suka all-caps, emoji rocket, 
        "TP naik", "belum telat masuk". Reaction cepat, bias momentum.'''
    },
    'retail_bear': {
        'name': 'Perma-bear Analyst',
        'bias': 'skeptical, focus on risks',
        'reaction_speed': 'medium',
        'influence': 'low-medium',
        'system_prompt': '''Kamu analyst retail yg skeptis. Focus pada red flags, 
        skandal masa lalu, indikator bearish. Bahasa formal tapi sinis.'''
    },
    'institutional': {
        'name': 'Sell-side Analyst (Tier-1 securities)',
        'bias': 'model-driven, cautious',
        'reaction_speed': 'slow (hours-days)',
        'influence': 'high (sets consensus)',
        'system_prompt': '''Kamu analyst institutional dari sekuritas besar. 
        Decision driven by model revisions, peer comparison, macro overlay. 
        Tone professional, cite specific numbers.'''
    },
    'foreign_flow': {
        'name': 'Regional PM (SG/HK based)',
        'bias': 'macro-driven, EM sentiment',
        'reaction_speed': 'slow',
        'influence': 'high (price impact via flow)',
        'system_prompt': '''Kamu PM fund regional yg cover EM Asia incl Indonesia. 
        Perspective macro: FX, Fed policy, commodity cycle, EM risk appetite. 
        Bahasa Inggris, mostly.'''
    },
    'media_pundit': {
        'name': 'Financial Media (CNBC-ID, Kontan)',
        'bias': 'narrative amplifier, story-driven',
        'reaction_speed': 'medium',
        'influence': 'high (sets public perception)',
        'system_prompt': '''Kamu journalist finansial. Cari angle dramatic, 
        quote berbagai pihak, simplify complex issues.'''
    },
    'regulator_view': {
        'name': 'OJK/BI perspective',
        'bias': 'systemic risk, stability',
        'reaction_speed': 'very slow (weeks)',
        'influence': 'very high (policy action)',
        'system_prompt': '''Kamu pandangan regulator (OJK atau BI). Focus stabilitas 
        pasar, investor protection, systemic risk. Tidak vocal tapi bisa bertindak.'''
    },
}
```

## Round dynamics

```python
async def run_simulation(event, ticker, personas, n_rounds=5):
    state = {p: {'sentiment': 0, 'posts': [], 'influence_received': 0} for p in personas}
    
    for round_i in range(n_rounds):
        # Each persona sees: event + other personas' previous posts
        for persona_id, persona in personas.items():
            context = build_context(event, ticker, state, round_i)
            post = await llm_call(persona['system_prompt'], context)
            state[persona_id]['posts'].append(post)
            
            # Update sentiment based on post
            state[persona_id]['sentiment'] = extract_sentiment(post)
        
        # Cross-influence: high-influence personas affect others
        propagate_influence(state, personas)
    
    # Aggregate
    return {
        'trajectory': plot_sentiment_over_rounds(state),
        'virality': calc_virality(state),
        'polarization': calc_polarization(state),
        'dominant_narrative': extract_dominant_theme(state),
        'price_impact_estimate': estimate_impact(state, ticker),
    }
```

## Implementation approach

### MVP (no Neo4j)
- SQLite storage untuk persona state, posts, rounds
- 6 fixed personas (as above)
- 3-5 rounds
- Model: Claude Sonnet 4.6 atau Gemma 3 12B local (faster for many calls)
- Output: structured JSON + chart timeline

### v2 (add graph)
- Neo4j untuk entity + relationship tracking
- Add persona memory (siapa inget siapa bilang apa)
- More personas (10-20)
- Longer simulations (10+ rounds)

### v3 (seeded from real data)
- Twitter/Reddit search API untuk seed persona context dari actual discussions
- Calibrate persona behavior ke observed historical reactions

## Validation approach

**Hardest problem: accuracy.** Simulated ≠ real reaction.

Tactics:
1. **Backtest** — run sim pada event historis (e.g., BBRI rights issue, TLKM spinoff), compare output sentiment trajectory ke actual price path
2. **Hold-out** — reserve recent events tidak dipakai buat calibrate
3. **Confidence intervals** — report sim sebagai probability distribution, bukan point estimate
4. **Human override** — final call user, sim as decision aid

## Cost estimate

- 6 personas × 5 rounds = 30 LLM calls per simulation
- Avg 500 tokens per call × $3/M input + $15/M output
- ~$0.10-0.30 per simulation (Sonnet 4.6)
- ~$0.03 per sim kalau pake Gemma local (free, slower)
- Target: 30-60 sims per month = $5-20/month

## Files to create

```
backend/analysis/
├── sentiment.py              # orchestrator
├── personas.py               # persona library
├── graph_store.py            # sqlite impl (v1), neo4j (v2)
├── price_impact_estimator.py # aggregate → price delta estimate
└── sentiment_validation.py   # backtesting harness
```

## Routes

```
POST /api/analysis/sentiment/{ticker}   # start sim
GET  /api/analysis/sentiment/sim/{id}   # get result
GET  /api/analysis/sentiment/stream/{id}  # SSE for live progress
```

## UI

- Event input: textarea "describe the event"
- Persona toggle: enable/disable each persona
- Rounds slider: 3-10
- "Run Simulation" → progress bar + live round posts streaming
- Results: sentiment timeline chart + dominant narrative summary + recommended action

## Not in MVP

- Real-time integration dengan current news
- Persona training on historical posts
- Multi-ticker correlation
- Backtesting harness UI (internal tool dulu)
