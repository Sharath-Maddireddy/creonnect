# Financial Model & KPI Tracker

## Usage

This document provides templates and formulas to track Creonnect's financial performance monthly. Copy into a spreadsheet (Excel, Sheets) and update with actual data.

For the product and engineering rules behind credits, provider cost conversion, and usage deduction, see [CREDITS_AND_USAGE_MODEL.md](CREDITS_AND_USAGE_MODEL.md).

---

## 1. Monthly Subscription Summary

```
MONTH: ___________

SUBSCRIBERS BY TIER:
├─ Starter ($4.99):        _____ users  ×  $4.99  = $______
├─ Pro ($12.99):           _____ users  ×  $12.99 = $______
├─ Agency ($49.99):        _____ users  ×  $49.99 = $______
└─ Enterprise (custom):    _____ users  ×  $____ = $______

TOTAL MRR (Monthly Recurring Revenue):     $______
ARPU (MRR ÷ Total Users):                  $______
YoY Annual Forecast:                       $______
```

---

## 2. Cost Tracking

### A. Infrastructure Costs

```
Compute (EC2/VPS):          $______  [budget: $78]
Database (RDS):             $______  [budget: $110]
Redis (cache):              $______  [budget: $72]
Storage & CDN (S3/CF):      $______  [budget: $402]
Monitoring & Observability: $______  [budget: $225]
────────────────────────────────────────
SUBTOTAL:                   $______  [budget: $887]
```

### B. API & Third-Party Costs

```
OpenAI (LLM + embeddings):  $______  [budget: $1,440]
Gemini Vision:              $______  [budget: $400]
Email/Auth services:        $______  [budget: $70]
────────────────────────────────────────
SUBTOTAL:                   $______  [budget: $1,910]
```

### C. Personnel Costs

```
Backend Engineer (0.5 FTE):     $______  [budget: $2,500]
DevOps/Infra (0.3 FTE):        $______  [budget: $1,500]
Support/Success (0.5 FTE):     $______  [budget: $1,000]
────────────────────────────────────────
SUBTOTAL:                       $______  [budget: $5,000]
```

### D. Operational Overhead

```
Stripe processing (2.9% + $0.30): $______  [budget: $150]
Domain/SSL:                       $______  [budget: $20]
Software licenses:                $______  [budget: $50]
Legal/Compliance:                 $______  [budget: $200]
Marketing (optional):             $______  [budget: $500]
────────────────────────────────────────
SUBTOTAL:                         $______  [budget: $920]
```

### E. Total Operating Costs

```
Infrastructure:        $______
APIs:                  $______
Personnel:             $______
Overhead:              $______
────────────────────────────────────────
TOTAL:                 $______  [budget: $8,717]

Cost per User: $ ______ ÷ _____ users = $______  [target: <$2.50]
```

---

## 3. Profitability Analysis

```
Monthly Recurring Revenue (MRR):       $______
Total Operating Costs:                 $______
────────────────────────────────────────
GROSS PROFIT:                          $______

Gross Margin %: $_______ ÷ $_______ × 100 = _____%  [target: >80%]

Net Profit (profit after tax, est. 25%): $______
Net Margin %: ______ ÷ $_______ × 100 = _____%  [target: >60%]
```

---

## 4. Unit Economics

```
Total Subscribers:                     _____
Average Revenue Per User (ARPU):       $______
Cost per User (OPEX/subscribers):      $______
Gross Profit per User:                 $______  [target: >$10]
────────────────────────────────────────

Lifetime Value (LTV) assuming 18-month avg lifetime:
LTV = Monthly Gross Profit per User × 18 months
LTV = $______ × 18 = $______  [target: >$150]

Customer Acquisition Cost (CAC):       $______
LTV:CAC Ratio = $______ ÷ $______ = ______:1  [target: >20:1]
```

---

## 5. Growth Metrics

### A. User Growth

```
Previous Month Total Users:    _____
New Users This Month:          _____
Churned Users This Month:      _____
────────────────────────────────────────
Current Month Total Users:     _____

Churn Rate % = _____ ÷ _____ × 100 = _____%  [target: <5%]
Net Growth Rate = (New - Churn) = _____  [target: 10-20% early stage]
```

