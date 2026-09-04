# Final Buildathon Evaluation

Held-out rows: 10000

| Strategy | Recovery rate | Incremental revenue | Net revenue | ROI | Intervention rate |
|---|---:|---:|---:|---:|---:|
| No Intervention | 49.01% | ₹0.00 | ₹8,969,433.37 | n/a | 0.00% |
| Always Retry | 51.62% | ₹77,613.63 | ₹8,992,888.17 | 1.17274 | 100.00% |
| Rule-Based Recovery | 56.80% | ₹1,034,581.32 | ₹9,907,144.71 | 12.850466 | 70.72% |
| ML Recovery | 51.69% | ₹91,118.50 | ₹9,012,867.26 | 2.673184 | 81.24% |
| ML + Optimization | 60.05% | ₹1,556,393.68 | ₹10,388,383.86 | 13.519995 | 98.55% |
| ML + Uplift + Optimization | 60.05% | ₹1,556,393.68 | ₹10,388,383.86 | 13.519995 | 98.55% |
| Full NexaRecover AI | 57.76% | ₹1,144,127.42 | ₹10,054,310.79 | 18.310167 | 78.81% |

This is a final held-out evaluation only. No test rows were used for tuning.
Results are synthetic/counterfactual estimates, not production causal claims.