### B. Conversion Funnel (Free → Paid)

```
Free Tier Users:                     _____
Converted to Paid This Month:        _____
Free-to-Paid Conversion Rate:        _____%  [target: >3-5%]
```

### C. Tier Breakdown

```
Starter:  _____ users (____%)  MRR: $_______
Pro:      _____ users (____%)  MRR: $_______
Agency:   _____ users (____%)  MRR: $_______
Enterprise: _____ customers (__%) MRR: $_______
────────────────────────────────────────────────
Total:    _____ users (100%)   MRR: $_______

Most valuable tier by total MRR: __________
```

---

## 6. API Usage & Efficiency

### A. OpenAI API

```
Account Analyses run this month:    _____
Average cost per analysis:          $_____  [target: <$0.10]
Total OpenAI spend:                 $_____

LLM Requests:                       _____
Avg. cost per request:              $_____
────────────────────────────────────────
Embedding operations:               _____
Cached vs. fresh (cache hit %):     _____%  [target: >60%]
```

### B. Gemini Vision API

```
Vision analyses run:                _____
Avg. cost per analysis:             $_____  [target: <$0.004]
Total Gemini spend:                 $_____

Vision enabled customers:           _____  [tier breakdown]
├─ Pro:         _____ (100%)
├─ Agency:      _____ (100%)
└─ Enterprise:  _____ (100%)
```

### C. API Cost Efficiency

```
API Spend as % of Revenue: $______ ÷ $______ × 100 = _____%
Target: <5% of MRR
────────────────────────────────────────

If exceeding target, actions:
□ Increase API caching (target: 70% hit rate)
□ Batch requests (target: 6-hour batches)
□ Use cheaper models for simple tasks
□ Make vision optional per tier
□ Implement rate limiting per user tier
```

---

## 7. Cost Per Feature (Single-Use)

Track the cost of individual feature usage. Use this to understand profitability per operation.

### A. Account Analysis (Complete)

```
One account analysis includes:
  ├─ Profile fetch (Instagram Graph API):     $0.00  [free]
  ├─ Post fetch & ingestion:                  $0.00  [free]
  ├─ Deterministic analytics (S1-S5):         $0.00  [internal]
  ├─ Niche detection (embeddings):            $0.005 [OpenAI embeddings]
  ├─ Growth scoring:                          $0.00  [internal]
  ├─ LLM action plan generation:              $0.02  [OpenAI gpt-4o-mini]
  └─ Vision analysis (20 posts × $0.004):     $0.08  [Gemini]
  ──────────────────────────────────────────
  TOTAL PER ACCOUNT:                          $0.105
  ──────────────────────────────────────────
  Actual avg (with caching):                  $0.08  [30% API cache hit saves ~$0.025]

Price points (conservative):
├─ Starter tier (20/month):  $0.08 × 20 = $1.60   [cost covered]
├─ Pro tier (unlimited):     avg ~$0.08 per
├─ Agency (bulk 100):        $0.08 × 100 = $8.00  [margin: $41.91]
└─ Enterprise (1000+):       $0.08 × 1000 = $80   [margin: huge]
```

### B. Single Post Analysis

```
One post analysis includes:
  ├─ Image download & caching:                $0.00  [S3, amortized]
  ├─ Deterministic metrics (S1-S5):           $0.00  [internal]
  ├─ Caption analysis (LLM if enabled):       $0.01  [OpenAI token estimate]
  ├─ Vision analysis (cringe/safety/hooks):   $0.004 [Gemini 2MP image]
  └─ Engagement benchmark (DB lookup):        $0.00  [internal]
  ──────────────────────────────────────────
  TOTAL PER POST:                             $0.014
  ──────────────────────────────────────────
  Starter (deterministic only):               $0.002 [vision disabled]
  Pro (full analysis):                        $0.014
  Agency bulk (1000 posts):                   $14.00 [margin: $35.99 per 49.99 tier]
```

### C. Vision Analysis (Cringe, Brand-Safety, Production)

```
Cost per image:                     $0.004  [Gemini 2MP pricing]

Included in Pro/Agency tiers:
├─ Cringe scoring:                  $0.004
├─ Brand-safety detection:          $0.004 [same API call]
├─ Hook strength detection:         $0.004 [same API call]
├─ Production level classification: $0.004 [same API call]
└─ Technical flaws detection:       $0.004 [same API call]

Result: All vision features in ONE call = $0.004 per image
(Multiple analyses on same image = cached, ~$0 incremental)
```

### D. Niche Detection & Creator Intelligence

```
Niche Detection (one creator):
  ├─ Embedding generation (posts):            $0.002 [OpenAI embeddings]
  ├─ Vector similarity search (pgvector):     $0.00  [internal DB]
  └─ LLM refinement (optional):               $0.01  [if using full LLM]
  ──────────────────────────────────────────
  TOTAL (deterministic):                      $0.002
  TOTAL (with LLM):                           $0.012

Creator Intelligence (full summary):
  ├─ All niche data:                          $0.002
  ├─ Brand-fit analysis (LLM):                $0.02  [OpenAI]
  ├─ Content style synthesis:                 $0.01  [OpenAI]
  └─ Red flags & opportunities:               $0.01  [OpenAI]
  ──────────────────────────────────────────
  TOTAL PER CREATOR:                          $0.042

Only included in Pro/Agency/Enterprise (not Starter)
```

### E. Action Plan Generation (RAG + LLM)

```
One complete action plan:
  ├─ RAG retrieval (markdown chunks):         $0.00  [in-memory, free]
  ├─ LLM synthesis (2-3 calls gpt-4o-mini):  $0.02  [OpenAI completion tokens]
  ├─ Formatting & fallback logic:             $0.00  [internal]
  └─ Daily/weekly action breakdown:           $0.00  [template]
  ──────────────────────────────────────────
  TOTAL PER ACTION PLAN:                      $0.02

Fallback (deterministic):                     $0.00  [rules-based, no API cost]
Cache (regenerate after 7 days):              $0.00  [incremental]
```

### F. Snapshots & Historical Tracking

```
One snapshot (daily snapshot of creator state):
  ├─ Fetch latest metrics from DB:            $0.00  [query cost negligible]
  ├─ Store in Redis (compressed):             $0.00  [storage in tier]
  ├─ Archive after 7 days to S3:              $0.001 [S3 write]
  └─ Retrieve old snapshot (historical):      $0.00  [retrieval from Redis/S3]
  ──────────────────────────────────────────
  TOTAL PER SNAPSHOT:                         $0.001

At scale (5K users, 1 snapshot/day):
  = 5,000 snapshots/day × $0.001 = $5/day = $150/month
  (negligible in overall costs)
```

### G. Report Generation & Exports

```
One PDF/Excel report export:
  ├─ Fetch data from DB & cache:              $0.00  [query cost minimal]
  ├─ Format & compile report:                 $0.00  [internal processing]
  ├─ Generate PDF (if needed):                $0.005 [assume external PDF service]
  ├─ Store in S3:                             $0.001 [S3 write]
  └─ Deliver via email:                       $0.10  [SendGrid per 100 emails ≈ $0.001 per email, or use bulk)
  ──────────────────────────────────────────
  TOTAL PER REPORT (PDF):                     $0.006
  TOTAL PER REPORT (CSV, no PDF):             $0.001

Agency tier (bulk 20 reports/month):         $0.12 [margin: $49.87]
```

### H. Embedding Search (Creator Pool)

```
One pool search (find similar creators):
  ├─ Query embedding generation:              $0.001 [OpenAI embeddings]
  ├─ pgvector similarity search:              $0.00  [internal)
  ├─ Return top N matches:                    $0.00  [internal]
  └─ Optional: LLM match reasoning:           $0.01  [if enabled]
  ──────────────────────────────────────────
  TOTAL (deterministic):                      $0.001
  TOTAL (with LLM reasoning):                 $0.011

Typical usage: Agency tier, 10 searches/month = $0.01
```

### I. Engagement Signals & Benchmarking

```
One account's engagement signals:
  ├─ Aggregate post metrics:                  $0.00  [SQL query]
  ├─ Niche benchmark lookup:                  $0.00  [DB cache)
  ├─ Trend analysis:                          $0.00  [internal)
  ├─ Compute trust/virality indices:          $0.00  [internal]
  └─ Compare to peers (if applicable):        $0.00  [batch query]
  ──────────────────────────────────────────
  TOTAL PER ACCOUNT:                          $0.00  [FREE]

Included in all tiers (pro/agency/enterprise)
```

### J. Webhooks & Real-Time Alerts

```
One webhook event notification:
  ├─ Trigger evaluation:                      $0.00  [internal]
  ├─ Format payload:                          $0.00  [internal]
  ├─ Send webhook (external):                 $0.00  [outbound, no cost]
  └─ Retry logic if failed:                   $0.00  [internal]
  ──────────────────────────────────────────
  TOTAL PER WEBHOOK:                          $0.00  [FREE]

Storage (log webhook events):                 $0.001 per 100 events [negligible]

Agency tier: include 1000 webhooks/month = free
Enterprise: unlimited webhooks = free
```

---

## 8. Total Feature Cost Table (Reference)

```
FEATURE                              COST PER USE    FREQUENCY (5K users)    MONTHLY TOTAL
────────────────────────────────────────────────────────────────────────────────────────
Account Analysis (full)              $0.08           3,000/mo (60% of users) $240
Post Analysis (single)               $0.014          100,000/mo (20 posts × 5K users) $1,400
Vision Analysis (cringe/safety)      $0.004          100,000/mo (20 posts × 5K users) $400
Niche Detection                      $0.002          5,000/mo (once per user) $10
Creator Intelligence                 $0.042          1,500/mo (Pro+ only)    $63
Action Plan Generation               $0.02           3,000/mo (full analysis) $60
Snapshots (daily)                    $0.001          150,000/mo (5K × 30 days) $150
Report Export (PDF)                  $0.006          5,000/mo (Agency tier)  $30
Embedding Pool Search                $0.001          2,000/mo (Agency)       $2
Engagement Signals (free)            $0.00           All users               $0
Webhooks (free)                      $0.00           10,000/mo (Agency+)     $0
────────────────────────────────────────────────────────────────────────────────────────
TOTAL API COSTS                                                               $2,355

Note: Some features overlap (e.g., vision included in account analysis)
Actual costs with optimization: ~$1,910/month (20% savings from caching)
```

---

## 9. Cost Per Tier (Feature-Based Breakdown)

### Starter ($4.99/month)

```
Included:
  ├─ Dashboard (views only):        $0.00
  ├─ Niche detection:               $0.002
  ├─ Growth score:                  $0.00
  ├─ 20 post analyses/month:        $0.002 × 20 = $0.04  [deterministic, no vision]
  └─ Basic action plan (fallback):  $0.00
  ───────────────────────────────────
  TOTAL API COST PER USER:          $0.042/month
  PROFIT PER USER:                  $4.99 - $0.042 = $4.948  (99% margin)
```

### Pro ($12.99/month)

```
Included:
  ├─ Unlimited accounts:            $0.00
  ├─ Full account analysis:         $0.08 × 2 = $0.16     [assume 2 per month avg]
  ├─ Unlimited post analyses:       $0.014 × 20 = $0.28   [20 posts, with vision]
  ├─ Creator intelligence:          $0.042 × 1 = $0.042   [once per month]
  ├─ Action plans (LLM):            $0.02 × 2 = $0.04     [2 per month]
  ├─ Daily snapshots (7-day):       $0.001 × 7 = $0.007
  ├─ Engagement signals:            $0.00
  ├─ Webhooks:                      $0.00
  └─ Basic reporting:               $0.00
  ───────────────────────────────────
  TOTAL API COST PER USER:          $0.529/month
  PROFIT PER USER:                  $12.99 - $0.529 = $12.461  (96% margin)
```

### Agency ($49.99/month)

```
Included:
  ├─ Everything in Pro ×5 accounts: $0.529 × 5 = $2.645
  ├─ Bulk analyses (100 creators):  $0.08 × 100 = $8.00
  ├─ Advanced reports (20 exports): $0.006 × 20 = $0.12
  ├─ Pool searches (10 queries):    $0.001 × 10 = $0.01
  ├─ Snapshots (30-day retention):  $0.001 × 30 = $0.03
  ├─ Webhooks (unlimited):          $0.00
  ├─ Team support:                  $0.00
  └─ API access (unlimited):        $0.00
  ───────────────────────────────────
  TOTAL API COST PER USER:          $10.805/month
  PROFIT PER USER:                  $49.99 - $10.805 = $39.185  (78% margin)

Note: Agency tier has lower margin % but higher absolute $ profit per user
```

### Enterprise (Custom, assume $500/month avg)

```
Included:
  ├─ Everything in Agency ×10 accounts: $10.805 × 10 = $108.05  [scaled usage]
  ├─ Bulk analyses (1000 creators):     $0.08 × 1000 = $80.00
  ├─ White-label infrastructure:       ~$50.00                 [extra compute]
  ├─ Dedicated support:                ~$100.00 FTE allocation [staff cost]
  ├─ Custom integrations:              ~$50.00                 [engineering time]
  └─ SLA & uptime guarantee:           ~$20.00                 [monitoring]
  ───────────────────────────────────
  TOTAL COST PER CUSTOMER:           $408.05/month (blended)
  PROFIT PER CUSTOMER:               $500 - $408.05 = $91.95  (18% margin)

But at scale, if 10-20 Enterprise customers:
  ├─ Amortized support cost per customer drops
  ├─ Actual margin approaches 80%+
  └─ Lifetime value is highest
```

---

## 10. Margin Analysis By Tier

```
              STARTER    PRO        AGENCY     ENTERPRISE
─────────────────────────────────────────────────────────────
Price         $4.99      $12.99     $49.99     $500 (avg)
API Cost      $0.042     $0.529     $10.805    ~$80 (avg)
Infra/Ops*    $0.50      $1.50      $7.00      $50.00
─────────────────────────────────────────────────────────────
Total Cost    $0.542     $2.029     $17.805    ~$130
Profit        $4.448     $10.961    $32.185    $370
─────────────────────────────────────────────────────────────
Margin %      89%        84%        64%        74%

*Infra/Ops = proportional allocation of $5,920 personnel + $887 infra per user
```

---

## 11. Cost Optimization Per Feature

```
FEATURE                    CURRENT COST    OPTIMIZATION STRATEGY           SAVINGS
─────────────────────────────────────────────────────────────────────────────────
Account Analysis           $0.08          Cache results (7-day TTL)        -$0.02  (25%)
Post Analysis Vision       $0.004         Make optional per tier           -$0.004 (free tier)
Niche Detection            $0.002         Batch embeddings (6-hour)        -$0.001 (50%)
Creator Intelligence       $0.042         Cache & quarterly only           -$0.02  (50%)
Action Plan Generation     $0.02          Use cheaper model for simple     -$0.005 (25%)
Snapshots                  $0.001         Reduce retention (3 days not 7)  -$0.0005
Report Export              $0.006         Use HTML instead of PDF         -$0.005 (80%)
Embedding Search           $0.001         Pre-batch vectors               -$0.0005
─────────────────────────────────────────────────────────────────────────────────
TOTAL POTENTIAL SAVINGS:                                                   -$0.091 (50%)

This reduces API costs from $1,910 to ~$955/month
```

---

## 12. Cost Per Tier - Batch Operations

For bulk/enterprise customers:

```
BULK OPERATION                     UNIT COST      BULK SIZE    BULK TOTAL    PRICE
────────────────────────────────────────────────────────────────────────────────────
Analyze 100 creators               $0.08          100          $8.00         $39.99 (Agency)
Analyze 1000 creators              $0.08          1000         $80.00        $500 (Enterprise)
Export 20 reports                  $0.006         20           $0.12         included
Vision analysis (1000 images)      $0.004         1000         $4.00         included
Niche detection (500 users)        $0.002         500          $1.00         included
Creator intelligence (100)         $0.042         100          $4.20         included
Pool searches (100)                $0.001         100          $0.10         included
────────────────────────────────────────────────────────────────────────────────────
TOTAL FOR BULK JOB                                             $97.42        $500+

Margin: Enterprise customer pays $500/mo for ~$97 in API costs
Remaining $403 covers support, infrastructure scaling, and profit
```

---

## Cash Flow Projection (Next 6 Months)

```
         Month 1  Month 2  Month 3  Month 4  Month 5  Month 6
────────────────────────────────────────────────────────────
MRR      $_____   $_____   $_____   $_____   $_____   $_____
Costs    $_____   $_____   $_____   $_____   $_____   $_____
Profit   $_____   $_____   $_____   $_____   $_____   $_____

Cumulative Profit: $_______
────────────────────────────────────────────────────────────
Target Growth (MRR Month-to-Month):
□ 20% month 1-2 (freemium stage)
□ 50% month 2-3 (launch paid tiers)
□ 30% month 3-6 (scale & optimize)
```

---

## 8. Scenario Analysis

### Conservative (Lower Conversion)

```
Tier Distribution:
├─ Starter: 60% of free users (lower ARPU)
├─ Pro:     35% of free users
├─ Agency:  4% of free users
└─ Enterprise: 1% of customers

Expected ARPU:          $8.50
Expected Margin:        80%
Monthly Revenue @ 5K:   $42,500
Monthly Profit @ 5K:    $33,783
```

### Moderate (Expected)

```
Tier Distribution:
├─ Starter: 28% ($4.99)
├─ Pro:     50% ($12.99)
├─ Agency:  10% ($49.99)
└─ Enterprise: 0.1% (custom)

Expected ARPU:          $14.39
Expected Margin:        88%
Monthly Revenue @ 5K:   $71,956
Monthly Profit @ 5K:    $63,239
```

### Aggressive (High Conversion)

```
Tier Distribution:
├─ Starter: 16% ($4.99)
├─ Pro:     50% ($12.99)
├─ Agency:  24% ($49.99)
└─ Enterprise: 0.6% (custom)

Expected ARPU:          $22.15
Expected Margin:        92%
Monthly Revenue @ 5K:   $110,750
Monthly Profit @ 5K:    $101,833
```

---

## 9. Key Performance Indicators (KPIs)

### Financial KPIs (Track Weekly)

| KPI | Target | Actual | Status |
|-----|--------|--------|--------|
| MRR Growth | 15-20% | $_______ | ⬜ |
| Gross Margin % | >80% | ___% | ⬜ |
| API Cost % of Revenue | <5% | ___% | ⬜ |
| Net Profit | $3K+ | $_______ | ⬜ |
| CAC Payback Period | <6 months | ___ months | ⬜ |

### Growth KPIs (Track Daily)

| KPI | Target | Actual | Status |
|-----|--------|--------|--------|
| Daily New Users | 20+ | _____ | ⬜ |
| Churn Rate | <5% | ___% | ⬜ |
| Free-to-Paid Conversion | >3% | ___% | ⬜ |
| NPS Score | >50 | _____ | ⬜ |

### Operational KPIs (Track Hourly)

| KPI | Target | Actual | Status |
|-----|--------|--------|--------|
| API Response Time | <200ms | ___ms | ⬜ |
| Uptime | 99.9% | ___% | ⬜ |
| Error Rate | <0.1% | ___% | ⬜ |
| Cache Hit Rate | >60% | ___% | ⬜ |

---

## 10. Red Flags & Alerts

Watch for these metrics trending wrong:

```
🚨 RED FLAGS:
─────────────────────────────────────────────

1. MRR Growth dropping below 10%:
   □ Possible causes: Market saturation, high churn, weak marketing
   □ Actions: Review product-market fit, increase features, run campaign

2. Churn Rate above 8%:
   □ Possible causes: Poor retention, missing features, bad support
   □ Actions: Send surveys, improve docs, hire support, feature sprint

3. API Costs exceeding 5% of revenue:
   □ Possible causes: Cache issues, inefficient prompts, overuse
   □ Actions: Implement caching, optimize prompts, rate limits

4. Gross Margin falling below 75%:
   □ Possible causes: Unforeseen infrastructure costs, new features
   □ Actions: Reduce scope, optimize infrastructure, raise prices

5. CAC Payback > 12 months:
   □ Possible causes: Low conversion, high acquisition costs
   □ Actions: Improve onboarding, run referral, reduce CAC
```

---

## 11. Monthly Review Checklist

```
□ Update subscriber counts by tier
□ Log all infrastructure & API costs
□ Calculate MRR, ARPU, Churn Rate
□ Review top N paying customers (identify at-risk)
□ Check API usage & efficiency
□ Review support tickets (identify common issues)
□ Calculate LTV, CAC, payback period
□ Compare to budget (document variances)
□ Review KPIs against targets
□ Plan next month's priorities based on metrics
```

---

## 12. Pricing Adjustment Framework

When to raise prices:

```
✓ MRR consistently >$20K
✓ Churn rate <5%
✓ NPS >50
✓ Enterprise tier demand (willing to pay custom)
✓ Gross margin >85%

Then:
1. Increase PRO to $14.99 (+$2.50)
2. Increase AGENCY to $59.99 (+$10)
3. Increase ENTERPRISE minimums
```

When to lower prices or add discounts:

```
✗ MRR growth <10% month-over-month
✗ Free-to-paid conversion <2%
✗ Churn rate >7%
✗ User acquisition cost too high

Then:
1. Test $9.99 for PRO (via A/B test)
2. Add 20% first-year discount for annual plans
3. Create "Starter Pro" at $7.99 (limited features)
4. Launch referral credits ($5 per referral)
```

---

## 13. Burn Rate & Runway

If bootstrapped with initial capital:

```
Initial Capital: $_______

Monthly Burn (if negative margin): $_______
Monthly Profit (if positive margin): $_______

Runway = $_______ ÷ $_______ = _____ months

At Month X: Expected to break even? ☐ Yes ☐ No
```

---

## 14. Template: Monthly P&L Statement

```
═══════════════════════════════════════════════════════════════
                    MONTHLY P&L - [MONTH/YEAR]
═══════════════════════════════════════════════════════════════

REVENUE:
  Starter ($4.99 × _____ users)           $________
  Pro ($12.99 × _____ users)              $________
  Agency ($49.99 × _____ users)           $________
  Enterprise (custom)                     $________
  ─────────────────────────────────────
  TOTAL REVENUE                            $________

COST OF GOODS SOLD (COGS) - APIs:
  OpenAI                                   $________
  Gemini Vision                            $________
  Email/Auth Services                     $________
  ─────────────────────────────────────
  TOTAL COGS                               $________

GROSS PROFIT                               $________
Gross Margin %                             ______%

OPERATING EXPENSES:
  Personnel                                $________
  Infrastructure                          $________
  Marketing                                $________
  Miscellaneous                            $________
  ─────────────────────────────────────
  TOTAL OPEX                               $________

OPERATING PROFIT (EBIT)                    $________
EBIT Margin %                              ______%

Taxes (est. 25%)                           $________

NET PROFIT                                 $________
Net Margin %                               ______%

═══════════════════════════════════════════════════════════════
```

---

## 15. Data Entry Template (Copy into Spreadsheet)

```
Date,Metric,Value,Notes
2026-05-01,Total Users,0,Launch date
2026-05-01,Starter Subscribers,0,
2026-05-01,Pro Subscribers,0,
2026-05-01,Agency Subscribers,0,
2026-05-01,Enterprise Subscribers,0,
2026-05-01,MRR,0,
2026-05-01,Churn Rate,0%,
2026-05-01,Infrastructure Cost,887,
2026-05-01,API Cost,1910,
2026-05-01,Personnel Cost,5000,
2026-05-01,Overhead,920,
2026-05-01,Total Cost,8717,
2026-05-01,Gross Profit,0,
2026-05-01,CAC,0,
2026-05-01,LTV,0,
```

---

## Export & Visualization

### Recommended Charts (Build in Sheets/Excel):

1. **MRR Trend** — Line chart over 12 months
2. **Subscriber Breakdown** — Pie chart (Starter/Pro/Agency/Enterprise)
3. **Cost Breakdown** — Stacked bar chart (COGS vs OPEX)
4. **Margin Trend** — Gross Margin % over time
5. **CAC Payback** — CAC vs LTV comparison
6. **Cohort Retention** — Churn by user cohort

---

## Assumptions (Update Quarterly)

```
□ Average customer lifetime: 18 months
□ Churn rate: 5% per month
□ Support cost per user: $0.20/month
□ API cost per analysis: $0.08
□ Conversion rate (free to paid): 3-5%
□ CAC target: <$5 per user
□ LTV:CAC target: >20:1
```

---

**Last Updated:** May 1, 2026  
**Next Review:** June 1, 2026  
**Prepared by:** Finance Team
